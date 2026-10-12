import math
import sys
from types import SimpleNamespace

import pytest

from cheevos.ui.pyui import badge_grid, generated, image_frames
from cheevos.ui.pyui.badge_grid import Details, Geometry, Screen, layout, thumb
from cheevos.ui.pyui.image_frames import Frame
from cheevos.ui.pyui.views import MenuItem

# Theme measurements of SPRUCE at every resolution it ships (top and bottom bar, title and body
# line heights, list row / 90), and the grid each gets.
SCREENS = {
    (640, 480): ((60, 60, 33, 25, 1.0), (8, 4)),
    (720, 480): ((60, 60, 33, 25, 1.0), (9, 4)),
    (752, 560): ((70, 70, 39, 29, 105 / 90), (8, 4)),
    (720, 720): ((67, 67, 37, 28, 101 / 90), (8, 6)),
    (960, 720): ((90, 90, 50, 37, 1.5), (8, 4)),
    (1024, 768): ((96, 96, 52, 39, 1.6), (8, 4)),
    (1280, 720): ((90, 90, 50, 37, 1.5), (11, 4)),
    (480, 800): ((60, 60, 31, 25, 1.0), (6, 8)),
}


def screen(size):
    (width, height), (metrics, _shape) = size, SCREENS[size]
    return Screen(width, height, *metrics)


@pytest.mark.parametrize("size", SCREENS)
def test_layout_fills_each_screen_with_whole_rows_and_columns(size):
    shown = screen(size)
    geometry = layout(shown)
    assert (geometry.columns, geometry.rows) == SCREENS[size][1]
    # Badges keep the theme's size, and neighbouring gold frames never touch.
    assert geometry.badge == round(64 * shown.scale)
    padding = image_frames.padding(Frame.GOLD, geometry.badge, geometry.badge)
    assert geometry.pitch > geometry.badge + 2 * padding
    # The details and the scrollbar stay on screen, the scrollbar right of the tiles.
    left, right = geometry.edges
    assert 0 < left < right < geometry.bar_x
    assert geometry.bar_x + geometry.bar_width <= shown.width
    assert geometry.details_top + shown.title_line + shown.body_line <= shown.height - shown.bottom


@pytest.mark.parametrize("size", SCREENS)
def test_enlarged_selection_never_reaches_the_bars_details_or_scrollbar(size):
    shown = screen(size)
    geometry = layout(shown)
    reach = image_frames.padding(Frame.FOCUS, geometry.enlarged, geometry.enlarged)
    last = geometry.page - 1
    for index in (0, geometry.columns - 1, last - geometry.columns + 1, last):
        x, y = geometry.centre(index)
        left = x - geometry.enlarged // 2 - reach
        top = y - geometry.enlarged // 2 - reach
        right = left + geometry.enlarged + 2 * reach
        bottom = top + geometry.enlarged + 2 * reach
        assert left >= 0
        assert right <= geometry.bar_x
        assert top >= shown.top
        assert bottom <= geometry.details_top


def test_tiny_screens_still_get_one_tile():
    geometry = layout(Screen(100, 200, 60, 60, 33, 25, 1.0))
    assert (geometry.columns, geometry.rows) == (1, 1)


@pytest.mark.parametrize(
    ("first_row", "total_rows", "expected"),
    [
        (0, 4, None),  # everything fits: no scrollbar
        (0, 5, (0, 160)),
        (1, 5, (40, 160)),  # the last window: the thumb touches the bottom
        (2, 8, (50, 100)),
        (0, 63, (0, 16)),  # 500 badges in 8 columns: the thumb keeps a minimum length
        (30, 63, (93, 16)),
        (59, 63, (184, 16)),
        (2000, 63, (184, 16)),  # past the end is clamped
    ],
)
def test_thumb_spans_the_track_from_first_to_last_window(first_row, total_rows, expected):
    assert thumb(first_row, total_rows, 4, 200) == expected


def test_cells_under_points_match_the_tiles():
    geometry = layout(screen((640, 480)))
    x, y = geometry.centre(9)
    assert geometry.cell_at(x, y) == 9
    assert geometry.cell_at(geometry.left - 1, y) is None
    assert geometry.cell_at(x, geometry.details_top + 5) is None
    assert geometry.cell_at(geometry.bar_x, y) is None


