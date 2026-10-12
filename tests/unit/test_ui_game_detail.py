import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cheevos.core.models import Achievement, AchievementType, GameDetail, PendingAward
from cheevos.core.ra_client.parse import parse_game_detail
from cheevos.core.settings import DescriptionHiding, Settings
from cheevos.ui import strings
from cheevos.ui.context import AppContext
from cheevos.ui.pyui.badge_grid import Details
from cheevos.ui.pyui.primitives import Area, Button
from cheevos.ui.pyui.views import Choice, Layout, MenuItem
from cheevos.ui.screens import common, game_detail


@pytest.fixture
def message_ui(monkeypatch):
    rendered = []
    monkeypatch.setattr(common.ui, "begin", lambda *_args, **_kwargs: Area(0, 0, 640, 480))
    monkeypatch.setattr(common.ui, "wrap", lambda paragraph, *_args: [paragraph])
    monkeypatch.setattr(common.ui, "text", lambda text, *_args, **_kwargs: rendered.append(text))
    monkeypatch.setattr(common.ui, "line_height", lambda _role: 20)
    monkeypatch.setattr(common.ui, "end", lambda: None)
    return rendered


def context(detail):
    ctx = SimpleNamespace(
        data=SimpleNamespace(game_detail=lambda _id: detail, game=lambda _id: None),
        pending_awards=dict,
        settings=Settings(),
    )

    def update_settings(settings):
        ctx.settings = settings

    ctx.update_settings = update_settings
    return cast(AppContext, ctx)


def fake_views(monkeypatch, presses):
    """Replace PreparedView: record each built view's items and layout, press ``presses``."""
    built = []

    class View:
        def __init__(self, _title, items, *, selected, layout):
            self.items, self.selected, self.layout = items, selected, layout
            built.append(self)

        def show(self, **_kwargs):
            pressed = next(presses)
            return Choice(self.items[0], 0, pressed) if pressed else None

    monkeypatch.setattr(game_detail, "PreparedView", View)
    return built


@pytest.mark.parametrize("button", [Button.A, Button.B])
@pytest.mark.parametrize("cached", [True, False])
def test_empty_set_returns_after_dismissal(monkeypatch, message_ui, button, cached):
    fixture = Path(__file__).resolve().parents[1] / "fixtures/ra-no-set/game_34131.json"
    detail = parse_game_detail(json.loads(fixture.read_text(encoding="utf-8")))
    ctx = context(detail if cached else None)
    monkeypatch.setattr(game_detail, "_load", lambda _ctx, _id: detail)
    presses = iter([None, button])  # One idle tick, then dismiss; reopening exhausts the inputs.

    def wait_for(buttons):
        assert button in buttons
        return next(presses)

    monkeypatch.setattr(common.ui, "wait_for", wait_for)
    game_detail.show_game(ctx, detail.game_id)
    assert message_ui == ["This game has no achievements."] * 2


@pytest.mark.parametrize("button", [Button.A, Button.B])
@pytest.mark.parametrize("layout", ["list", "grid"])
def test_empty_filter_recovers_the_full_set(monkeypatch, message_ui, button, layout):
    achievement = Achievement(1, 1, "Locked", "", 5, 5, "1", 0, None, 0, 0, None, None)
    detail = GameDetail(1, "Game", "Console", "", 1, 1, 0, (achievement,))
    ctx = context(detail)
    built = fake_views(monkeypatch, iter([Button.Y, None]))
    presses = iter([button])
    monkeypatch.setattr(game_detail, "_row", lambda _ctx, a, *_args: MenuItem(a.title))
    monkeypatch.setattr(
        game_detail,
        "_options",
        lambda view: replace(view, layout=layout, filter="unlocked", sort="points"),
    )
    monkeypatch.setattr(common.ui, "wait_for", lambda _buttons: next(presses))
    game_detail.show_game(ctx, detail.game_id)
    expected = Layout.BADGES if layout == "grid" else Layout.LIST
    shown = [(view.items, view.layout) for view in built]
    assert shown == [([MenuItem("Locked")], Layout.LIST), ([MenuItem("Locked")], expected)]
    assert message_ui == [strings.NO_ACHIEVEMENTS]


