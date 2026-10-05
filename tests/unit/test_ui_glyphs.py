import struct
import zlib

from cheevos.ui.pyui import generated
from cheevos.ui.pyui.generated import encode_png
from cheevos.ui.pyui.glyphs import Lettering, Style, compose, style_from_pixels

GOLD = (215, 180, 95)
BLACK = (0, 0, 0)


def pixels(*colors: tuple[int, int, int, int]) -> bytes:
    return b"".join(bytes(color) for color in colors)


def test_style_takes_fill_and_contrasting_ink_from_the_badge():
    badge = pixels(*[(*GOLD, 255)] * 6, (*BLACK, 255), (*BLACK, 255), (10, 10, 10, 0))
    assert style_from_pixels(26, badge) == Style(26, GOLD, BLACK)


def test_style_needs_opaque_pixels():
    assert style_from_pixels(26, pixels((1, 2, 3, 0))) is None


def lettering(width: int, height: int) -> Lettering:
    return Lettering(width, height, b"\xff" * (width * height), cap_top=2, cap_bottom=height - 2)


def test_single_letter_is_a_circle():
    width, rgba = compose("A", Style(20, GOLD, BLACK), lettering(6, 12))
    assert width == 20
    corner, centre = rgba[3], rgba[(10 * 20 + 10) * 4 : (10 * 20 + 10) * 4 + 4]
    assert corner == 0  # outside the circle
    assert tuple(centre) == (*BLACK, 255)  # lettering in ink, fully opaque


def test_word_is_a_padded_pill_with_fill_around_the_text():
    width, rgba = compose("SELECT", Style(20, GOLD, BLACK), lettering(40, 16))
    assert width == 40 + 2 * 6
    edge = (10 * width + 2) * 4  # left padding, mid-height: fill colour
    assert tuple(rgba[edge : edge + 4]) == (*GOLD, 255)


def test_encode_png_round_trips():
    rgba = pixels((1, 2, 3, 4), (5, 6, 7, 8))
    png = encode_png(2, 1, rgba)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, depth, kind = struct.unpack(">IIBB", png[16:26])
    assert (width, height, depth, kind) == (2, 1, 8, 6)
    length = struct.unpack(">I", png[33:37])[0]
    assert zlib.decompress(png[41 : 41 + length]) == b"\x00" + rgba


def test_swatch_is_written_once_per_colour(tmp_path):
    generated.use_scratch(tmp_path)
    first = generated.swatch((1, 2, 3), 60)
    assert first == tmp_path / "swatch-0102033c-w.png"
    mtime = first.stat().st_mtime_ns
    assert generated.swatch((1, 2, 3), 60) == first
    assert first.stat().st_mtime_ns == mtime
    assert generated.swatch((1, 2, 3), 140) != first


def test_tall_swatch_for_vertical_strips(tmp_path):
    generated.use_scratch(tmp_path)
    tall = generated.swatch((1, 2, 3), 255, tall=True)
    assert tall.name == "swatch-010203ff-t.png"
    width, height = struct.unpack(">II", tall.read_bytes()[16:24])
    assert height > width
