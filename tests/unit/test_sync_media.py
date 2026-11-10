"""The sync's image phase: badge scopes, the full library's badges, skipped and resumed images."""

import pytest
from sync_harness import FFTA, FIXTURES, NOW, Harness, build_media_dir, recorded_game_ids

from cheevos.core.errors import RequestCancelledError
from cheevos.core.ra_client.transport import FixtureTransport, Response
from cheevos.core.storage.media_cache import avatar_key, badge_key
from cheevos.core.sync.options import FULL_SINCE_KEY, BadgeScope, SyncOptions
from cheevos.core.sync.progress import Phase


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory):
    # Transports only read this source; each test still owns its caches and request history.
    return build_media_dir(tmp_path_factory.mktemp("sync-media-host"))


@pytest.fixture
def harness(tmp_path, media_dir):
    return Harness(tmp_path, media_dir)


def test_full_resync_refetches_every_game_and_downloads_its_badges(harness):
    harness.engine().run(SyncOptions())
    status = harness.engine().run(SyncOptions(full=True, badge_scope=BadgeScope.NONE))
    assert status.phase is Phase.DONE
    assert status.details_fetched == len(recorded_game_ids())
    for game_id in recorded_game_ids():
        detail = harness.data.game_detail(game_id)
        assert detail is not None
        assert not harness.media.missing(
            badge_key(a.badge_name, locked=not a.unlocked) for a in detail.achievements
        )
    assert harness.data.get_meta(FULL_SINCE_KEY) is None


def test_full_library_images_are_planned_in_chunks_without_repeats(harness, monkeypatch):
    # Chunks smaller than the library: feed badges repeat game badges from earlier chunks.
    monkeypatch.setattr("cheevos.core.sync.engine.MEDIA_PLAN_BATCH", 7)
    original = harness.client.media
    requested = []

    def record(path):
        requested.append(path)
        return original(path)

    harness.client.media = record
    status = harness.engine().run(SyncOptions(full=True))
    assert status.phase is Phase.DONE
    assert len(requested) == len(set(requested))
    assert status.media_fetched == len(requested)
    for game_id in recorded_game_ids():
        detail = harness.data.game_detail(game_id)
        assert detail is not None
        assert not harness.media.missing(
            badge_key(a.badge_name, locked=not a.unlocked) for a in detail.achievements
        )


def test_full_resync_resumes_missing_badges_after_cancellation(harness):
    harness.engine().run(SyncOptions())
    original = harness.client.media
    requested = []

    def interrupt(path):
        requested.append(path)
        if len(requested) == 2:
            raise RequestCancelledError
        return original(path)

    harness.client.media = interrupt
    status = harness.engine().run(SyncOptions(full=True))
    assert status.phase is Phase.CANCELLED
    assert harness.data.get_meta(FULL_SINCE_KEY) is not None
    completed, interrupted = requested
    requested.clear()

    def record(path):
        requested.append(path)
        return original(path)

    harness.client.media = record
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert status.details_fetched == 0
    assert completed not in requested
    assert interrupted in requested
    assert harness.data.get_meta(FULL_SINCE_KEY) is None


class FlakyMediaTransport(FixtureTransport):
    def get(self, host, path, headers):
        if path.startswith("/Badge/"):
            return Response(status=404, body=b"")
        return super().get(host, path, headers)


def test_missing_badges_are_skipped_not_fatal(tmp_path, media_dir):
    transport = FlakyMediaTransport(FIXTURES, media_dir=media_dir)
    harness = Harness(tmp_path, media_dir, transport=transport)
    status = harness.engine().run(SyncOptions())
    assert status.phase is Phase.DONE
    assert harness.media.has(avatar_key("Balah"))


@pytest.mark.parametrize(
    ("scope", "expect_badges"),
    [(BadgeScope.NONE, False), (BadgeScope.ALL, True)],
)
def test_badge_scope(tmp_path, media_dir, scope, expect_badges):
    harness = Harness(tmp_path, media_dir, on_device=frozenset())
    harness.engine().run(SyncOptions(badge_scope=scope))
    fire_emblem = harness.data.game_detail(554)
    assert fire_emblem is not None
    first = fire_emblem.achievements[0]
    key = badge_key(first.badge_name, locked=not first.unlocked)
    assert harness.media.has(key) is expect_badges


def test_normal_sync_uses_30_days_for_details_and_badges(harness):
    harness.on_device.clear()
    # FFTA was played 32 days ago, while Fire Emblem was played yesterday.
    harness.engine().run(SyncOptions())
    assert harness.media.has(badge_key("176564", locked=True))  # Fire Emblem
    # Feed badges are kept for offline browsing, without fetching either full set.
    assert harness.data.game_detail(FFTA) is None
    assert harness.data.game_detail(355) is None
    assert harness.media.has(badge_key("198102", locked=False))
    # Even if the user opened an old game, its locked badges stay outside the working set.
    game = harness.data.game(FFTA)
    detail = harness.client.game_detail(FFTA)
    harness.data.save_game_detail(detail, fingerprint=game.fingerprint, synced_at=NOW)
    harness.engine().run(SyncOptions())
    locked = next(a for a in detail.achievements if not a.unlocked)
    assert not harness.media.has(badge_key(locked.badge_name, locked=True))
