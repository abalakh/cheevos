import pytest

from cheevos.ui.pyui import text
from cheevos.ui.pyui.text import ListRoom, Text, displayable, fit_text, text_width

LACKING = {"·", "…", "é"}  # a pixel font like Pico-8's


@pytest.fixture(autouse=True)
def fake_font(monkeypatch):
    """Every character is 10 px wide (a "W" 20 px); the font lacks the characters in LACKING."""
    measured = []

    def advance(_purpose, char):
        measured.append(char)
        return 20 if char == "W" else 10

    monkeypatch.setattr(text, "_advance", advance)
    monkeypatch.setattr(text, "_has_glyph", lambda _purpose, char: char not in LACKING)
    text._advances.clear()
    text._glyphs.clear()
    text._ellipsis.cache_clear()
    yield measured
    text._advances.clear()
    text._glyphs.clear()
    text._ellipsis.cache_clear()


def test_plain_ascii_is_returned_as_is():
    title = "Final Fantasy Tactics Advance"
    assert displayable(title, Text.TITLE) is title


def test_spaces_collapse_and_emoji_go():
    assert displayable("  Mario \U0001f3ae  Kart ", Text.TITLE) == "Mario Kart"


def test_characters_the_font_lacks_get_stand_ins():
    assert displayable("Pokémon · Red…", Text.BODY) == "Pokemon - Red..."
    assert displayable("Ñandú", Text.BODY) == "Ñandú"  # the font has these


def test_text_width_measures_each_character_once_per_font(fake_font):
    assert text_width("WAA", Text.TITLE) == 40
    assert text_width("AWW", Text.TITLE) == 50
    assert sorted(fake_font) == ["A", "W"]
    assert text_width("A", Text.BODY) == 10
    assert sorted(fake_font) == ["A", "A", "W"]


def test_fit_text_keeps_text_that_fits_and_shortens_the_rest():
    assert fit_text("Metroid", Text.TITLE, 100) == "Metroid"  # 70 px of 97
    # 97 px less "..." (30 px) leaves 67 px: six letters, then the stand-in ellipsis
    assert fit_text("Metroid Fusion", Text.TITLE, 100) == "Metroi..."


def test_list_room_leaves_the_value_its_width_and_the_title_a_minimum():
    room = ListRoom(full=400, gap=16, least=160)
    assert room.title("") == 400
    assert room.title("12/40") == 400 - 50 - 16
    assert room.title("W" * 20) == 160
