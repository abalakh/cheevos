import json
import threading
from pathlib import Path

import pytest

from cheevos.core.errors import AuthError, CheevosError
from cheevos.core.ra_client.client import RaClient
from cheevos.core.ra_client.transport import FixtureTransport, Response
from cheevos.core.settings import BadgeScope
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache, avatar_key, badge_key, icon_key
from cheevos.core.sync.engine import (
    LAST_SYNC_KEY,
    BackgroundSync,
    SyncDeps,
    SyncEngine,
    SyncOptions,
)
from cheevos.core.sync.progress import Failure, Phase, ProgressTracker

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
NOW = 1_791_158_400  # 2026-10-05 00:00 UTC
FFTA = 519


def recorded_game_ids():
    return sorted(int(p.stem.split("_")[1]) for p in FIXTURES.glob("game_*.json"))


def build_media_dir(root: Path) -> Path:
    """Mirror the media host for every image the fixtures reference."""
    summary = json.loads((FIXTURES / "user_summary.json").read_text())
    paths = {summary["UserPic"]}
    for game_id in recorded_game_ids():
        game = json.loads((FIXTURES / f"game_{game_id}.json").read_text())
        paths.add(game["ImageIcon"])
        for achievement in game["Achievements"].values():
            paths.add(f"/Badge/{achievement['BadgeName']}.png")
            paths.add(f"/Badge/{achievement['BadgeName']}_lock.png")
    for path in paths:
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG:" + path.encode())
    return root


class Harness:
    def __init__(self, tmp_path: Path, transport=None, on_device=frozenset({FFTA})):
        self.transport = transport or FixtureTransport(
            FIXTURES, media_dir=build_media_dir(tmp_path / "media-host")
        )
        self.client = RaClient("Balah", "k" * 32, self.transport, user_agent="test", min_interval=0)
        self.data = DataCache.open(tmp_path / "data.db", "Balah")
        self.media = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")
        self.tracker = ProgressTracker()
        self.cancel = threading.Event()
        self.online = True
        self.clock_ok = True
        self.on_device = set(on_device)

    def engine(self):
        deps = SyncDeps(self.client, self.data, self.media, on_device=lambda: self.on_device)
        return SyncEngine(
            deps,
            self.tracker,
            self.cancel,
            clock=lambda: NOW,
            online=lambda: self.online,
            clock_ok=lambda _now: self.clock_ok,
        )

    def calls(self):
        return [method for method, _ in self.transport.calls]


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def test_first_sync_fills_the_caches(harness):
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert status.details_fetched == len(recorded_game_ids())
    assert harness.data.load_profile().username == "Balah"
    assert len(harness.data.games()) == 12
    ffta = harness.data.game_detail(FFTA)
    assert ffta is not None
    assert len(ffta.achievements) == 138
    assert harness.data.get_meta(LAST_SYNC_KEY) == str(NOW)
    # Images: avatar, every game icon, and FFTA's badges (on device) in their current state.
    assert harness.media.has(avatar_key("Balah"))
    assert all(harness.media.has(icon_key(game_id)) for game_id in recorded_game_ids())
    unlocked = next(a for a in ffta.achievements if a.unlocked)
    locked = next(a for a in ffta.achievements if not a.unlocked)
    assert harness.media.has(badge_key(unlocked.badge_name, locked=False))
    assert harness.media.has(badge_key(locked.badge_name, locked=True))
    assert not harness.media.has(badge_key(unlocked.badge_name, locked=True))


def test_second_sync_without_playing_fetches_no_details_or_images(harness):
    harness.engine().run(SyncOptions())
    harness.transport.calls.clear()
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert status.details_fetched == 0
    assert status.media_fetched == 0
    assert harness.calls() == [
        "API_GetUserSummary",
        "API_GetUserCompletionProgress",
        "API_GetUserRecentlyPlayedGames",
        "API_GetUserAwards",
    ]


