import pytest

from cheevos.core.models import AwardKind
from cheevos.ui.pyui import generated
from cheevos.ui.pyui.bar_colors import (
    DARK_GOLD,
    GOLD,
    HARDCORE_GOLD,
    NEUTRAL_500,
    ZINC_300,
    ZINC_400,
    Marker,
    Paint,
    palette,
)

DARK = (43, 43, 43)  # SPRUCE's page
WHITE = (255, 255, 255)  # MINIMAL's selected row
YELLOW = (230, 190, 40)  # a theme that fights gold
CREAM = (240, 230, 200)


def test_dark_rows_get_ra_gold_and_grey():
    colors = palette(DARK, CREAM)
    assert (colors.hardcore, colors.casual) == (Paint(HARDCORE_GOLD), Paint(ZINC_400))
    assert colors.markers[AwardKind.MASTERED] == Marker(GOLD, filled=True)
    assert colors.markers[AwardKind.COMPLETED] == Marker(DARK_GOLD, filled=False)
    assert colors.markers[AwardKind.BEATEN_HARDCORE] == Marker(ZINC_300, filled=True)
    assert colors.markers[AwardKind.BEATEN_SOFTCORE] == Marker(ZINC_400, filled=False)


def test_light_rows_get_ras_light_mode_colours():
    colors = palette(WHITE, (0, 0, 0))
    assert (colors.hardcore, colors.casual) == (Paint(DARK_GOLD), Paint(NEUTRAL_500))
    assert colors.markers[AwardKind.MASTERED].color == DARK_GOLD
    assert colors.track.color == (0, 0, 0)


def test_unreadable_backgrounds_fall_back_to_the_theme_text_colour():
    colors = palette(YELLOW, (20, 20, 20))
    assert {colors.hardcore.color, colors.casual.color, colors.track.color} == {(20, 20, 20)}
    assert colors.hardcore.alpha > colors.casual.alpha > colors.track.alpha
    assert colors.markers[AwardKind.MASTERED].filled
    assert not colors.markers[AwardKind.BEATEN_SOFTCORE].filled


@pytest.mark.parametrize(("ring", "centre_alpha"), [(0, 255), (2, 0)])
def test_disc_is_filled_or_a_ring(ring, centre_alpha):
    size = 10
    pixels = generated.disc_pixels(GOLD, size, ring)
    assert len(pixels) == size * size * 4
    corner, centre = pixels[3], pixels[(5 * size + 5) * 4 + 3]
    assert corner == 0
    assert centre == centre_alpha
    edge = pixels[(5 * size + 0) * 4 + 3]  # left edge, mid-height: part of the ring too
    assert edge > 0


def test_average_composites_translucent_pixels_over_the_background():
    opaque = bytes((200, 100, 0, 255)) * 20
    assert generated.average_pixels(opaque, under=(100, 100, 100)) == (200, 100, 0)
    clear = bytes((0, 0, 0, 0)) * 20
    assert generated.average_pixels(clear, under=(100, 100, 100)) == (100, 100, 100)
    half = bytes((200, 200, 200, 128))
    assert generated.average_pixels(half, under=(0, 0, 0)) == (100, 100, 100)
