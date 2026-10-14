import sys
from types import SimpleNamespace

import pytest

from cheevos.ui.pyui import carousel, image_frames, visible_images
from cheevos.ui.pyui.carousel import FIVE_TILES, SMALL_TILES, _Painter, columns, layout
from cheevos.ui.pyui.image_frames import Frame
from cheevos.ui.pyui.primitives import Text
from cheevos.ui.pyui.views import MenuItem

# SPRUCE's bars and line heights (see test_ui_badge_grid) and its scale.
SCREENS = {
    (640, 480): ((60, 60), (33, 25), 1.0),
    (752, 560): ((70, 70), (39, 29), 105 / 90),
    (720, 720): ((67, 67), (37, 28), 101 / 90),
    (1280, 720): ((90, 90), (50, 37), 1.5),
    (480, 800): ((60, 60), (31, 25), 1.0),
}


@pytest.mark.parametrize("size", SCREENS)
def test_images_sit_between_the_top_bar_and_the_details(size):
    width, height = size
    bars, lines, scale = SCREENS[size]
    geometry = layout(width, height, bars, lines, scale)
    top = geometry.image_y - geometry.image_height // 2
    bottom = geometry.image_y + geometry.image_height // 2
    assert top >= bars[0]
    assert bottom <= geometry.details_y - geometry.gap
    assert geometry.details_y + sum(lines) <= height - bars[1]
    assert geometry.text_width == width - 2 * geometry.gap
    assert geometry.portrait is (height > width)


def test_tiles_depend_on_the_collection_and_the_screen():
    assert columns(40, portrait=False) == (FIVE_TILES, 40)
    assert columns(4, portrait=False) == (SMALL_TILES, 50)
    assert columns(40, portrait=True) == (SMALL_TILES, 60)  # images are sized by width


def entry(title, *, frame=None, path=None, description="", tail=""):
    item = MenuItem(title, description, frame=frame, tail=tail)
    asked = []

    def icon():
        asked.append(title)
        return path or f"{title}.png"

    return SimpleNamespace(
        get_value=lambda: item,
        get_icon=icon,
        asked=asked,
        image_path=None,
        image_path_selected=None,
    )


class View:
    def __init__(self, entries, selected=0, cols=5):
        self.options, self.selected, self.cols = entries, selected, cols
        self.prev_visible_options = None
        self.options_length = len(entries)

    def get_visible_options(self):
        half = self.cols // 2
        count = len(self.options)
        visible = [self.options[(self.selected + step) % count] for step in range(-half, half + 1)]
        return visible, half


def painter():
    return _Painter(layout(640, 480, (60, 60), (33, 25), 1.0))


def test_images_follow_the_selection_and_queue_the_next_ones(monkeypatch):
    dropped = []
    monkeypatch.setattr(visible_images, "new_window", lambda: dropped.append(True))
    entries = [entry(f"A{index}") for index in range(20)]
    view, drawn = View(entries, selected=10), painter()
    drawn.images(view)
    assert len(dropped) == 1
    # The five on screen, then five more each side for the next moves.
    assert sum(1 for e in entries if e.asked) == 15
    assert entries[10].image_path == entries[10].image_path_selected
    assert entries[10].image_path.startswith("A10.png#")  # the path, keyed by its entry
    assert entries[2].asked == entries[18].asked == []
    drawn.images(view)
    assert len(dropped) == 1  # the same selection keeps its downloads
    view.selected = 11
    drawn.images(view)
    assert len(dropped) == 2


def test_frames_follow_each_drawn_award(monkeypatch):
    monkeypatch.setattr(visible_images, "new_window", lambda: None)
    rendered, outlines = [], []
    display = SimpleNamespace(
        render_image=lambda *args: rendered.append(args) or (120, 100),
    )
    monkeypatch.setitem(sys.modules, "display.display", SimpleNamespace(Display=display))
    render_mode = SimpleNamespace(RenderMode=SimpleNamespace(MIDDLE_CENTER_ALIGNED="centre"))
    monkeypatch.setitem(sys.modules, "display.render_mode", render_mode)
    monkeypatch.setattr(image_frames, "fill", lambda *args: outlines.append(args))
    entries = [
        entry("Gold", frame=Frame.GOLD),
        entry("Plain"),
        entry("Holo", frame=Frame.HOLO),
        # Images not downloaded: both show the fallback, each with its own frame.
        entry("Missing", frame=Frame.GOLD, path="fallback.png"),
        entry("Missing too", path="fallback.png"),
    ]
    drawn = painter()
    drawn.images(View(entries, selected=2))
    geometry = drawn.geometry
    for made, x in zip(entries, (320, 100, 500, 600, 50), strict=True):
        drawn.image(made.image_path, x, 255.6 if x == 320 else 50, None)
    drawn.image("other.png", 200, 50, None)  # an image PyUI found itself is drawn as it is
    assert [args[0] for args in rendered] == [
        "Gold.png",
        "Plain.png",
        "Holo.png",
        "fallback.png",
        "fallback.png",
        "other.png",
    ]
    assert rendered[0] == (
        "Gold.png",
        320,
        geometry.image_y,
        "centre",
        256,
        geometry.image_height,
        None,
    )
    top = geometry.image_y - 50
    assert outlines == [
        (Frame.GOLD, (260, top, 120, 100)),
        (Frame.HOLO, (440, top, 120, 100)),
        (Frame.GOLD, (540, top, 120, 100)),
    ]


def test_details_are_fitted_once_per_selection(monkeypatch):
    fitted, drawn_text = [], []
    monkeypatch.setattr(carousel, "fit_text", lambda value, *_args: fitted.append(value) or value)
    monkeypatch.setattr(
        carousel,
        "fit_with_tail",
        lambda value, tail, *_args: fitted.append(value) or f"{value}|{tail}",
    )
    monkeypatch.setattr(carousel, "text", lambda value, *args: drawn_text.append((value, args)))
    entries = [entry("Banjo", description="Mastered", tail="9 Aug 2026"), entry("Other")]
    view, drawn = View(entries, cols=3), painter()
    drawn.details(view)
    drawn.details(view)
    assert fitted == ["Banjo", "Mastered"]
    geometry = drawn.geometry
    assert [value for value, _args in drawn_text] == ["Banjo", "Mastered|9 Aug 2026"] * 2
    assert drawn_text[0][1][:2] == (320, geometry.details_y)
    assert drawn_text[1][1][:3] == (320, geometry.details_y + geometry.title_line, Text.BODY)
    view.selected = 1
    drawn.details(view)
    assert fitted[-2:] == ["Other", ""]
