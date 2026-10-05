import sqlite3
import threading
import time

import pytest

from cheevos.core.errors import ApiPayloadError, CheevosError, NetworkError
from cheevos.core.storage.media_cache import MediaCache
from cheevos.core.sync.lazy_media import LazyMediaFetcher


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.005)


class FakeClient:
    """Media downloader: returns bytes, raises configured errors, can block on a gate."""

    def __init__(self):
        self.calls = []
        self.errors = {}
        self.gated = set()
        self.gate = threading.Event()
        self.lock = threading.Lock()

    def media(self, path):
        with self.lock:
            self.calls.append(path)
        if path in self.gated:
            self.gate.wait(5)
        error = self.errors.get(path)
        if error is not None:
            raise error
        return b"PNG" + path.encode()


class Harness:
    def __init__(self, tmp_path, **kwargs):
        self.tmp_path = tmp_path
        self.client = FakeClient()
        self.closed = threading.Event()
        self.opens = 0
        self.now = 0.0
        self.fetcher = LazyMediaFetcher(self.open_session, clock=lambda: self.now, **kwargs)

    def open_session(self):
        self.opens += 1
        media = MediaCache.open(self.tmp_path / "media.db", self.tmp_path / "scratch")

        def close():
            media.close()
            self.closed.set()

        return self.client, media, close

    def stored(self, key):
        reader = MediaCache.open(self.tmp_path / "media.db", self.tmp_path / "reader")
        try:
            return reader.has(key)
        finally:
            reader.close()


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.client.gate.set()
    h.fetcher.close()


def test_success_stores_and_bumps_version(harness):
    assert harness.fetcher.version == 0
    harness.fetcher.request("badge/1", "/Badge/1.png")
    wait_until(lambda: harness.fetcher.version == 1)
    assert harness.fetcher.pending() == 0
    assert harness.stored("badge/1")


def test_requests_are_deduplicated_while_queued_in_flight_and_after_storing(harness):
    harness.client.gated.add("/Badge/1.png")
    harness.fetcher.request("badge/1", "/Badge/1.png")
    wait_until(lambda: harness.client.calls == ["/Badge/1.png"])
    harness.fetcher.request("badge/1", "/Badge/1.png")
    assert harness.fetcher.pending() == 1
    harness.client.gate.set()
    wait_until(lambda: harness.fetcher.version == 1)
    harness.fetcher.request("badge/1", "/Badge/1.png")
    assert harness.fetcher.pending() == 0
    assert harness.client.calls == ["/Badge/1.png"]


def test_missing_image_is_not_retried(harness):
    harness.client.errors["/Badge/404.png"] = ApiPayloadError("HTTP 404")
    harness.fetcher.request("badge/404", "/Badge/404.png")
    wait_until(lambda: harness.client.calls and harness.fetcher.pending() == 0)
    harness.fetcher.request("badge/404", "/Badge/404.png")
    harness.fetcher.request("badge/ok", "/Badge/ok.png")
    wait_until(lambda: harness.fetcher.version == 1)
    assert harness.client.calls.count("/Badge/404.png") == 1
    assert not harness.stored("badge/404")


def test_network_error_backs_off_and_drops_the_queue(harness):
    first = "/Badge/1.png"
    harness.client.gated.add(first)
    harness.client.errors[first] = NetworkError("offline")
    harness.fetcher.request("badge/1", first)
    wait_until(lambda: harness.client.calls == [first])
    harness.fetcher.request("badge/2", "/Badge/2.png")
    harness.fetcher.request("badge/3", "/Badge/3.png")
    assert harness.fetcher.pending() == 3
    harness.client.gate.set()
    wait_until(lambda: harness.fetcher.pending() == 0)
    assert harness.client.calls == [first]

    harness.fetcher.request("badge/4", "/Badge/4.png")  # still in backoff: ignored
    assert harness.fetcher.pending() == 0

    harness.now = 61.0  # backoff over; the failed key may be requested again
    del harness.client.errors[first]
    harness.fetcher.request("badge/1", first)
    wait_until(lambda: harness.fetcher.version == 1)
    assert harness.stored("badge/1")


def test_full_queue_drops_requests_which_can_be_repeated(tmp_path):
    harness = Harness(tmp_path, max_queue=2)
    try:
        harness.client.gated.add("/a.png")
        harness.fetcher.request("a", "/a.png")
        wait_until(lambda: harness.client.calls == ["/a.png"])
        for key in ("b", "c", "d"):
            harness.fetcher.request(key, f"/{key}.png")
        assert harness.fetcher.pending() == 3  # a in flight, b and c queued, d dropped
        harness.client.gate.set()
        wait_until(lambda: harness.fetcher.version == 3)
        assert harness.client.calls == ["/a.png", "/b.png", "/c.png"]
        harness.fetcher.request("d", "/d.png")
        wait_until(lambda: harness.fetcher.version == 4)
    finally:
        harness.client.gate.set()
        harness.fetcher.close()


def test_close_releases_the_session_and_ignores_later_requests(harness):
    harness.fetcher.request("badge/1", "/Badge/1.png")
    wait_until(lambda: harness.fetcher.version == 1)
    harness.fetcher.close()
    assert harness.closed.is_set()
    harness.fetcher.request("badge/2", "/Badge/2.png")
    assert harness.fetcher.pending() == 0


def test_close_without_any_request_is_a_no_op(harness):
    harness.fetcher.close()
    assert harness.opens == 0


def test_open_failure_disables_the_fetcher(tmp_path):
    opens = []

    def open_session():
        opens.append(1)
        raise CheevosError("no key")

    fetcher = LazyMediaFetcher(open_session)
    try:
        fetcher.request("badge/1", "/Badge/1.png")
        wait_until(lambda: fetcher.pending() == 0 and opens)
        fetcher.request("badge/2", "/Badge/2.png")
        assert fetcher.pending() == 0
        assert len(opens) == 1
        assert fetcher.version == 0
    finally:
        fetcher.close()


class BrokenStore:
    def __init__(self):
        self.fail = True
        self.stored = {}

    def put(self, key, data):
        if self.fail:
            raise sqlite3.OperationalError("database is locked")
        self.stored[key] = data


def test_storage_error_forgets_the_key_so_it_can_be_retried():
    client = FakeClient()
    store = BrokenStore()
    fetcher = LazyMediaFetcher(lambda: (client, store, lambda: None))
    try:
        fetcher.request("badge/1", "/Badge/1.png")
        wait_until(lambda: client.calls and fetcher.pending() == 0)
        assert fetcher.version == 0
        store.fail = False
        fetcher.request("badge/1", "/Badge/1.png")
        wait_until(lambda: fetcher.version == 1)
        assert "badge/1" in store.stored
    finally:
        fetcher.close()


def test_close_errors_are_logged_not_raised(caplog):
    def bad_close():
        raise OSError("disk gone")

    fetcher = LazyMediaFetcher(lambda: (FakeClient(), BrokenStore(), bad_close))
    fetcher.request("k", "/k.png")
    wait_until(lambda: fetcher.pending() == 0)
    fetcher.close()
    assert "Closing the image session failed" in caplog.text