def test_changed_game_is_the_only_one_refetched(harness):
    harness.engine().run(SyncOptions())
    stored = harness.data.game_detail(FFTA)
    harness.data.save_game_detail(stored, fingerprint="before-new-unlock", synced_at=NOW)
    harness.transport.calls.clear()
    status = harness.engine().run(SyncOptions())
    assert status.details_fetched == 1
    assert harness.calls().count("API_GetGameInfoAndUserProgress") == 1


def test_full_resync_refetches_everything(harness):
    harness.engine().run(SyncOptions())
    status = harness.engine().run(SyncOptions(full=True))
    assert status.details_fetched == len(recorded_game_ids())


def test_cancel_mid_details_then_resume_fetches_only_the_rest(harness):
    calls = {"details": 0}
    original = harness.client.game_detail

    def cancelling_game_detail(game_id):
        calls["details"] += 1
        if calls["details"] == 3:
            harness.cancel.set()
        return original(game_id)

    harness.client.game_detail = cancelling_game_detail
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.CANCELLED
    assert status.details_fetched == 3
    harness.cancel.clear()
    harness.client.game_detail = original
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert status.details_fetched == len(recorded_game_ids()) - 3


@pytest.mark.parametrize(
    ("online", "clock_ok", "failure"),
    [(False, True, Failure.OFFLINE), (True, False, Failure.CLOCK)],
)
def test_preflight_failures_make_no_requests(harness, online, clock_ok, failure):
    harness.online, harness.clock_ok = online, clock_ok
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.FAILED
    assert status.failure is failure
    assert harness.calls() == []


class RejectingTransport:
    def __init__(self):
        self.calls = []

    def get(self, host, path, headers):
        return Response(status=401, body=b'{"message":"Unauthenticated."}')


def test_rejected_key_fails_with_auth(tmp_path):
    harness = Harness(tmp_path, transport=RejectingTransport())
    status = harness.engine().run(SyncOptions())
    assert status.failure is Failure.AUTH


class FlakyMediaTransport(FixtureTransport):
    def get(self, host, path, headers):
        if path.startswith("/Badge/"):
            return Response(status=404, body=b"")
        return super().get(host, path, headers)


def test_missing_badges_are_skipped_not_fatal(tmp_path):
    transport = FlakyMediaTransport(FIXTURES, media_dir=build_media_dir(tmp_path / "host"))
    harness = Harness(tmp_path, transport=transport)
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert harness.media.has(avatar_key("Balah"))


@pytest.mark.parametrize(
    ("scope", "expect_badges"),
    [(BadgeScope.NONE, False), (BadgeScope.ALL, True)],
)
def test_badge_scope(tmp_path, scope, expect_badges):
    harness = Harness(tmp_path, on_device=frozenset())
    harness.engine().run(SyncOptions(badge_scope=scope))
    zelda = harness.data.game_detail(355)
    assert zelda is not None
    first = zelda.achievements[0]
    key = badge_key(first.badge_name, locked=not first.unlocked)
    assert harness.media.has(key) is expect_badges


def has_any_badge(harness, game_id):
    detail = harness.data.game_detail(game_id)
    assert detail is not None
    return any(
        harness.media.has(badge_key(a.badge_name, locked=not a.unlocked))
        for a in detail.achievements
    )


def test_recent_scope_takes_recently_played_games_only(tmp_path):
    harness = Harness(tmp_path, on_device=frozenset())
    harness.engine().run(SyncOptions(recent_days=30))
    assert has_any_badge(harness, 554)  # Fire Emblem, played the day before NOW
    assert not has_any_badge(harness, FFTA)  # last played 33 days before NOW
    assert not has_any_badge(harness, 355)  # 2023


def test_background_sync_runs_on_a_worker_and_closes(tmp_path):
    closed = threading.Event()
    transport = FixtureTransport(FIXTURES, media_dir=build_media_dir(tmp_path / "host"))

    def open_deps():
        client = RaClient("Balah", "k" * 32, transport, user_agent="test", min_interval=0)
        data = DataCache.open(tmp_path / "data.db", "Balah")
        media = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")

        def close():
            data.close()
            media.close()
            closed.set()

        return SyncDeps(client, data, media, close=close)

    sync = BackgroundSync(open_deps, online=lambda: True, clock_ok=lambda _now: True)
    assert sync.start(SyncOptions())
    sync.join(timeout=30)
    assert sync.status().phase is Phase.DONE
    assert closed.is_set()
    assert not sync.status().running


