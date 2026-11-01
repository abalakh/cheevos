import sys
from types import SimpleNamespace

import pytest

from cheevos.ui.pyui import text
from cheevos.ui.pyui.text import Text, displayable, fit_text, fit_with_tail, text_width

LACKING = {"·", "…", "é"}  # a pixel font like Pico-8's


def advance(char):
    return 20 if char == "W" else 10


def count_chars_that_fit(_purpose, value, max_width):
    used = 0
    for index, char in enumerate(value):
        used += advance(char)
        if used > max_width:
            return index
    return len(value)


@pytest.fixture(autouse=True)
def fake_font(monkeypatch):
    """PyUI's Display with a font where every character is 10 px wide (a "W" 20 px), lacking
    the characters in LACKING."""
    display = SimpleNamespace(
        fonts={"loaded": True},
        get_text_width_from_glyphs=lambda _purpose, value: sum(map(advance, value)),
        get_text_dimensions=lambda _purpose, value: (sum(map(advance, value)), 20),
        count_chars_that_fit=count_chars_that_fit,
        requires_fallback_font=lambda value, _purpose: any(char in LACKING for char in value),
    )
    purposes = SimpleNamespace(FontPurpose={role.value: role.value for role in Text})
    monkeypatch.setitem(sys.modules, "display.display", SimpleNamespace(Display=display))
    monkeypatch.setitem(sys.modules, "display.font_purpose", purposes)
    text._glyphs.clear()
    yield display
    text._glyphs.clear()


def test_plain_ascii_is_returned_as_is():
    title = "Final Fantasy Tactics Advance"
    assert displayable(title, Text.TITLE) is title


def test_spaces_collapse_and_emoji_go():
    assert displayable("  Mario \U0001f3ae  Kart ", Text.TITLE) == "Mario Kart"


def test_characters_the_font_lacks_get_stand_ins():
    assert displayable("Pokémon · Red…", Text.BODY) == "Pokemon - Red..."
    assert displayable("Ñandú", Text.BODY) == "Ñandú"  # the font has these


def test_characters_are_kept_until_the_theme_fonts_are_loaded(fake_font):
    fake_font.fonts = {}
    assert displayable("Pokémon · Red…", Text.BODY) == "Pokémon · Red…"


def test_widths_come_from_pyui_in_the_roles_font(fake_font, monkeypatch):
    asked = []
    monkeypatch.setattr(
        fake_font, "get_text_width_from_glyphs", lambda purpose, _value: asked.append(purpose) or 7
    )
    assert text_width("Mario", Text.HEADING) == 7
    assert asked == ["TOP_BAR_TEXT"]


def test_fit_text_keeps_text_that_fits_and_shortens_the_rest():
    assert fit_text("Metroid", Text.TITLE, 100) == "Metroid"  # 70 px of 100
    # 100 px less "..." (30 px) leaves 70 px: seven letters, then the ellipsis
    assert fit_text("Metroid Fusion", Text.TITLE, 100) == "Metroid..."


def test_fit_with_tail_keeps_the_date_whole():
    # Joined: "Mastered - 1 May" (16 characters, 160 px) fits 200 px as it is.
    assert fit_with_tail("Mastered", "1 May", Text.BODY, 200) == "Mastered - 1 May"
    # Too long: the description is shortened, the date and its separator stay.
    fitted = fit_with_tail("Awarded for earning points", "1 May", Text.BODY, 200)
    assert fitted.endswith("... - 1 May")
    assert text_width(fitted, Text.BODY) <= 200
    # No room left for a description: everything is shortened together.
    assert fit_with_tail("Awarded", "27 April 2026", Text.BODY, 110) == "Awarded..."
    assert fit_with_tail("", "1 May", Text.BODY, 200) == "1 May"
    assert fit_with_tail("Mastered", "", Text.BODY, 200) == "Mastered"


def test_description_room_takes_the_icon_column_from_the_row_background(monkeypatch):
    # SPRUCE at 480x800: the row background is 640 px wide, so PyUI's icon column is 80 px.
    device = SimpleNamespace(screen_width=lambda: 480)
    theme = SimpleNamespace(
        get_list_large_selected_bg=lambda: "bg-list-l.png",
        get_descriptive_list_icon_offset_x=lambda: 7,
        get_descriptive_list_text_from_icon_offset=lambda: 7,
    )
    display = SimpleNamespace(get_image_dimensions=lambda _path: (640, 90))
    monkeypatch.setitem(
        sys.modules,
        "devices.device",
        SimpleNamespace(Device=SimpleNamespace(get_device=lambda: device)),
    )
    monkeypatch.setitem(sys.modules, "themes.theme", SimpleNamespace(Theme=theme))
    monkeypatch.setitem(sys.modules, "display.display", SimpleNamespace(Display=display))
    assert text.description_room() == 480 - 7 - 80 - 7 * 2


def test_lines_break_between_words():
    assert text.wrap("aaa bbb ccc dd", Text.BODY, 70) == ["aaa bbb", "ccc dd"]


def test_text_without_spaces_breaks_where_the_line_ends():
    # Chinese and Japanese put no spaces between words.
    assert text.wrap("一二三四五六七八", Text.BODY, 30) == ["一二三", "四五六", "七八"]
    assert text.wrap("ab 一二三四五", Text.BODY, 30) == ["ab", "一二三", "四五"]


def test_a_character_wider_than_the_line_still_gets_a_line():
    assert text.wrap("WWW", Text.BODY, 10) == ["W", "W", "W"]
