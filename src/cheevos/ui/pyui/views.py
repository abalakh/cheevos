"""Typed wrappers around PyUI's standard list and grid views."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from cheevos.core.models import AwardKind
from cheevos.ui.pyui import grid_frames, row_bars, status_bar
from cheevos.ui.pyui.primitives import (
    Button,
    Text,
    displayable,
    fit_text,
    fit_title,
    list_title_width,
    screen_size,
)
from cheevos.ui.pyui.row_bars import Progress
from cheevos.ui.pyui.status_bar import Hint

logger = logging.getLogger(__name__)

_CAPTION_MARGIN = 12  # keeps neighbouring grid captions apart
_REFERENCE_HEIGHT = 480  # grid tile sizes are given for 480-line screens
BADGE_TILE = 64  # RA achievement badges are 64x64
ICON_TILE = 96  # RA game icons are 96x96
# Log list preparation times for big lists or slow builds (performance diagnostics on devices).
_SLOW_LIST_ROWS = 100
_SLOW_LIST_MS = 200

# A lazily resolved image: called when the row is drawn, so only visible rows pay for it and
# an image that arrives in the background shows up on the next frame.
IconSource = Path | Callable[[], Path | None] | None


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One row of a list, or one tile of a grid.

    Attributes:
        title: Primary text.
        description: Secondary line under the title (lists only; may be empty).
        icon: Image left of the text (lists) or the tile image (grids): a path, or a callable
            returning one when the row is drawn.
        value: Right-aligned text, e.g. ``"2/138"`` (lists only; may be empty).
        key: Caller-defined identifier, returned unchanged on selection.
        progress: A progress bar shown instead of the description (lists only).
        frame: An award frame around the tile's image (grids only; RA's colours).
    """

    title: str
    description: str = ""
    icon: IconSource = None
    value: str = ""
    key: str = ""
    progress: Progress | None = None
    frame: AwardKind | None = None


@dataclass(frozen=True, slots=True)
class Choice:
    """The user's pick.

    Attributes:
        item: Selected item.
        index: Its position in the list.
        button: Button that confirmed it (A, or one of the extra buttons).
    """

    item: MenuItem
    index: int
    button: Button


class Layout(Enum):
    """Supported PyUI view types."""

    LIST = "ICON_AND_DESC"
    GRID = "GRID"
    POPUP = "POPUP"  # small menu over the current screen (options, filters)


# Called on every input timeout (~12x/s). Returning items replaces the list in place.
TickHandler = Callable[[], Sequence[MenuItem] | None]


def _lazy(source: Callable[[], Path | None]) -> Callable[[object], str | None]:
    """Adapt a lazy icon source to PyUI's searcher signature (it passes the entry value).

    Args:
        source: Callable returning the image path.

    Returns:
        A PyUI icon/image searcher.
    """

    def search(_value: object) -> str | None:
        """Resolve the image when PyUI draws the entry."""
        path = source()
        return str(path) if path else None

    return search


def _entry(item: MenuItem, *, fit: bool, caption: int = 0) -> Any:  # noqa: ANN401 — PyUI
    """Convert one item into a PyUI ``GridOrListEntry``.

    Args:
        item: Row or tile.
        fit: Shorten the title so it never runs into the right-aligned value (lists).
        caption: Width a grid tile's caption must fit (PyUI doesn't shorten captions).

    Returns:
        The PyUI entry, carrying the item as its value.
    """
    from views.grid_or_list_entry import GridOrListEntry

    icon = item.icon
    static = str(icon) if isinstance(icon, Path) else None
    searcher = None if icon is None or isinstance(icon, Path) else _lazy(icon)
    if fit:
        title = fit_text(item.title, Text.TITLE, list_title_width(item.value))
        description = fit_text(item.description, Text.BODY, list_title_width(""))
    elif caption:
        title = fit_text(item.title, Text.GRID, caption)
        description = ""
    else:
        title = displayable(item.title, Text.TITLE)
        description = displayable(item.description, Text.BODY)
    if item.progress is not None:
        description = ""  # keeps the two-line row; the bar is drawn in its place
    return GridOrListEntry(
        primary_text=title,
        value_text=item.value or None,
        description=None if not description and item.progress is None else description,
        icon=static,
        image_path=static,
        icon_searcher=searcher,
        image_path_searcher=searcher,
        image_path_selected_searcher=searcher,
        value=item,
    )


def _entries(
    items: Sequence[MenuItem], layout: Layout = Layout.LIST, columns: int = 0
) -> list[Any]:
    """Convert items into PyUI entries.

    Args:
        items: Rows or tiles.
        layout: Target view; list titles are fitted next to their values.
        columns: Grid columns (grid captions are fitted to a column).

    Returns:
        PyUI entries in the same order.
    """
    caption = 0
    if layout is Layout.GRID and columns:
        width, _ = screen_size()
        caption = width // columns - _CAPTION_MARGIN
    return [_entry(item, fit=layout is Layout.LIST, caption=caption) for item in items]