@pytest.fixture
def drawn(monkeypatch, tmp_path):
    """Fake PyUI's drawing and the theme's fonts (10 px per character)."""
    calls = []

    def render_image(path, x, y, _mode=None, width=None, height=None, *_args):
        calls.append(("image", path, x, y, width, height))
        return (width or 1, height or 1) if path else (0, 0)

    display = SimpleNamespace(
        render_image=render_image,
        render_box=lambda _color, x, y, width, height: calls.append(("box", x, y, width, height)),
    )
    modes = SimpleNamespace(MIDDLE_CENTER_ALIGNED="centre", TOP_LEFT_ALIGNED="top-left")
    for name, module in {
        "display.display": SimpleNamespace(Display=display),
        "display.render_mode": SimpleNamespace(RenderMode=modes),
        "display.resize_type": SimpleNamespace(ResizeType=SimpleNamespace(ZOOM="zoom")),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(generated._state, "scratch", tmp_path)
    image_frames._image.cache_clear()
    fitted = []

    def fit_text(value, _role, width):
        fitted.append(value)
        return value if len(value) * 10 <= width else value[: max(width // 10 - 1, 0)] + "…"

    monkeypatch.setattr(badge_grid, "fit_text", fit_text)
    monkeypatch.setattr(badge_grid, "text_width", lambda value, _role: 10 * len(value))
    monkeypatch.setattr(badge_grid, "track_color", lambda: (200, 200, 200))
    monkeypatch.setattr(
        badge_grid, "text", lambda value, x, y, *_args, **_kw: calls.append(("text", value, x, y))
    )
    return calls, fitted


def entry(index, frame=None):
    item = MenuItem(f"Title {index}", value="5 pts", frame=frame, details=Details("Do it", "Tag"))
    return SimpleNamespace(
        get_value=lambda: item,
        get_image_path_ideal=lambda *_size: f"badge-{index}.png",
        get_image_path_selected_ideal=lambda *_size: f"badge-{index}.png",
    )


def grid(count, selected, *, first=0, frame=None):
    geometry = layout(screen((640, 480)))
    view = SimpleNamespace(
        options=[entry(i, frame) for i in range(count)],
        selected=selected,
        current_left=first,
        current_right=first + geometry.page,
    )
    return badge_grid._Painter(geometry), view


def test_selection_is_drawn_last_enlarged_ringed_then_framed(drawn):
    calls, _fitted = drawn
    painter, view = grid(40, 3, frame=Frame.GOLD)
    painter.draw(view)
    geometry = painter.geometry
    badges = [call for call in calls if call[0] == "image" and str(call[1]).startswith("badge")]
    # Every visible tile once; the selected one last, enlarged (it covers its neighbours).
    assert [call[1] for call in badges] == [f"badge-{i}.png" for i in range(32) if i != 3] + [
        "badge-3.png"
    ]
    assert {call[4] for call in badges[:-1]} == {geometry.badge}
    assert badges[-1][4] == geometry.enlarged
    after = calls[calls.index(badges[-1]) + 1 :]
    frames = [str(call[1]).rsplit("/", 1)[1] for call in after if call[0] == "image"]
    size = f"{geometry.enlarged}x{geometry.enlarged}"
    assert frames[:2] == [f"frame-focus-{size}.png", f"frame-gold-{size}.png"]


def test_missing_selected_image_is_still_ringed(drawn):
    calls, _fitted = drawn
    painter, view = grid(3, 1)
    view.options[1].get_image_path_selected_ideal = lambda *_size: None
    painter.draw(view)
    rings = [call for call in calls if "frame-focus" in str(call[1])]
    assert len(rings) == 1


def test_details_fit_once_per_selection(drawn):
    calls, fitted = drawn
    painter, view = grid(10, 2)
    painter.draw(view)
    painter.draw(view)
    assert fitted.count("Title 2") == 1
    texts = [call[1] for call in calls if call[0] == "text"]
    assert texts[:4] == ["Title 2", "5 pts", "Do it", "Tag"]
    view.selected = 3
    painter.draw(view)
    assert fitted.count("Title 3") == 1


def test_details_fit_the_right_hand_parts_first(monkeypatch):
    geometry = layout(screen((640, 480)))
    left, right = geometry.edges
    room = right - left
    long_title = "T" * 100
    item = MenuItem(long_title, value="10 pts", details=Details("D" * 100, "Hardcore · Win"))
    monkeypatch.setattr(badge_grid, "fit_text", lambda value, _role, width: value[: width // 10])
    monkeypatch.setattr(badge_grid, "text_width", lambda value, _role: 10 * len(value))
    title, points, description, tags = badge_grid.fitted_details(item, geometry)
    assert (points, tags) == ("10 pts", "Hardcore · Win")
    assert len(title) * 10 + geometry.text_gap + 60 <= room
    assert len(description) * 10 + geometry.text_gap + 140 <= room
    assert len(description) > len(tags)


@pytest.mark.parametrize(("count", "visible"), [(5, None), (500, 32)])
def test_scrollbar_only_for_lists_longer_than_a_screen(drawn, count, visible):
    calls, _fitted = drawn
    last_window = max(math.ceil(count / 8) - 4, 0) * 8  # PyUI's windows start on a row
    painter, view = grid(count, count - 1, first=last_window)
    painter.draw(view)
    boxes = [call for call in calls if call[0] == "box"]
    if visible is None:
        assert boxes == []
        return
    top, height = painter.geometry.track()
    (_box, _x, thumb_top, _width, length) = boxes[0]
    assert thumb_top + length == top + height  # the last window: the thumb at the bottom
    assert length == max(height * 4 // math.ceil(count / 8), 16)


def test_taps_select_tiles_only(drawn):
    painter, view = grid(35, 0, first=8)
    geometry = painter.geometry
    assert painter.touched(view, geometry.centre(0)) == 8
    assert painter.touched(view, geometry.centre(26)) == 34  # the partial last row's last tile
    assert painter.touched(view, geometry.centre(27)) is None  # an empty cell after it
    assert painter.touched(view, (geometry.left + 5, geometry.details_top + 5)) is None
    assert painter.touched(view, None) is None


def test_geometry_is_shared_by_tiles_and_scrollbar():
    geometry = Geometry(
        columns=2,
        rows=2,
        badge=64,
        enlarged=70,
        pitch=72,
        left=10,
        top=60,
        details_top=300,
        title_line=33,
        text_gap=16,
        bar_x=600,
        bar_width=4,
    )
    assert geometry.centre(3) == (10 + 72 + 36, 60 + 72 + 36)
    assert geometry.edges == (11, 10 + 72 + 71)
    assert geometry.track() == (61, 72 + 70)
