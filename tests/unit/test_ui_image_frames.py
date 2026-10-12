import sys
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest

from cheevos.core.models import Achievement, PendingAward
from cheevos.ui.context import AppContext
from cheevos.ui.pyui import generated, grid_frames, image_frames
from cheevos.ui.pyui.bar_colors import BLACK, GOLD, ZINC_300, ZINC_400
from cheevos.ui.pyui.image_frames import Frame
from cheevos.ui.pyui.primitives import Area
from cheevos.ui.pyui.views import MenuItem
from cheevos.ui.screens import achievement, rows


@pytest.fixture
def images(monkeypatch, tmp_path):
    drawn = []
    display = SimpleNamespace(render_image=lambda *args: drawn.append(args))
    monkeypatch.setitem(sys.modules, "display.display", SimpleNamespace(Display=display))
    monkeypatch.setitem(generated._state, "scratch", tmp_path)
    image_frames._image.cache_clear()
    pixels = {}
    original = generated.write

    def write(name, width, height, rgba):
        pixels[name] = width, height, rgba
        return original(name, width, height, rgba)

    monkeypatch.setattr(generated, "write", write)
    return drawn, pixels


@pytest.mark.parametrize("size", [31, 64, 79, 96, 144])
def test_gold_outline_scales_and_never_covers_artwork(images, size):
    drawn, assets = images
    left, top = 20, 65
    image_frames.draw(Frame.GOLD, (left, top, size, size))
    path, x, y = drawn[0]
    width, height, rgba = assets[path.rsplit("/", 1)[1]]
    padding = left - x
    assert top - y == padding >= 3
    assert width == height == size + 2 * padding
    for py in range(height):
        for px in range(width):
            pixel = rgba[(py * width + px) * 4 : (py * width + px + 1) * 4]
            if padding <= px < width - padding and padding <= py < height - padding:
                assert pixel == bytes(4)
            elif px in (0, width - 1) or py in (0, height - 1):
                assert pixel == bytes((*BLACK, 255))
            else:
                assert pixel == bytes((*GOLD, 255))
    image_frames.draw(Frame.GOLD, (left + 100, top + 100, size, size))
    assert drawn[1] == (path, x + 100, y + 100)
    assert image_frames._image.cache_info().hits == 1


@pytest.mark.parametrize(
    ("frame", "color", "padding"),
    [(Frame.SILVER, ZINC_300, 4), (Frame.SILVER_THIN, ZINC_400, 2)],
)
def test_award_frames_preserve_style_on_rectangular_artwork(images, frame, color, padding):
    drawn, assets = images
    image_frames.draw(frame, (20, 65, 128, 96))
    path, x, y = drawn[0]
    width, height, rgba = assets[path.rsplit("/", 1)[1]]
    assert (x, y, width, height) == (
        20 - padding,
        65 - padding,
        128 + 2 * padding,
        96 + 2 * padding,
    )
    assert rgba[width * 4 + 4 : width * 4 + 8] == bytes((*color, 255))


@pytest.mark.parametrize("size", [70, 106])
def test_focus_ring_leaves_room_for_the_gold_frame_inside(images, size):
    drawn, assets = images
    image_frames.draw(Frame.FOCUS, (100, 100, size, size))
    image_frames.draw(Frame.GOLD, (100, 100, size, size))
    (focus, x, _y), (_gold, gold_x, _) = drawn
    width, _height, rgba = assets[focus.rsplit("/", 1)[1]]
    gold = image_frames.padding(Frame.GOLD, size, size)
    assert 100 - gold_x == gold
    ring = image_frames.padding(Frame.FOCUS, size, size)
    assert 100 - x == ring > gold + 2

    def pixel(px):
        return rgba[(ring * width + px) * 4 : (ring * width + px + 1) * 4]  # the middle row

    white = bytes((255, 255, 255, 255))
    assert pixel(0) == bytes((*BLACK, 255))
    assert pixel(1) == white
    assert pixel(ring - gold - 1) == white
    assert {pixel(px) for px in range(ring - gold, ring)} == {bytes((*BLACK, 255))}
    assert pixel(ring) == bytes(4)


def test_failed_images_get_no_outline(images):
    image_frames.draw(Frame.GOLD, (20, 65, 0, 0))
    assert images == ([], {})


def badge():
    return Achievement(1, 2, "Title", "Description", 5, 10, "123", 0, None, 100, 50, None, None)


