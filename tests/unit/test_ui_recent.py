from dataclasses import replace
from types import SimpleNamespace
from typing import cast

from cheevos.core.models import GameDetail
from cheevos.core.ra_client.parse import parse_recent_unlocks
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.recent_feed import RecentFeed, RecentFeedCache
from cheevos.ui import strings
from cheevos.ui.context import AppContext
from cheevos.ui.pyui.image_frames import Frame
from cheevos.ui.pyui.primitives import Area, Button
from cheevos.ui.screens import achievement, lists


def entry():
    return parse_recent_unlocks(
        [
            {
                "AchievementID": 1,
                "GameID": 519,
                "Title": "Win the race",
                "Description": "Finish first",
                "Date": "2026-10-05 00:00:00",
                "HardcoreMode": 1,
                "BadgeName": "123",
                "Points": 5,
                "GameTitle": "An uncached game",
            }
        ]
    )[0]


def detail():
    a = replace(
        entry().achievement,
        num_awarded=50,
        num_awarded_hardcore=10,
        earned_at=1,
        earned_hardcore_at=2,
    )
    return GameDetail(519, "Game", "Console", "", 100, 80, 20, (a,))


def test_recent_list_works_offline_without_a_library_row_or_game_set(tmp_path, monkeypatch):
    data = DataCache.open(tmp_path / "data.db", "Balah")
    RecentFeedCache(data).save(RecentFeed((entry(),), "state", 1))
    ctx = SimpleNamespace(
        data=data, pending_awards=dict, screenshots=SimpleNamespace(lookup=lambda _id: None)
    )
    shown = []

    def choose(_title, items, **_kwargs):
        shown.extend(items)

    monkeypatch.setattr(lists, "choose", choose)
    lists.show_recent(cast(AppContext, ctx))
    assert len(shown) == 1
    assert shown[0].title == "Win the race"
    assert shown[0].frame is Frame.GOLD
    assert "An uncached game" in shown[0].description
    assert data.game_detail(519) is None
    data.close()


def test_feed_enrichment_preserves_the_feed_mode_and_timestamp():
    a = entry().achievement
    enriched = achievement.enrich_achievement(a, detail())
    assert enriched.num_awarded == 50
    assert enriched.earned_at == a.earned_at
    assert enriched.earned_hardcore_at == a.earned_hardcore_at


def test_rarity_is_unknown_until_the_game_statistics_arrive(monkeypatch):
    lines = []
    card = achievement._Card(
        cast(AppContext, None), entry().achievement, Area(0, 0, 640, 480), None
    )
    monkeypatch.setattr(card, "_line", lines.append)
    card.status(None, None)
    assert lines[-1] == strings.DETAIL_RARITY.format(
        casual=strings.UNKNOWN, hardcore=strings.UNKNOWN
    )
    enriched = achievement.enrich_achievement(entry().achievement, detail())
    card = achievement._Card(cast(AppContext, None), enriched, Area(0, 0, 640, 480), None)
    monkeypatch.setattr(card, "_line", lines.append)
    card.status(100, 20)
    assert lines[-1] == strings.DETAIL_RARITY.format(casual="50%", hardcore="50%")


def test_card_displays_cached_content_and_enriches_on_the_next_tick(monkeypatch):
    states, requests = [], []
    responses = iter([None, detail()])
    ctx = SimpleNamespace(
        screenshots=SimpleNamespace(lookup=lambda _id: None),
        settings=SimpleNamespace(hide_descriptions=None),
        details=SimpleNamespace(request=requests.append),
        data=SimpleNamespace(game_detail=lambda _id: next(responses)),
    )
    ticks = iter([None, Button.B])
    monkeypatch.setattr(achievement.ui, "begin", lambda *_args: Area(0, 0, 640, 480))
    monkeypatch.setattr(achievement.ui, "end", lambda: None)
    monkeypatch.setattr(achievement.ui, "wait_for", lambda _buttons: next(ticks))
    monkeypatch.setattr(achievement._Card, "header", lambda _self: None)
    monkeypatch.setattr(achievement._Card, "description", lambda _self, **_kwargs: None)

    def status(card, players, hardcore):
        states.append((players, hardcore, card._achievement.num_awarded))

    monkeypatch.setattr(achievement._Card, "status", status)
    achievement.show_achievement(
        cast(AppContext, ctx),
        entry().achievement,
        game_title="Game",
        players=None,
        players_hardcore=None,
    )
    assert requests == [519]
    assert states == [(None, None, 0), (100, 20, 50)]
