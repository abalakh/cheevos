import pytest

from cheevos.ui.pyui.views import grid_shape
from cheevos.ui.pyui.visible_images import next_page


@pytest.mark.parametrize(
    ("width", "usable", "column", "row", "shape"),
    [
        (640, 360, 155, 155, (4, 2)),  # as designed
        (720, 480 - 120, 155, 155, (4, 2)),  # half a column spare: not enough for a fifth
        (1280, 540, 232.5, 215, (5, 2)),  # 16:9 at the theme's 1.5x: one more column
        (720, 586, 174, 169, (4, 3)),  # square: one more row
        (480, 680, 155, 206, (3, 3)),  # portrait: 2.97 columns round up, rows don't
        (200, 100, 155, 206, (1, 1)),  # never less than one
    ],
)
def test_grid_shape(width, usable, column, row, shape):
    assert grid_shape(width, usable, column, row) == shape


@pytest.mark.parametrize(
    ("shown", "forward", "page"),
    [
        (range(5, 10), True, range(10, 15)),  # scrolling down: the page below
        (range(5, 10), False, range(5)),  # scrolling up: the page above
        (range(18, 20), True, range(16, 18)),  # at the end: the page above instead
        (range(5), False, range(5, 10)),  # at the top: the page below instead
        (range(5), True, range(5, 10)),
    ],
)
def test_next_page_follows_the_scroll(shown, forward, page):
    assert next_page(shown, 20, forward=forward) == page
