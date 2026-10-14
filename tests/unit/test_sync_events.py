import json
import threading
from pathlib import Path

import pytest

from cheevos.core.errors import RequestCancelledError
from cheevos.core.ra_client.client import RaClient
from cheevos.core.ra_client.parse_awards import parse_awards
from cheevos.core.ra_client.transport import API_V2_HOST, FixtureTransport, Response
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache, award_key
from cheevos.core.sync.engine import SyncDeps, SyncEngine, SyncOptions
from cheevos.core.sync.events import EVENT_REFRESH, stale_events, sync_events
from cheevos.core.sync.progress import Phase, ProgressTracker
from cheevos.platform.desktop.showcase_awards import award_rows, image_paths, v2_body

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
NOW = 1_791_158_400  # 2026-10-05 00:00 UTC
AWARDS = award_rows(0)  # the showcase's events (196, 164, 141, 221) and site badges


class EventAwards:
    """The fixtures, with the showcase's event and site awards and RA's v2 API for them."""

    def __init__(self, media_dir=None, *, failing=frozenset()):
        self.base = FixtureTransport(FIXTURES, media_dir=media_dir)
        self.v2 = []
        self.failing = failing  # v2 resources answering 401

    @property
    def calls(self):
        return self.base.calls

    def get(self, host, path, headers):
        if host == API_V2_HOST:
            resource = path.split("?")[0]
            self.v2.append(resource)
            if resource in self.failing:
                return Response(status=401, body=b'{"errors": [{"status": "401"}]}')
            return Response(status=200, body=json.dumps(v2_body(path)).encode())
        if "API_GetUserAwards" in path:
            body = {"VisibleUserAwards": AWARDS}
            return Response(status=200, body=json.dumps(body).encode())
        return self.base.get(host, path, headers)


def client(transport):
    return RaClient("Balah", "k" * 32, transport, user_agent="test", min_interval=0)


@pytest.fixture
def data(tmp_path):
    cache = DataCache.open(tmp_path / "data.db", "Balah")
    yield cache
    cache.close()


def visible():
    return parse_awards({"VisibleUserAwards": AWARDS})[1]


def test_events_are_fetched_once_with_their_tiers_and_points(data):
    transport = EventAwards()
    sync_events(client(transport), data, visible(), NOW, threading.Event())
    assert transport.v2 == ["/v2/events", "/v2/event-achievements"]
    events = data.events()
    assert sorted(events) == [141, 164, 196, 221]
    assert events[196].points == 64
    assert [tier.label for tier in events[196].tiers] == ["Bronze", "Silver", "Gold", "Champion"]
    assert events[221].tiers == ()
    transport.v2.clear()
    sync_events(client(transport), data, visible(), NOW + 3_600, threading.Event())
    assert transport.v2 == []  # fresh: no request


def test_stale_and_newly_earned_events_are_fetched_again(data):
    awards = visible()
    fetched = {196: NOW, 164: NOW - EVENT_REFRESH - 1, 141: 0, 221: NOW}
    # 164 is stale; 141's award was earned after it was fetched; 196 and 221 are fresh.
    assert stale_events(awards, fetched, NOW) == [141, 164]
    assert stale_events(awards, {}, NOW) == [141, 164, 196, 221]
    assert stale_events([a for a in awards if a.type.value != "Event"], {}, NOW) == []


@pytest.mark.parametrize(
    ("failing", "known", "points"),
    [
        (frozenset({"/v2/events"}), False, None),
        (frozenset({"/v2/event-achievements"}), True, None),
    ],
)
def test_v2_refusals_leave_honest_fallbacks(data, caplog, failing, known, points):
    sync_events(client(EventAwards(failing=failing)), data, visible(), NOW, threading.Event())
    events = data.events()
    assert (196 in events) is known
    assert (events[196].points if known else None) == points
    assert "unavailable" in caplog.text
    assert data.event_fetch_times() == ({} if not known else dict.fromkeys(events, NOW))


def test_cancelled_sync_stops_before_asking(data):
    cancel = threading.Event()
    cancel.set()
    transport = EventAwards()
    with pytest.raises(RequestCancelledError):
        sync_events(client(transport), data, visible(), NOW, cancel)
    assert transport.v2 == []


def test_a_sync_stores_events_and_downloads_their_art(tmp_path):
    media_dir = tmp_path / "media-host"
    for path in image_paths():
        target = media_dir / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG:" + path.encode())
    transport = EventAwards(media_dir, failing=frozenset())
    data = DataCache.open(tmp_path / "data.db", "Balah")
    media = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")
    deps = SyncDeps(client(transport), data, media)
    engine = SyncEngine(
        deps, ProgressTracker(), threading.Event(), clock=lambda: NOW, online=lambda: True
    )
    assert engine.run(SyncOptions()).phase is Phase.DONE
    assert sorted(data.events()) == [141, 164, 196, 221]
    assert media.has(award_key("/Images/122639.png"))  # AotW 2026, Silver
    assert media.has(award_key("/Images/104712.png"))  # AotW 2024 shows its Gold tier
    assert media.has(award_key("/assets/images/badge/patreon.png"))
    assert len(data.awards()[1]) == len(AWARDS)
    data.close()
    media.close()


def test_v2_refusal_is_not_a_rejected_key(tmp_path):
    transport = EventAwards(failing=frozenset({"/v2/events", "/v2/event-achievements"}))
    data = DataCache.open(tmp_path / "data.db", "Balah")
    media = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")
    deps = SyncDeps(client(transport), data, media)
    engine = SyncEngine(
        deps, ProgressTracker(), threading.Event(), clock=lambda: NOW, online=lambda: True
    )
    status = engine.run(SyncOptions())
    assert status.phase is Phase.DONE  # the v1 API took the key: not "API key rejected"
    assert len(data.awards()[1]) == len(AWARDS)  # the awards still show
    data.close()
    media.close()