def test_background_sync_reports_open_failure(tmp_path):
    def open_deps():
        raise CheevosError("no key")

    sync = BackgroundSync(open_deps, online=lambda: True, clock_ok=lambda _now: True)
    sync.start(SyncOptions())
    sync.join(timeout=5)
    assert sync.status().failure is Failure.ERROR


def test_auth_error_type_is_cheevos_error():
    assert issubclass(AuthError, CheevosError)


class StatusTransport(FixtureTransport):
    """Fixture transport that answers one endpoint (or media) with a fixed status."""

    def __init__(self, *args, fail_on, status, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_on = fail_on
        self.status = status

    def get(self, host, path, headers):
        if self.fail_on in path:
            return Response(status=self.status, headers={"retry-after": "0"}, body=b"{}")
        return super().get(host, path, headers)


@pytest.mark.parametrize(
    ("fail_on", "status", "failure"),
    [
        ("API_GetUserAwards", 429, Failure.RATE_LIMITED),
        ("API_GetGameInfoAndUserProgress", 503, Failure.NETWORK),
        ("API_GetUserAwards", 418, Failure.ERROR),
    ],
)
def test_request_failures_map_to_failure_reasons(tmp_path, fail_on, status, failure):
    transport = StatusTransport(
        FIXTURES, media_dir=build_media_dir(tmp_path / "host"), fail_on=fail_on, status=status
    )
    harness = Harness(tmp_path, transport=transport)
    harness.client._sleep = lambda _seconds: None
    status_ = harness.engine().run(SyncOptions())
    assert status_.phase is Phase.FAILED
    assert status_.failure is failure


def test_network_drop_during_media_keeps_downloaded_images(tmp_path):
    transport = StatusTransport(
        FIXTURES, media_dir=build_media_dir(tmp_path / "host"), fail_on="/Badge/", status=502
    )
    harness = Harness(tmp_path, transport=transport)
    status = harness.engine().run(SyncOptions())
    assert status.failure is Failure.NETWORK
    assert harness.media.has(avatar_key("Balah"))  # fetched before the first badge


def test_background_sync_refuses_a_second_concurrent_start(tmp_path):
    release = threading.Event()

    def open_deps():
        release.wait(5)
        raise CheevosError("stop")

    sync = BackgroundSync(open_deps, online=lambda: True, clock_ok=lambda _now: True)
    assert sync.start(SyncOptions())
    assert sync.status().running
    assert not sync.start(SyncOptions())
    sync.cancel()
    release.set()
    sync.join(timeout=5)


def test_interrupted_full_resync_resumes_as_full(harness):
    harness.engine().run(SyncOptions())  # warm cache: everything fresh
    clock = {"now": NOW + 100}
    calls = {"details": 0}
    original = harness.client.game_detail

    def cancelling_game_detail(game_id):
        calls["details"] += 1
        if calls["details"] == 4:
            harness.cancel.set()
        return original(game_id)

    harness.client.game_detail = cancelling_game_detail

    def engine():
        deps = SyncDeps(harness.client, harness.data, harness.media, on_device=set)
        return SyncEngine(
            deps,
            harness.tracker,
            harness.cancel,
            clock=lambda: clock["now"],
            online=lambda: True,
            clock_ok=lambda _now: True,
        )

    status = engine().run(SyncOptions(full=True))
    assert status.phase is Phase.CANCELLED
    harness.cancel.clear()
    harness.client.game_detail = original
    clock["now"] += 100
    status = engine().run(SyncOptions())  # a normal sync finishes the full re-sync
    assert status.details_fetched == len(recorded_game_ids()) - 4
    clock["now"] += 100
    assert engine().run(SyncOptions()).details_fetched == 0  # and then it's done
