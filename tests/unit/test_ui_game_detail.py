import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cheevos.core.models import Achievement, GameDetail
from cheevos.core.ra_client.parse import parse_game_detail
from cheevos.core.settings import Settings
from cheevos.ui import strings
from cheevos.ui.context import AppContext
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
    shown = []
    choices = iter([Button.Y, None])
    presses = iter([button])

    def choose(_title, items, **kwargs):
        shown.append((items, kwargs["layout"]))
        pressed = next(choices)
        return Choice(items[0], 0, pressed) if pressed else None

    monkeypatch.setattr(game_detail, "choose", choose)
    monkeypatch.setattr(game_detail, "_row", lambda _ctx, a, *_args: MenuItem(a.title))
    monkeypatch.setattr(
        game_detail,
        "_options",
        lambda view: replace(view, layout=layout, filter="unlocked", sort="points"),
    )
    monkeypatch.setattr(common.ui, "wait_for", lambda _buttons: next(presses))
    game_detail.show_game(ctx, detail.game_id)
    expected = Layout.GRID if layout == "grid" else Layout.LIST
    assert shown == [([MenuItem("Locked")], Layout.LIST), ([MenuItem("Locked")], expected)]
    assert message_ui == [strings.NO_ACHIEVEMENTS]


@pytest.mark.parametrize("initial_grid", [False, True])
@pytest.mark.parametrize("button", [Button.SELECT, Button.Y])
def test_layout_choice_carries_to_reopened_and_other_games(monkeypatch, initial_grid, button):
    achievement = Achievement(1, 1, "Locked", "", 5, 5, "1", 0, None, 0, 0, None, None)
    detail = GameDetail(1, "Game", "Console", "", 1, 1, 0, (achievement,))
    ctx = context(detail)
    ctx.update_settings(Settings(achievement_grid=initial_grid, game_list_details=True))
    shown = []
    choices = iter([button, None, None, None])

    def choose(_title, items, **kwargs):
        shown.append(kwargs["layout"])
        pressed = next(choices)
        return Choice(items[0], 0, pressed) if pressed else None

    monkeypatch.setattr(game_detail, "choose", choose)
    monkeypatch.setattr(game_detail, "_row", lambda _ctx, a, *_args: MenuItem(a.title))
    monkeypatch.setattr(
        game_detail,
        "_options",
        lambda view: replace(view, layout="list" if initial_grid else "grid"),
    )
    game_detail.show_game(ctx, 1)
    game_detail.show_game(ctx, 1)
    game_detail.show_game(ctx, 2)
    initial = Layout.GRID if initial_grid else Layout.LIST
    toggled = Layout.LIST if initial_grid else Layout.GRID
    assert shown == [initial, toggled, toggled, toggled]
    assert ctx.settings == Settings(achievement_grid=not initial_grid, game_list_details=True)