@pytest.mark.parametrize(
    ("casual", "hardcore", "pending", "expected"),
    [
        (None, None, False, None),
        (10, None, False, None),
        (None, 20, False, Frame.GOLD),
        (10, 20, False, Frame.GOLD),
        (None, None, True, None),
        (10, 20, True, Frame.GOLD),  # a stale queue entry cannot downgrade RA's hardcore unlock
    ],
)
def test_rows_and_cards_follow_ra_mode(monkeypatch, casual, hardcore, pending, expected):
    item = replace(badge(), earned_at=casual, earned_hardcore_at=hardcore)
    waiting = PendingAward(1, 2, "Game", "Title", 5, 30) if pending else None
    icons, outlines = [], []

    def resolve(_achievement, *, unlocked):
        icons.append(unlocked)
        return "badge.png"

    ctx = cast(
        AppContext,
        SimpleNamespace(
            media=SimpleNamespace(badge=resolve),
            screenshots=SimpleNamespace(lookup=lambda _id: None),
        ),
    )
    row = rows.achievement_row(ctx, item, players=100, pending=waiting)
    assert row.frame is expected
    assert callable(row.icon)
    row.icon()
    monkeypatch.setattr(achievement.ui, "image", lambda *_args: (79, 79))
    monkeypatch.setattr(achievement.ui, "wrap", lambda *_args: [])
    monkeypatch.setattr(achievement._Card, "_line", lambda *_args: None)
    monkeypatch.setattr(image_frames, "draw", lambda *args: outlines.append(args))
    achievement._Card(ctx, item, Area(0, 60, 640, 360), waiting).header()
    assert icons == [item.unlocked or pending] * 2
    assert outlines == (
        [(Frame.GOLD, (achievement.PADDING, 60 + achievement.PADDING, 79, 79))]
        if expected is Frame.GOLD
        else []
    )


def entry(frame, path="badge.png"):
    return SimpleNamespace(get_value=lambda: MenuItem("Title", frame=frame), get_icon=lambda: path)


def test_list_draws_only_visible_framed_rows_and_follows_new_images(monkeypatch):
    bounds, measured, calls = [], [], []
    version = [0]
    monkeypatch.setattr(image_frames, "image_version", lambda: version[0])
    view = SimpleNamespace(
        options=[entry(Frame.GOLD, "offscreen.png"), entry(Frame.GOLD), entry(None)],
        current_top=1,
        current_bottom=3,
        each_entry_width=640,
        get_row_geometry=lambda: (65, 88),
        _render=lambda: calls.append("rows"),
    )
    theme = SimpleNamespace(get_descriptive_list_icon_offset_x=lambda: 20)
    monkeypatch.setitem(sys.modules, "themes.theme", SimpleNamespace(Theme=theme))

    def dimensions(path):
        measured.append(path)
        return (64, 64) if path == "badge.png" else (96, 96)

    monkeypatch.setattr(image_frames, "_dimensions", dimensions)
    monkeypatch.setattr(image_frames, "draw", lambda *args: bounds.append(args))
    image_frames.attach_list(view)
    view._render()
    assert calls == ["rows"]
    assert measured == ["badge.png"]
    assert bounds == [(Frame.GOLD, (21, 70, 79, 79))]
    view._render()
    assert measured == ["badge.png"]  # unchanged frames do no image resolution or sizing
    assert bounds[-1] == bounds[0]
    # A lazy download invalidates fitted bounds even without scrolling.
    view.options[1] = entry(Frame.GOLD, "downloaded.png")
    version[0] += 1
    view._render()
    assert measured == ["badge.png", "downloaded.png"]
    assert bounds[-1] == bounds[0]
    # On-tick row replacement and scrolling each rebuild just the visible window.
    view.options = [entry(None), entry(Frame.GOLD), entry(Frame.GOLD, "next.png")]
    view._render()
    assert measured[-2:] == ["badge.png", "next.png"]
    view.current_top, view.current_bottom = 2, 3
    view._render()
    assert measured[-1] == "next.png"
    assert bounds[-1] == bounds[0]


class Grid:
    def __init__(self, size):
        self.size = size
        self.calls = []

    def _render_primary_image(self, path, x, y, **kwargs):
        self.calls.append((path, x, y, kwargs))
        return self.size

    def _render_cell(self, visible_index, *args, **kwargs):
        self._render_primary_image("badge.png", 100.5, 130, target_width=96, target_height=96)
        return visible_index


@pytest.mark.parametrize("size", [(79, 79), (96, 48), (0, 0)])
def test_grid_outlines_actual_image_before_present_and_clears_tile_state(monkeypatch, size):
    outlines = []
    monkeypatch.setattr(image_frames, "draw", lambda *args: outlines.append(args))
    view = Grid(size)
    grid_frames.attach(view)
    assert view._render_cell(visible_index=2, imageTextPair=entry(Frame.GOLD)) == 2
    width, height = size
    assert outlines == [(Frame.GOLD, (int(100.5 - width // 2), 130 - height // 2, width, height))]
    view._render_cell(3, entry(None))
    view._render_primary_image("outside.png", 0, 0)
    assert len(outlines) == 1
    assert len(view.calls) == 3