class ImageDemand(Enum):
    """How much the screen needs the image it's asking for (``MediaResolver.resolve``)."""

    SHOWN = "shown"  # drawn now: download it ahead of anything waiting
    NEXT = "next"  # the next page: download it after what's on screen
    MEASURED = "measured"  # PyUI scanning rows it won't draw yet: don't download


@dataclass(slots=True)
class _ImageHooks:
    """How the views reach the app's images (set with :func:`track_images`).

    Attributes:
        version: Changes whenever a new image becomes available.
        new_window: Drops downloads waiting for rows that scrolled away.
        demand: What image requests are for right now (UI thread only).
    """

    version: Callable[[], int] = lambda: 0
    new_window: Callable[[], None] = lambda: None
    demand: ImageDemand = ImageDemand.SHOWN


_hooks = _ImageHooks()


def track_images(version: Callable[[], int], new_window: Callable[[], None]) -> None:
    """Connect the views to the app's images.

    Args:
        version: Returns a number that changes whenever a new image becomes available
            (``MediaResolver.version``).
        new_window: Drops downloads queued for rows no longer shown
            (``MediaResolver.new_window``).
    """
    _hooks.version = version
    _hooks.new_window = new_window


def image_demand() -> ImageDemand:
    """Return what image requests are for right now (passed to ``MediaResolver``)."""
    return _hooks.demand


@contextlib.contextmanager
def _demanding(demand: ImageDemand) -> Iterator[None]:
    """Mark the image requests made during the block.

    Args:
        demand: What they are for.

    Yields:
        Nothing.
    """
    previous, _hooks.demand = _hooks.demand, demand
    try:
        yield
    finally:
        _hooks.demand = previous


