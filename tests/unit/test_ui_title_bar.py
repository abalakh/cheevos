import logging

import pytest

from cheevos.core.models import AwardKind
from cheevos.ui.pyui import title_bar
from cheevos.ui.pyui.title_bar import Title, compose, dot_x, gap_spaces

CHAR = 10  # every character is 10 px wide in these tests


def measure(value):
    return len(value) * CHAR


def fit(value, width):
    if measure(value) <= width:
        return value
    return value[: max(width // CHAR - 1, 0)] + "…"


def test_gap_spaces_leave_room_for_the_dot_and_its_padding():
    assert gap_spaces(12, 6) == 5  # 12 + 2 * 8 = 28 px -> five 6 px spaces
    assert gap_spaces(12, 7) == 4
    assert gap_spaces(12, 0) == 28  # a font without a space width doesn't divide by zero


def test_only_the_name_is_shortened():
    title = Title("Final Fantasy Tactics Advance", "90/138")
    # 200 px, less " 90/138" (70 px), leaves the name 130 px: 12 letters and the ellipsis
    assert compose(title, room=200, dot=12, measure=measure, fit=fit) == (
        "Final Fantas…",
        " ",
        "90/138",
    )
    assert compose(title, room=500, dot=12, measure=measure, fit=fit)[0] == title.name


def test_an_award_leaves_a_gap_for_its_dot():
    title = Title("Descent", "106/106", AwardKind.MASTERED)
    name, gap, tail = compose(title, room=500, dot=12, measure=measure, fit=fit)
    assert (name, tail) == ("Descent", "106/106")
    assert gap == " " * 3  # 28 px of dot and padding in 10 px spaces


def test_dot_is_centred_in_the_gap_of_a_centred_title():
    # 640 px screen, a 200 px title centred at 320: it spans 220-420. The name ends at 290 and
    # the tail starts at 360, so a 10 px dot sits at 320-330.
    assert dot_x(640, text=200, name=70, tail=60, dot=10) == 320
    assert dot_x(641, text=201, name=70, tail=60, dot=10) == 320  # PyUI rounds like int()


class FakeBar:
    def __init__(self):
        self.titles = []

    def render(self, title, hide_top_bar_icons=False):
        self.titles.append(title)


@pytest.fixture
def hooked(monkeypatch):
    bar = FakeBar()
    drawn = []
    monkeypatch.setattr(title_bar, "_draw", lambda _bar, dot: drawn.append(dot.text))
    monkeypatch.setattr(title_bar, "_dot", None)
    return bar, title_bar._wrap_render(bar, bar.render), drawn


def dot(text):
    return title_bar._Dot(text, "Descent", "1/106", AwardKind.MASTERED, 12)


def test_dot_is_drawn_only_under_its_own_title_and_forgotten_after(hooked, monkeypatch):
    bar, render, drawn = hooked
    monkeypatch.setattr(title_bar, "_dot", dot("Descent   1/106"))
    render("Descent   1/106")
    render("Descent   1/106")  # a popup over the screen redraws the same title
    assert drawn == ["Descent   1/106", "Descent   1/106"]
    render("Descent")  # the achievement card: another title
    assert title_bar._dot is None
    render("Descent   1/106")  # nothing left to draw until the game screen sets it again
    assert len(drawn) == 2
    assert bar.titles == ["Descent   1/106", "Descent   1/106", "Descent", "Descent   1/106"]


def test_a_failing_dot_is_dropped_and_logged_once(monkeypatch, caplog):
    bar = FakeBar()
    calls = []

    def broken(_bar, _dot):
        calls.append(1)
        raise RuntimeError("no font")

    monkeypatch.setattr(title_bar, "_draw", broken)
    monkeypatch.setattr(title_bar, "_dot", dot("Descent   1/106"))
    render = title_bar._wrap_render(bar, bar.render)
    with caplog.at_level(logging.ERROR):
        render("Descent   1/106")
        render("Descent   1/106")
    assert len(calls) == 1
    assert caplog.text.count("Could not draw the award dot") == 1
    assert bar.titles == ["Descent   1/106", "Descent   1/106"]  # the title itself still shows


def test_keyword_title_and_no_dot(hooked):
    bar, render, drawn = hooked
    render(title="Games · All games")
    assert (bar.titles, drawn) == (["Games · All games"], [])
