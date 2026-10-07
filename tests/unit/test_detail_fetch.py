import json
import threading
import time
from pathlib import Path

import pytest

from cheevos.core.errors import (
    ApiPayloadError,
    AuthError,
    NetworkError,
    RateLimitedError,
    RequestCancelledError,
)
from cheevos.core.ra_client.parse import parse_game_detail
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.sync.detail_fetch import DetailFetcher, FetchState
from cheevos.core.sync.engine import RATE_LIMITED_UNTIL_KEY
from cheevos.core.sync.progress import Failure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
NOW = 1_791_158_400.0
FFTA, DESCENT, METROID = 519, 3830, 1487


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.005)


class FakeClient:
    """Serves recorded game details; raises configured errors; can hold one game at a gate."""

    def __init__(self, stop):
        self.stop = stop
        self.calls = []
        self.errors = {}
        self.gated = set()
        self.gate = threading.Event()

    def game_detail(self, game_id):
        self.calls.append(game_id)
        if game_id in self.gated and not self.gate.wait(5):
            raise AssertionError("gate never opened")
        if self.stop.is_set():
            raise RequestCancelledError
        error = self.errors.get(game_id)
        if error is not None:
            raise error
        data = json.loads((FIXTURES / f"game_{game_id}.json").read_text())
        return parse_game_detail(data)


def settled(fetcher, game_id):
    """Wait until a requested game is no longer waiting, and return its status."""

    def ready():
        status = fetcher.status(game_id)
        return status is not None and status.state is not FetchState.WAITING

    wait_until(ready)
    status = fetcher.status(game_id)
    assert status is not None
    return status


class Harness:
    def __init__(self, tmp_path):
        self.db = tmp_path / "data.db"
        DataCache.open(self.db, "Balah").close()
        self.clients = []
        self.closes = 0
        self.errors = {}
        self.gated = set()
        self.gate = threading.Event()
        self.now = NOW
        self.fetcher = DetailFetcher(self.open_session, clock=lambda: self.now)

    def open_session(self, stop):
        client = FakeClient(stop)
        client.errors, client.gated, client.gate = self.errors, self.gated, self.gate
        self.clients.append(client)
        data = DataCache.open(self.db, "Balah")

        def close():
            data.close()
            self.closes += 1

        return client, data, close

    def calls(self):
        return [game_id for client in self.clients for game_id in client.calls]

    def finished(self, game_id):
        return settled(self.fetcher, game_id)

    def cache(self):
        return DataCache.open(self.db, "Balah")


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.gate.set()
    h.fetcher.close()


def test_a_requested_game_is_fetched_and_stored(harness):
    assert harness.fetcher.status(FFTA) is None
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).state is FetchState.DONE
    cache = harness.cache()
    assert len(cache.game_detail(FFTA).achievements) == 138
    cache.close()


def test_a_fetched_game_is_not_fetched_again(harness):
    harness.fetcher.request(FFTA)
    harness.finished(FFTA)
    harness.fetcher.request(FFTA)
    time.sleep(0.05)
    assert harness.calls() == [FFTA]


def test_the_latest_request_goes_first(harness):
    harness.gated.add(FFTA)
    harness.fetcher.request(FFTA)  # in flight, held at the gate
    wait_until(lambda: harness.calls() == [FFTA])
    harness.fetcher.request(DESCENT)
    harness.fetcher.request(METROID)
    harness.fetcher.request(DESCENT)  # asked again: moves ahead of Metroid
    harness.gate.set()
    harness.finished(METROID)
    assert harness.calls() == [FFTA, DESCENT, METROID]


@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (NetworkError("no route"), Failure.NETWORK),
        (ApiPayloadError("HTTP 404"), Failure.ERROR),
    ],
)
def test_failures_are_reported_and_a_new_request_retries(harness, error, failure):
    harness.errors[FFTA] = error
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).failure is failure
    del harness.errors[FFTA]
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).state is FetchState.DONE


def test_a_rejected_key_reopens_the_session_for_the_next_request(harness):
    harness.errors[FFTA] = AuthError("rejected")
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).failure is Failure.AUTH
    wait_until(lambda: harness.closes == 1)
    harness.fetcher.request(DESCENT)
    assert harness.finished(DESCENT).state is FetchState.DONE
    assert len(harness.clients) == 2


def test_a_long_rate_limit_is_stored_for_the_sync_too(harness):
    harness.errors[FFTA] = RateLimitedError(600)
    harness.fetcher.request(FFTA)
    status = harness.finished(FFTA)
    assert (status.failure, status.retry_at) == (Failure.RATE_LIMITED, NOW + 600)
    cache = harness.cache()
    assert cache.get_meta(RATE_LIMITED_UNTIL_KEY) == str(int(NOW + 600))
    cache.close()
    harness.fetcher.request(DESCENT)  # RA's pause isn't over: not even asked
    assert harness.finished(DESCENT).failure is Failure.RATE_LIMITED
    assert harness.calls() == [FFTA]


def test_an_unset_clock_does_not_block_a_request(harness):
    harness.now = 0
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).state is FetchState.DONE
    assert harness.calls() == [FFTA]


@pytest.mark.parametrize("pause", [NOW - 60, NOW + 600])
def test_stored_pause_uses_refreshed_time_after_a_cold_boot(harness, pause):
    cache = harness.cache()
    cache.set_meta(RATE_LIMITED_UNTIL_KEY, str(int(pause)))
    cache.close()
    harness.now = 0

    def online():
        harness.now = NOW
        return True

    harness.fetcher._online = online
    harness.fetcher.request(FFTA)
    status = harness.finished(FFTA)
    if pause < NOW:
        assert status.state is FetchState.DONE
        assert harness.calls() == [FFTA]
    else:
        assert status.failure is Failure.RATE_LIMITED
        assert harness.calls() == []


def test_pause_time_refresh_failure_leaves_the_cache_usable(harness):
    cache = harness.cache()
    cache.set_meta(RATE_LIMITED_UNTIL_KEY, str(int(NOW + 600)))
    cache.close()
    harness.fetcher._online = lambda: False
    harness.fetcher.request(FFTA)
    assert harness.finished(FFTA).failure is Failure.NETWORK
    assert harness.calls() == []


def test_close_interrupts_and_releases_the_session(harness):
    harness.gated.add(FFTA)
    harness.fetcher.request(FFTA)
    wait_until(lambda: harness.calls() == [FFTA])
    harness.fetcher.close(timeout=0.2)  # the client's wait ends with the stop event
    harness.gate.set()
    wait_until(lambda: harness.closes == 1)
    assert harness.fetcher.status(FFTA) is None  # forgotten, not failed
    harness.fetcher.request(DESCENT)
    assert harness.fetcher.status(DESCENT) is None  # ignored after close


def test_a_session_that_cannot_open_fails_the_request(tmp_path):
    def open_session(_stop):
        raise OSError("no card")

    fetcher = DetailFetcher(open_session)
    fetcher.request(FFTA)
    assert settled(fetcher, FFTA).failure is Failure.ERROR
    fetcher.close()
