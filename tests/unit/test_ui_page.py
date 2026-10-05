import pytest

from cheevos.ui.pyui.primitives import Button
from cheevos.ui.screens import page

ROOM = 300  # 10 rows of 30 px fit


def rows(count, height=30):
    return [page.Row(height, lambda top: None) for _ in range(count)]


@pytest.mark.parametrize(
    ("first", "pressed", "expected"),
    [
        (0, Button.DOWN, 1),
        (5, Button.UP, 4),
        (0, Button.UP, 0),  # never above the top
        (0, Button.R1, 9),  # the last visible row (9) comes to the top
        (20, Button.L1, 11),  # the first visible row (20) goes to the bottom
        (4, Button.L1, 0),
        (3, None, 3),
    ],
)
def test_l1_r1_move_a_screenful_keeping_one_row(first, pressed, expected):
    assert page.scroll(first, pressed, rows(40), ROOM) == expected


def test_the_screenful_depends_on_the_screen_and_the_rows():
    assert page.scroll(0, Button.R1, rows(40), 600) == 19  # a taller screen: 20 rows fit
    tall = rows(3, height=500)  # a row taller than the screen still moves one row
    assert page.scroll(0, Button.R1, tall, ROOM) == 1
    assert page.scroll(2, Button.L1, tall, ROOM) == 1


def test_rows_being_rebuilt_move_one_row():
    assert page.scroll(5, Button.R1, None, ROOM) == 6
