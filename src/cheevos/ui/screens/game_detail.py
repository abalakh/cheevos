"""A game's achievements as a list or badge grid (Select), with filter and sort options (Y)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from cheevos.core.models import Achievement, AchievementType, GameDetail
from cheevos.ui import strings
from cheevos.ui.context import AppContext
from cheevos.ui.pyui.primitives import Button
from cheevos.ui.pyui.title_bar import Title
from cheevos.ui.pyui.views import Layout, MenuItem, choose
from cheevos.ui.screens.achievement import show_achievement
from cheevos.ui.screens.common import message, pick
from cheevos.ui.screens.rows import achievement_row, rarity

_KEY_TYPES = (AchievementType.PROGRESSION, AchievementType.WIN_CONDITION)

FILTERS: dict[str, Callable[[Achievement], bool]] = {
    "all": lambda _a: True,
    "locked": lambda a: not a.unlocked,
    "unlocked": lambda a: a.unlocked,
    "missable": lambda a: a.type is AchievementType.MISSABLE,
    "key": lambda a: a.type in _KEY_TYPES,
}


@dataclass(frozen=True, slots=True)
class _View:
    """Presentation choices for the achievement list.

    Attributes:
        layout: ``"list"`` or ``"grid"``.
        filter: Key of :data:`FILTERS`.
        sort: Key of ``strings.ACH_SORTS``.
    """

    layout: str = "list"
    filter: str = "all"
    sort: str = "order"


def _sorted(achievements: list[Achievement], sort: str, players: int) -> list[Achievement]:
    """Order achievements for display.

    Args:
        achievements: Filtered achievements in RA's order.
        sort: Key of ``strings.ACH_SORTS``.
        players: Distinct players, for rarity.

    Returns:
        A new, ordered list.
    """
    if sort == "unlocked":
        return sorted(achievements, key=lambda a: not a.unlocked)
    if sort == "locked":
        return sorted(achievements, key=lambda a: a.unlocked)
    if sort == "points":
        return sorted(achievements, key=lambda a: -a.points)
    if sort == "rarity":
        return sorted(achievements, key=lambda a: rarity(a, players))
    return list(achievements)


def show_game(ctx: AppContext, game_id: int) -> None:
    """Show a game's achievements until B.

    Args:
        ctx: App context.
        game_id: RA game ID.
    """
    detail = ctx.data.game_detail(game_id)
    game = ctx.data.game(game_id)
    if detail is None:
        message(game.title if game else strings.GAMES, [strings.NO_DETAILS])
        return
    pending = ctx.pending_awards()
    earned = sum(1 for a in detail.achievements if a.unlocked)
    count = f"{earned}/{len(detail.achievements)}"
    title = Title(detail.title, count, game.highest_award if game else None)
    view = _View()
    selected = 0
    while True:
        shown = _sorted(
            [a for a in detail.achievements if FILTERS[view.filter](a)],
            view.sort,
            detail.num_distinct_players,
        )
        if not shown:
            message(detail.title, [strings.NO_ACHIEVEMENTS])
            view = _View(layout=view.layout)
            continue
        items = [_row(ctx, a, detail, pending) for a in shown]
        layout = Layout.GRID if view.layout == "grid" else Layout.LIST
        buttons = frozenset({Button.A, Button.Y, Button.SELECT})
        toggle = strings.HINT_LIST if view.layout == "grid" else strings.HINT_GRID
        hints = [(Button.Y, strings.HINT_FILTER), (Button.SELECT, toggle)]
        choice = choose(
            title, items, selected=selected, buttons=buttons, layout=layout, hints=hints
        )
        if choice is None:
            return
        if choice.button is Button.Y:
            view = _options(view)
            selected = 0
            continue
        selected = choice.index
        if choice.button is Button.SELECT:  # list <-> grid, like PyUI's game lists
            view = replace(view, layout="list" if view.layout == "grid" else "grid")
            continue
        achievement = shown[choice.index]
        show_achievement(
            ctx,
            achievement,
            game_title=detail.title,
            players=detail.num_distinct_players,
            players_hardcore=detail.num_players_hardcore,
            pending=pending.get(achievement.achievement_id),
        )


def _row(ctx: AppContext, achievement: Achievement, detail: GameDetail, pending: dict) -> MenuItem:
    """Build one achievement row for this game.

    Args:
        ctx: App context.
        achievement: The achievement.
        detail: Its game.
        pending: Pending unlocks by achievement ID.

    Returns:
        The row.
    """
    return achievement_row(
        ctx,
        achievement,
        players=detail.num_distinct_players,
        pending=pending.get(achievement.achievement_id),
    )


def _options(view: _View) -> _View:
    """Let the user change the view, filter or sort through popups.

    Args:
        view: Current choices.

    Returns:
        The updated choices (unchanged if the user backed out).
    """
    menu = {
        "layout": strings.VIEW.format(value=strings.VIEWS[view.layout]),
        "filter": strings.FILTER.format(value=strings.ACH_FILTERS[view.filter]),
        "sort": strings.SORT.format(value=strings.ACH_SORTS[view.sort]),
    }
    which = pick(strings.APP_TITLE, menu, "layout")
    if which == "layout":
        layout = pick(strings.APP_TITLE, strings.VIEWS, view.layout)
        return replace(view, layout=layout) if layout else view
    if which == "filter":
        chosen = pick(strings.APP_TITLE, strings.ACH_FILTERS, view.filter)
        return replace(view, filter=chosen) if chosen else view
    if which == "sort":
        chosen = pick(strings.APP_TITLE, strings.ACH_SORTS, view.sort)
        return replace(view, sort=chosen) if chosen else view
    return view
