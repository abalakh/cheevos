import sys
from types import SimpleNamespace

import pytest

from cheevos.core.models import AwardKind
from cheevos.ui.pyui import row_bars
from cheevos.ui.pyui.bar_colors import palette
from cheevos.ui.pyui.row_bars import Progress


def entry(progress):
    return SimpleNamespace(
        get_value=lambda: SimpleNamespace(progress=progress),
        get_value_text=lambda: "106/106",
    )


@pytest.fixture
def drawing(monkeypatch):
    images, text, fills = [], [], []
    device = SimpleNamespace(screen_width=lambda: 640)
    theme = SimpleNamespace(
        get_descriptive_list_text_from_icon_offset=lambda: 10,
        get_descriptive_list_icon_offset_x=lambda: 20,
        get_descriptive_list_text_offset_y=lambda: 12,
        get_use_text_for_line_height=lambda: True,
        text_color=lambda _font: (240, 230, 200),
        text_color_selected=lambda _font: (255, 255, 255),
    )
    display = SimpleNamespace(
        get_text_dimensions=lambda _font, _text: (12, 24),
        render_image=lambda *args: images.append(args),
        render_text=lambda *args: text.append(args),
    )
    font = SimpleNamespace(DESCRIPTIVE_LIST_DESCRIPTION="body", DESCRIPTIVE_LIST_TITLE="title")
    mode = SimpleNamespace(MIDDLE_CENTER_ALIGNED="centre", MIDDLE_LEFT_ALIGNED="left")
    modules = {
        "devices.device": SimpleNamespace(Device=SimpleNamespace(get_device=lambda: device)),
        "display.display": SimpleNamespace(Display=display),
        "display.font_purpose": SimpleNamespace(FontPurpose=font),
        "display.render_mode": SimpleNamespace(RenderMode=mode),
        "themes.theme": SimpleNamespace(Theme=theme),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    colors = (palette((43, 43, 43), (240, 230, 200)), palette((73, 66, 62), (255, 255, 255)))
    monkeypatch.setattr(row_bars, "_palettes", lambda _view: colors)
    monkeypatch.setattr(row_bars, "text_width", lambda value, _role: len(value) * 12)
    monkeypatch.setattr(row_bars, "_fill", lambda paint, rect: fills.append((paint, rect)))
    return SimpleNamespace(
        device=device, theme=theme, display=display, images=images, text=text, fills=fills
    )


@pytest.mark.parametrize(("width", "line"), [(640, 24), (752, 28), (1280, 36)])
def test_layout_keeps_one_endpoint_and_room_for_awards_and_percentages(drawing, width, line):
    drawing.device.screen_width = lambda: width
    drawing.display.get_text_dimensions = lambda _font, _text: (12, line)
    view = SimpleNamespace(each_entry_width=width, contains_any_icons=True)
    ordinary = [entry(Progress(0.3, 0.35, "65%")), entry(Progress(0, 0, "0%"))]
    awards = [entry(Progress(1, 0, "100%", AwardKind.MASTERED)), *ordinary]
    layout = row_bars._layout(view, awards)
    assert layout.award_x == layout.bar_x + layout.bar_width
    assert line * 0.8 <= layout.award_size <= line
    assert layout.award_x + layout.award_size / 2 + 10 <= layout.label_right - 48
    # Even a list without any awards leaves the same room at the endpoint.
    no_awards = [entry(Progress(1, 0, "100%")), *ordinary]
    assert row_bars._layout(view, no_awards).bar_width == layout.bar_width


def test_awards_overlay_the_track_and_use_the_selected_row_background(drawing, monkeypatch):
    options = [entry(Progress(1, 0, "100%", AwardKind.MASTERED))]
    options += [entry(Progress(0.4, 0.6, "100%", AwardKind.COMPLETED))]
    options += [entry(Progress(0.45, 0, "45%", AwardKind.BEATEN_HARDCORE))]
    options += [entry(Progress(0.2, 0.3, "50%", AwardKind.BEATEN_SOFTCORE))]
    view = SimpleNamespace(
        options=options,
        current_top=0,
        current_bottom=4,
        selected=1,
        each_entry_width=640,
        contains_any_icons=True,
        get_row_geometry=lambda: (65, 72),
    )
    cache = {}
    row_bars._draw(view, cache)
    layout = cache[id(options)]
    assert len(drawing.images) == 4
    # Hollow awards get an extra background strip, entirely inside the circle.
    tracks = [drawing.fills[index][1] for index in (0, 3, 7, 10)]
    for row, image in enumerate(drawing.images):
        track = tracks[row]
        assert image[1] == track[0] + track[2] == layout.award_x
        assert image[2] == track[1] + track[3] // 2
        assert image[3] == "centre"
        assert image[4] == image[5]  # Scaling keeps the circles round.
    masks = [drawing.fills[index] for index in (6, 13)]
    assert [paint.color for paint, _rect in masks] == [(73, 66, 62), (43, 43, 43)]
    for _paint, rect in masks:
        assert rect[0] + rect[2] == layout.award_x
        assert rect[2] >= layout.award_size * 0.4
        assert rect[2] < layout.award_size / 2
    # Percentages stay right-aligned even when their lengths differ.
    assert {call[1] + len(call[0]) * 12 for call in drawing.text} == {layout.label_right}
    drawing.images.clear()
    drawing.fills.clear()
    view.selected = 3
    row_bars._draw(view, cache)
    assert drawing.fills[-1][0].color == (73, 66, 62)  # the grey ring now covers the highlight


@pytest.mark.parametrize(
    ("page", "selected", "text", "accent"),
    [
        ((40, 40, 40), (251, 241, 199), (251, 241, 199), (251, 241, 199)),  # SPRUCE: cream
        ((17, 29, 53), (255, 204, 170), (255, 241, 232), (255, 204, 170)),  # Pico-8: peach on navy
        ((0, 0, 0), (0, 0, 0), (255, 255, 255), (255, 255, 255)),  # MINIMAL: black for a white bar
        ((235, 235, 235), (255, 255, 255), (20, 20, 20), (20, 20, 20)),  # a light page
    ],
)
def test_page_accent_is_the_selected_colour_only_where_it_reads(
    monkeypatch, page, selected, text, accent
):
    theme = SimpleNamespace(
        text_color_selected=lambda _font: [*selected, 255], text_color=lambda _font: list(text)
    )
    font = SimpleNamespace(FontPurpose=SimpleNamespace(LIST="list"))
    monkeypatch.setitem(sys.modules, "themes.theme", SimpleNamespace(Theme=theme))
    monkeypatch.setitem(sys.modules, "display.font_purpose", font)
    monkeypatch.setattr(row_bars, "page_color", lambda: page)
    assert row_bars.page_accent() == accent
