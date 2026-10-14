import sys
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest

from cheevos.core.models import Achievement, PendingAward
from cheevos.ui.context import AppContext
from cheevos.ui.pyui import generated, image_frames
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


def test_holo_frame_runs_ras_gradient_from_top_left_to_bottom_right(images):
    drawn, assets = images
    image_frames.draw(Frame.HOLO, (20, 65, 64, 64))
    path, x, y = drawn[0]
    width, height, rgba = assets[path.rsplit("/", 1)[1]]
    padding = 20 - x
    assert padding == 65 - y == image_frames.padding(Frame.GOLD, 64, 64)  # as wide as gold

    def pixel(px, py):
        return rgba[(py * width + px) * 4 : (py * width + px + 1) * 4]

    span = width + height - 2
    assert pixel(0, 0) == bytes((*BLACK, 255))
    assert pixel(1, 1) == bytes((*image_frames.holo_color(2 / span), 255))
    assert pixel(width - 2, 1) == bytes((*image_frames.holo_color((width - 1) / span), 255))
    assert pixel(padding, padding) == bytes(4)
    assert pixel(1, 1) != pixel(width - 2, 1)  # the colours run across the frame


def opaque_pixels(asset):
    width, height, rgba = asset
    return {
        (px, py): tuple(rgba[(py * width + px) * 4 : (py * width + px) * 4 + 3])
        for py in range(height)
        for px in range(width)
        if rgba[(py * width + px) * 4 + 3] == 255
    }


@pytest.mark.parametrize("frame", list(Frame))
@pytest.mark.parametrize("size", [(64, 64), (101, 77), (224, 224)])
def test_filled_frames_paint_the_drawn_frames_pixels(images, frame, size):
    _drawn, assets = images
    width, height = size
    image_frames.draw(frame, (0, 0, width, height))
    (png,) = assets.values()
    expected = opaque_pixels(png)
    pad = image_frames.padding(frame, width, height)
    painted = {}
    for color, (x, y, rect_width, rect_height) in image_frames.strips(frame, (0, 0, width, height)):
        for py in range(y + pad, y + pad + rect_height):
            for px in range(x + pad, x + pad + rect_width):
                assert (px, py) not in painted  # every pixel is filled once
                painted[px, py] = color
    assert painted.keys() == expected.keys()  # the same band, nothing over the artwork
    for at, color in painted.items():
        # Solid bands match exactly; the holographic one in steps, close to each pixel's colour.
        tolerance = 0 if frame is not Frame.HOLO or color == BLACK else 40
        assert max(abs(a - b) for a, b in zip(color, expected[at], strict=True)) <= tolerance


def test_filled_holo_band_steps_through_the_gradient():
    def colours(size):
        rects = image_frames.strips(Frame.HOLO, (10, 10, size, size))
        return [color for color, _rect in rects if color != BLACK]

    assert len(colours(48)) == 4 * 12  # at least a dozen per side
    # The band around 224 px is 238 px across, 224 px down between the top and bottom.
    assert len(colours(224)) == 2 * 15 + 2 * 14  # one per 16 px
    assert len(colours(1000)) == 4 * 32  # however large it gets
    assert len(set(colours(224))) > 40


def test_holo_gradient_follows_ras_stops():
    assert image_frames.holo_color(0) == (255, 215, 0)  # gold
    assert image_frames.holo_color(0.4) == (255, 106, 213)  # pink, the third of six stops
    assert image_frames.holo_color(1) == (255, 215, 0)
    assert image_frames.holo_color(-1) == image_frames.holo_color(0)
    assert image_frames.holo_color(0.1) == (255, 184, 45)  # halfway from gold to orange


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
