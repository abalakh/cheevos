"""The game library: progress bars or details (Select), with filter and sort options (Y)."""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from cheevos.core.models import AwardKind, GameProgress
from cheevos.core.sync.planner import activity
from cheevos.ui import strings
from cheevos.ui.context import AppContext
from cheevos.ui.pyui.primitives import Button
from cheevos.ui.pyui.views import choose
from cheevos.ui.screens.common import busy, message, pick
from cheevos.ui.screens.game_detail import show_game
from cheevos.ui.screens.rows import game_row

logger = logging.getLogger(__name__)

FINISHED = frozenset(AwardKind)
# Above this many rows, preparing the list takes a noticeable moment on a Miyoo Mini
# (about 1.5 s for 1,000 games), so show a loading frame first.
LOADING_FRAME_ROWS = 300


@dataclass(frozen=True, slots=True)
class _View:
    """Filter and sort choices.

    Attributes:
        filter: Key of ``strings.GAME_FILTERS``.
        sort: Key of ``strings.GAME_SORTS``.
    """

    filter: str = "all"
    sort: str = "recent"


def _filters(ctx: AppContext) -> dict[str, Callable[[GameProgress], bool]]:
    """Build the filter predicates (the on-device one needs the context).

    Args:
        ctx: App context.

    Returns:
        Filter key to predicate.
    """
    return {
        "all": lambda _g: True,
        "device": lambda g: g.game_id in ctx.on_device_ids(),
        "progress": lambda g: 0 < g.earned < g.max_possible and g.highest_award is None,
        "finished": lambda g: g.highest_award in FINISHED,
        "unstarted": lambda g: g.earned == 0,
    }


def _completion(game: GameProgress) -> float:
    """Return a game's completion as a fraction.

    Args:
        game: The game.

    Returns:
        Earned over total (0 for games without achievements).
    """
    return game.earned / game.max_possible if game.max_possible else 0.0


def _sorted(games: list[GameProgress], sort: str) -> list[GameProgress]:
    """Order games for display.

    Args:
        games: Filtered games (already in activity order).
        sort: Key of ``strings.GAME_SORTS``.

    Returns:
        A new, ordered list.
    """
    if sort == "title":
        return sorted(games, key=lambda g: g.title.lower())
    if sort == "console":
        return sorted(games, key=lambda g: (g.console_name.lower(), g.title.lower()))
    if sort == "completion":
        return sorted(games, key=lambda g: (-_completion(g), -activity(g)))
    return list(games)


def show_games(ctx: AppContext) -> None:
    """Show the library until B.

    Args:
        ctx: App context.
    """
    view = _View()
    selected = 0
    filters = _filters(ctx)
    while True:
        games = _sorted([g for g in ctx.data.games() if filters[view.filter](g)], view.sort)
        if not games:
            message(strings.GAMES, [strings.NO_GAMES])
            if view == _View():
                return
            view = _View()
            continue
        title = f"{strings.GAMES} · {strings.GAME_FILTERS[view.filter]}"
        if len(games) > LOADING_FRAME_ROWS:
            busy(title, strings.LOADING)
        started = time.monotonic()
        details = ctx.settings.game_list_details
        pending = ctx.pending_by_game()
        items = [
            game_row(ctx, game, details=details, pending=pending.get(game.game_id, 0))
            for game in games
        ]
        logger.info(
            "Built %d game rows in %.0f ms", len(items), (time.monotonic() - started) * 1000
        )
        buttons = frozenset({Button.A, Button.Y, Button.SELECT})
        toggle = strings.HINT_PROGRESS if details else strings.HINT_DETAILS
        hints = [(Button.Y, strings.HINT_FILTER), (Button.SELECT, toggle)]
        choice = choose(title, items, selected=selected, buttons=buttons, hints=hints)
        if choice is None:
            return
        if choice.button is Button.Y:
            view = _options(view)
            selected = 0
            continue
        selected = choice.index
        if choice.button is Button.SELECT:  # progress bars <-> console and last activity
            ctx.update_settings(dataclasses.replace(ctx.settings, game_list_details=not details))
            continue
        show_game(ctx, games[choice.index].game_id)


def _options(view: _View) -> _View:
    """Let the user change the filter or sort through popups.

    Args:
        view: Current choices.

    Returns:
        The updated choices.
    """
    menu = {
        "filter": strings.FILTER.format(value=strings.GAME_FILTERS[view.filter]),
        "sort": strings.SORT.format(value=strings.GAME_SORTS[view.sort]),
    }
    which = pick(strings.GAMES, menu, "filter")
    if which == "filter":
        chosen = pick(strings.GAMES, strings.GAME_FILTERS, view.filter)
        return replace(view, filter=chosen) if chosen else view
    if which == "sort":
        chosen = pick(strings.GAMES, strings.GAME_SORTS, view.sort)
        return replace(view, sort=chosen) if chosen else view
    return view
