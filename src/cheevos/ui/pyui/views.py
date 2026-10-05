"""Typed wrappers around PyUI's standard list and grid views."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
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
from cheevos.ui.pyui.visible_images import ImageDemand, VisibleImages, demanding

logger = logging.getLogger(__name__)

_CAPTION_MARGIN = 12  # keeps neighbouring grid captions apart
# Grids are designed at 640x480: 4 columns of 155 px, under the theme's 90 px list rows
# (SPRUCE). Other screens scale that like the theme scales its rows (see grid_shape).
_REFERENCE_COLUMN = 155
_REFERENCE_ROW = 90
_GRID_PAD = 10  # PyUI's GridView x_pad on each side
_TIGHTEST = 0.75  # a column may be up to a quarter narrower than designed, to fit another one
_CAPTION_GAP = 2  # between a tile's image and its caption
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


def grid_shape(width: int, usable_height: int, column: float, row: float) -> tuple[int, int]:
    """Return how many columns and rows of grid cells fit on a screen.

    Nothing in Spruce or PyUI knows a panel's DPI. Themes decide how big things are drawn at
    each resolution instead (SPRUCE ships a skin per resolution), and they keep the same
    number of list rows on every landscape screen, only bigger. Grids follow the theme: tiles
    and columns scale like its rows, and rows are as tall as its caption layout needs. So wide
    screens get more columns and square or portrait ones more rows, but tiles never shrink to
    squeeze more in.

    Args:
        width: Screen width.
        usable_height: Height between the top and bottom bars.
        column: Designed column width at this scale (a column may be a quarter narrower).
        row: Smallest row that fits a tile and its caption.

    Returns:
        ``(columns, rows)``, at least one each.
    """
    columns = (width - 2 * _GRID_PAD) / column
    tight = 1 if columns % 1 >= _TIGHTEST else 0
    return max(int(columns) + tight, 1), max(int(usable_height // row), 1)


def _screen_grid(tile: int) -> tuple[int, int, int]:
    """Shape a grid for this screen and theme (see :func:`grid_shape`).

    A row has to hold what ``GridView._render_cell`` draws in it: the image, centred and moved
    by the theme's image offset, above a caption that sits one line up from the row's bottom
    and moves by the theme's caption offset.

    Args:
        tile: Image size at 640x480.

    Returns:
        ``(columns, rows, image size)``.
    """
    from display.display import Display
    from display.font_purpose import FontPurpose
    from themes.theme import Theme

    width, height = screen_size()
    list_row = int(Display.get_image_dimensions(Theme.get_list_large_selected_bg())[1])
    scale = list_row / _REFERENCE_ROW if list_row else min(width / 640, height / 480)
    size = round(tile * scale)
    caption = int(Display.get_line_height(FontPurpose.GRID_MULTI_ROW))
    image_offset = int(Theme.get_grid_multi_row_img_y_offset(caption))
    caption_offset = int(Theme.multi_row_grid_text_y_offset())
    row = 4 * caption - 2 * caption_offset + image_offset + size + 2 * _CAPTION_GAP
    usable = int(Display.get_usable_screen_height())
    columns, rows = grid_shape(width, usable, _REFERENCE_COLUMN * scale, max(row, 1))
    return columns, rows, size


def choose(  # noqa: PLR0913 — keyword-only presentation options
    title: str,
    items: Sequence[MenuItem],
    *,
    selected: int = 0,
    buttons: frozenset[Button] = frozenset({Button.A}),
    layout: Layout = Layout.LIST,
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
        layout: List with icons and descriptions, or image grid (shaped by :func:`grid_shape`).
        tile: Grid image size at 640x480 (scaled like the theme). Without one, PyUI loads
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
    columns, rows, size = _screen_grid(tile) if layout is Layout.GRID else (0, 0, None)
    entries = _entries(items, layout, columns)
    with demanding(ImageDemand.MEASURED):  # PyUI asks every row for its image here
        view = ViewCreator.create_view(
            view_type=ViewType[layout.value],
            top_bar_text=fit_title(title),
            options=entries,
            selected_index=selected,
            cols=columns or None,
            rows=rows or None,
            grid_resized_width=size,
            grid_resized_height=size,
        )
    if layout is Layout.LIST and any(item.progress is not None for item in items):
        row_bars.attach(view)
    images = None if layout is Layout.POPUP else VisibleImages(view, entries, grid=columns > 0)
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
    images: VisibleImages | None
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