class _Images:
    """Keeps a view's image downloads on the rows it shows (.agents/sync-and-storage.md).

    PyUI asks every row for its image when it builds a list (to pick the selection style), so
    opening a list used to queue downloads for all its rows, top to bottom, and a jump to the
    end waited for everything above. Now ``choose`` marks that scan ``MEASURED`` (no
    downloads), and after each frame this:

    - when the visible window moved, drops the downloads queued for the old one, asks for the
      visible rows' images again (ahead of anything else) and queues the next page in the
      scroll direction behind them;
    - lets a grid's visible tiles ask again when images arrive: PyUI keeps a tile's image path
      from the first time it draws the tile (``GridOrListEntry`` drops its searcher).

    Args:
        view: The list or grid; its ``_render`` is wrapped.
        entries: Its entries.
        grid: The view is a grid.
    """

    def __init__(self, view: Any, entries: Sequence[Any], *, grid: bool) -> None:  # noqa: ANN401
        self._view = view
        self._grid = grid
        self.reset(entries)
        original = view._render

        def render(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — PyUI's signature
            """Draw the frame, then follow the visible rows."""
            result = original(*args, **kwargs)
            try:
                self._follow()
            except Exception:  # downloads are an optimisation; never take the view down
                logger.exception("Could not queue images for the visible rows")
            return result

        view._render = render

    def reset(self, entries: Sequence[Any]) -> None:
        """Remember new entries' searchers (before PyUI drops them).

        Args:
            entries: The view's new entries.
        """
        self._searchers = [entry.icon_searcher for entry in entries]
        self._shown: range | None = None
        self._version = _hooks.version()

    def _visible(self) -> range:
        """Return the indices on screen."""
        view, count = self._view, len(self._searchers)
        if self._grid:
            start, stop = int(view.current_left), int(view.current_right)
        else:
            start, stop = int(view.current_top), int(view.current_bottom)
        return range(max(start, 0), min(stop, count))

    def _follow(self) -> None:
        """Re-target downloads when the window moved; refresh grid tiles when images arrived."""
        shown = self._visible()
        if shown != self._shown:
            forward = self._shown is None or shown.start >= self._shown.start
            self._shown = shown
            _hooks.new_window()
            self._ask(shown)
            with _demanding(ImageDemand.NEXT):
                self._ask(_next_page(shown, len(self._searchers), forward=forward))
        if self._grid:
            self._rearm(shown)

    def _ask(self, rows: range) -> None:
        """Ask the rows for their images (missing ones get requested).

        Args:
            rows: Entry indices.
        """
        for index in rows:
            searcher = self._searchers[index]
            if searcher is not None:
                searcher(None)

    def _rearm(self, shown: range) -> None:
        """Let visible grid tiles ask for their image again if images arrived since last time.

        Args:
            shown: Indices on screen.
        """
        version = _hooks.version()
        if version == self._version:
            return
        self._version = version
        for index in shown:
            searcher = self._searchers[index]
            if searcher is None:
                continue
            entry = self._view.options[index]
            entry.image_path = None
            entry.image_path_searcher = searcher
            entry.image_path_selected = None
            entry.image_path_selected_searcher = searcher


def _next_page(shown: range, count: int, *, forward: bool) -> range:
    """Return the page after ``shown`` in the scroll direction (the other way at an end).

    Args:
        shown: Indices on screen.
        count: Number of entries.
        forward: The last move went down the list.

    Returns:
        Up to one screenful of indices.
    """
    size = len(shown)
    below = range(shown.stop, min(shown.stop + size, count))
    above = range(max(shown.start - size, 0), shown.start)
    first, second = (below, above) if forward else (above, below)
    return first or second


def choose(  # noqa: PLR0913 — keyword-only presentation options
    title: str,
    items: Sequence[MenuItem],
    *,
    selected: int = 0,
    buttons: frozenset[Button] = frozenset({Button.A}),
    layout: Layout = Layout.LIST,
    grid: tuple[int, int] = (4, 2),
    tile: int = BADGE_TILE,
    on_tick: TickHandler | None = None,
    full_status: bool = False,
    hints: Sequence[Hint] = (),
) -> Choice | None:
    """Show a themed list or grid and wait for a choice.

    Start runs the global Start action (sync) and keeps the view open, unless ``buttons``
    claims it. Popups ignore it.

    Args:
        title: Top-bar text.
        items: Rows (list) or tiles (grid), in order. Must not be empty.
        selected: Initially highlighted index.
        buttons: Buttons that confirm a choice (B always backs out).
        layout: List with icons and descriptions, or image grid.
        grid: ``(columns, rows)`` for the grid layout.
        tile: Grid image size at 480 lines (scaled to the screen). Without one, PyUI loads
            every tile's image when the grid opens to find the tallest.
        on_tick: Called on each input timeout; returned items replace the current ones.
        full_status: Show the detailed sync status in the bottom bar (home, settings), not
            only progress.
        hints: Button hints for the bottom bar, e.g. ``[(Button.SELECT, "Details")]``.

    Returns:
        The choice, or ``None`` when B is pressed.
    """
    from controller.controller_inputs import ControllerInput
    from views.view_creator import ViewCreator
    from views.view_type import ViewType

    accepted = [ControllerInput[button.value] for button in buttons] + [ControllerInput.B]
    global_start = layout is not Layout.POPUP and Button.START not in buttons
    if global_start:
        accepted.append(ControllerInput.START)
    started = time.monotonic()
    columns = grid[0] if layout is Layout.GRID else 0
    entries = _entries(items, layout, columns)
    size = round(tile * screen_size()[1] / _REFERENCE_HEIGHT) if layout is Layout.GRID else None
    with _demanding(ImageDemand.MEASURED):  # PyUI asks every row for its image here
        view = ViewCreator.create_view(
            view_type=ViewType[layout.value],
            top_bar_text=fit_title(title),
            options=entries,
            selected_index=selected,
            cols=grid[0] if layout is Layout.GRID else None,
            rows=grid[1] if layout is Layout.GRID else None,
            grid_resized_width=size,
            grid_resized_height=size,
        )
    if layout is Layout.LIST and any(item.progress is not None for item in items):
        row_bars.attach(view)
    images = None if layout is Layout.POPUP else _Images(view, entries, grid=columns > 0)
    if layout is Layout.GRID and any(item.frame is not None for item in items):
        grid_frames.attach(view)
    elapsed_ms = (time.monotonic() - started) * 1000
    if len(entries) > _SLOW_LIST_ROWS or elapsed_ms > _SLOW_LIST_MS:
        logger.info("Prepared %d rows in %.0f ms", len(entries), elapsed_ms)
    try:
        with status_bar.detailed(full_status), status_bar.hints(hints):
            loop = _Loop(on_tick, layout, columns, images, global_start=global_start)
            return _select(view, accepted, loop)
    finally:
        # Popups freeze the frame underneath as their backdrop until told they're done;
        # without this, every later screen is drawn over that frozen frame.
        finished = getattr(view, "view_finished", None)
        if finished is not None:
            finished()


@dataclass(frozen=True, slots=True)
class _Loop:
    """How a selection loop treats ticks and Start.

    Attributes:
        on_tick: Called on each input timeout; returned items replace the current ones.
        layout: View layout (for converting refreshed items).
        columns: Grid columns (for fitting refreshed captions).
        images: Keeps image downloads on the visible rows (not for popups).
        global_start: Start runs the global Start action instead of ending the loop.
    """

    on_tick: TickHandler | None
    layout: Layout
    columns: int
    images: _Images | None
    global_start: bool


def _select(view: Any, accepted: list[Any], loop: _Loop) -> Choice | None:  # noqa: ANN401
    """Run PyUI's selection loop until a confirming button or B.

    Args:
        view: PyUI view.
        accepted: Controller inputs that end the loop (B included).
        loop: Tick and Start handling.

    Returns:
        The choice, or ``None`` when B is pressed.
    """
    from controller.controller_inputs import ControllerInput

    while True:
        selection = view.get_selection(accepted)
        # PyUI returns a Selection with no input after a timeout or a cursor move.
        if selection is None or selection.get_input() is None:
            if loop.on_tick is not None and (updated := loop.on_tick()) is not None:
                entries = _entries(updated, loop.layout, loop.columns)
                view.set_options(entries)
                if loop.images is not None:
                    loop.images.reset(entries)
            continue
        if selection.get_input() == ControllerInput.B:
            return None
        if loop.global_start and selection.get_input() == ControllerInput.START:
            status_bar.press_start()
            continue
        item = selection.get_selection().get_value()
        return Choice(item, selection.get_index(), Button(selection.get_input().name))
