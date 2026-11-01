from unittest.mock import Mock

import pytest

from cheevos.ui import strings
from cheevos.ui.pyui.primitives import Area
from cheevos.ui.screens import profile
from cheevos.ui.screens.common import PADDING

WIDTH = 640  # a 608 px table: columns of 101 px fit titles up to 85 px
CHAR = 10  # px per character in the fake font


@pytest.fixture
def drawn(monkeypatch):
    """Record where the console table's cells are drawn: text -> x."""
    cells: dict[str, int] = {}
    ui = Mock(
        screen_size=Mock(return_value=(WIDTH, 480)),
        line_height=Mock(return_value=20),
        text_width=lambda value, role: len(value) * CHAR,
        displayable=lambda value: value,
        fit_text=lambda value, role, room: value,
        text=lambda value, x, y, **kwargs: cells.__setitem__(value, x),
    )
    monkeypatch.setattr(profile, "ui", ui)
    return cells


def draw_titles() -> None:
    page = profile._Page(Mock(), Mock(), Area(0, 0, WIDTH, 400))
    titles = (strings.CONSOLE, strings.PLAYED, strings.BEATEN, strings.MASTERED)
    page._table_row(titles, header=True).draw(0)


SIXTH = (WIDTH - PADDING * 2) // 6


def test_number_columns_are_a_sixth_of_the_table(drawn):
    draw_titles()

    assert drawn["Beaten"] - drawn["Played"] == SIXTH
    assert drawn["Mastered"] - drawn["Beaten"] == SIXTH


def test_a_longer_title_widens_only_its_column(monkeypatch, drawn):
    monkeypatch.setattr(strings, "MASTERED", "Опановано!")  # 100 px: wider than a sixth with a gap

    draw_titles()

    assert drawn["Beaten"] - drawn["Played"] == SIXTH
    assert drawn["Опановано!"] - drawn["Beaten"] == 100 + PADDING
    assert drawn["Опановано!"] == WIDTH - PADDING  # still ends at the right edge