@pytest.mark.parametrize("initial_grid", [False, True])
@pytest.mark.parametrize("button", [Button.SELECT, Button.Y])
def test_layout_choice_carries_to_reopened_and_other_games(monkeypatch, initial_grid, button):
    achievement = Achievement(1, 1, "Locked", "", 5, 5, "1", 0, None, 0, 0, None, None)
    detail = GameDetail(1, "Game", "Console", "", 1, 1, 0, (achievement,))
    ctx = context(detail)
    ctx.update_settings(Settings(achievement_grid=initial_grid, game_list_details=True))
    built = fake_views(monkeypatch, iter([button, None, None, None]))
    monkeypatch.setattr(game_detail, "_row", lambda _ctx, a, *_args: MenuItem(a.title))
    monkeypatch.setattr(
        game_detail,
        "_options",
        lambda view: replace(view, layout="list" if initial_grid else "grid"),
    )
    game_detail.show_game(ctx, 1)
    game_detail.show_game(ctx, 1)
    game_detail.show_game(ctx, 2)
    initial = Layout.BADGES if initial_grid else Layout.LIST
    toggled = Layout.LIST if initial_grid else Layout.BADGES
    assert [view.layout for view in built] == [initial, toggled, toggled, toggled]
    assert ctx.settings == Settings(achievement_grid=not initial_grid, game_list_details=True)


def test_card_and_unchanged_options_return_to_the_same_view(monkeypatch):
    # Back from a card, or from a Y menu left as it was, the view is shown again (same page);
    # a new filter rebuilds it from the top.
    achievements = tuple(
        Achievement(i, 1, f"A{i}", "", 5, 5, str(i), 0, None, 0, 0, None, None) for i in (1, 2)
    )
    detail = GameDetail(1, "Game", "Console", "", 1, 1, 0, achievements)
    ctx = context(detail)
    built = fake_views(monkeypatch, iter([Button.A, Button.Y, Button.Y, Button.A, None]))
    monkeypatch.setattr(game_detail, "_row", lambda _ctx, a, *_args: MenuItem(a.title))
    sorts = iter([None, "points"])  # Y left unchanged, then a new sort

    def options(view):
        sort = next(sorts)
        return replace(view, sort=sort) if sort else view

    monkeypatch.setattr(game_detail, "_options", options)
    cards = []
    monkeypatch.setattr(game_detail, "show_achievement", lambda _ctx, a, **_kw: cards.append(a))
    game_detail.show_game(ctx, 1)
    assert len(built) == 2
    assert built[1].selected == 0
    assert cards == [achievements[0], achievements[0]]


def achievement_with(**changes):
    base = Achievement(1, 1, "Title", "How to unlock", 5, 5, "1", 0, None, 0, 0, None, None)
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("changes", "pending", "tags"),
    [
        ({"earned_at": 1, "earned_hardcore_at": 1}, False, "Hardcore"),
        ({"earned_at": 1}, False, "Casual"),
        ({}, True, "Pending sync"),
        ({}, False, "Locked"),
        ({"type": AchievementType.MISSABLE}, False, "Locked · Missable"),
        ({"earned_at": 1, "type": AchievementType.WIN_CONDITION}, False, "Casual · Win"),
    ],
)
def test_badge_details_name_the_unlock_mode_and_type(changes, pending, tags):
    achievement = achievement_with(**changes)
    waiting = PendingAward(1, 1, "Game", "Title", 5, 30) if pending else None
    details = game_detail._details(context(None), achievement, waiting)
    assert details == Details("How to unlock", tags)


@pytest.mark.parametrize(
    ("hiding", "changes", "pending", "hidden"),
    [
        (DescriptionHiding.OFF, {"type": AchievementType.PROGRESSION}, False, False),
        (DescriptionHiding.STORY, {"type": AchievementType.PROGRESSION}, False, True),
        (DescriptionHiding.STORY, {"type": AchievementType.MISSABLE}, False, False),
        (DescriptionHiding.ALL, {}, False, True),
        (DescriptionHiding.ALL, {}, True, False),  # unlocked on the device
        (DescriptionHiding.ALL, {"earned_at": 1}, False, False),
    ],
)
def test_badge_details_follow_the_spoiler_setting(hiding, changes, pending, hidden):
    ctx = context(None)
    ctx.update_settings(Settings(hide_descriptions=hiding))
    waiting = PendingAward(1, 1, "Game", "Title", 5, 30) if pending else None
    details = game_detail._details(ctx, achievement_with(**changes), waiting)
    assert details.text == (strings.HIDDEN_DESCRIPTION if hidden else "How to unlock")
