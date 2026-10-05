"""Text handling for the PyUI bridge: glyph coverage, fast width estimates, fitting.

Theme fonts vary a lot (the Pico-8 theme's pixel font lacks "·" and "…"), and measuring every
row with SDL_ttf is too slow on a Miyoo Mini for big lists, so widths come from cached glyph
advances.
"""

from __future__ import annotations

import ctypes
import functools
import re
import unicodedata
from enum import Enum

# Emoji and pictographs: theme fonts have no glyphs for them (they render as boxes).
_NO_GLYPH = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u200d\u2b50\u2b55\u231a-\u23ff]")
# Typographic characters we use, with ASCII stand-ins for theme fonts that lack them
# (e.g. the Pico-8 theme's pixel font has neither "·" nor "…").
_ASCII_FALLBACKS = {
    "\u00b7": "-",  # middle dot
    "\u2026": "...",  # ellipsis
    "\u2014": "-",  # em dash
    "\u2013": "-",  # en dash
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}
_BMP_MAX = 0xFFFF  # TTF_GlyphIsProvided (pre-2.0.18) only takes 16-bit code points
# Width estimates ignore kerning; keep a little slack so fitted text never touches neighbours.
_FIT_MARGIN = 0.97
# Share of the screen width the top-bar title may use; the clock and battery take the rest.
_TITLE_WIDTH_SHARE = 0.44


class Text(Enum):
    """Text roles, mapped to PyUI font purposes (and so to theme fonts and colours)."""

    TITLE = "DESCRIPTIVE_LIST_TITLE"
    BODY = "DESCRIPTIVE_LIST_DESCRIPTION"
    LIST = "LIST"
    HEADING = "TOP_BAR_TEXT"
    GRID = "GRID_MULTI_ROW"  # captions under grid tiles


def font_purpose(role: Text) -> object:
    """Return PyUI's ``FontPurpose`` member for a text role.

    Args:
        role: Text role.

    Returns:
        The ``FontPurpose`` member.
    """
    from display.font_purpose import FontPurpose

    return FontPurpose[role.value]


@functools.lru_cache(maxsize=256)
def _has_glyph(purpose: str, char: str) -> bool:
    """Whether the active theme's font for ``purpose`` can draw ``char``.

    Args:
        purpose: ``FontPurpose`` member name.
        char: One character.

    Returns:
        ``True`` if the font has a glyph (or the check is unavailable).
    """
    from display.display import Display
    from display.font_purpose import FontPurpose
    from sdl2 import sdlttf

    fonts = getattr(Display, "fonts", None)
    loaded = fonts.get(FontPurpose[purpose]) if fonts else None
    if loaded is None:
        return True
    try:
        return bool(sdlttf.TTF_GlyphIsProvided32(loaded.font, ord(char)))
    except AttributeError:  # SDL_ttf older than 2.0.18
        return ord(char) > _BMP_MAX or bool(sdlttf.TTF_GlyphIsProvided(loaded.font, ord(char)))


def displayable(value: str, role: Text = Text.BODY) -> str:
    """Make RA text drawable in the theme font for ``role``.

    Removes emoji and pictographs (no theme font has them), swaps typographic characters the
    font lacks for ASCII, drops accents the font can't draw ("Pokémon" -> "Pokemon" in the
    Pico-8 theme), and collapses leftover spaces.

    Args:
        value: Text from RA or our strings (titles, rich presence, ...).
        role: Text role whose font will draw it.

    Returns:
        Text safe to render.
    """
    text = " ".join(_NO_GLYPH.sub("", value).split())
    for char, fallback in _ASCII_FALLBACKS.items():
        if char in text and not _has_glyph(role.value, char):
            text = text.replace(char, fallback)
    if text.isascii():
        return text
    return "".join(_plain(char) if not _has_glyph(role.value, char) else char for char in text)


@functools.lru_cache(maxsize=512)
def _plain(char: str) -> str:
    """Return a character without its accent ("é" -> "e"), for fonts that lack the accented one.

    Args:
        char: One character.

    Returns:
        The base letter, or the character itself when it has none.
    """
    base = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
    return base or char


@functools.lru_cache(maxsize=8192)
def _advance(purpose: str, char: str) -> int:
    """Return how far one character advances the pen in the theme font for ``purpose``.

    Cached per font and character, so measuring long lists costs dictionary lookups instead
    of an SDL_ttf call per string (on the Mini, per-string measurement of 1,000 rows took
    longer than 15 s).

    Args:
        purpose: ``FontPurpose`` member name.
        char: One character.

    Returns:
        Advance width in pixels.
    """
    from display.display import Display
    from display.font_purpose import FontPurpose
    from sdl2 import sdlttf

    font = Display.fonts[FontPurpose[purpose]].font
    metrics = [ctypes.c_int() for _ in range(5)]
    try:
        failed = sdlttf.TTF_GlyphMetrics32(font, ord(char), *(ctypes.byref(m) for m in metrics))
    except AttributeError:  # SDL_ttf older than 2.0.18
        failed = True
    if not failed:
        return metrics[4].value
    return int(Display.get_text_dimensions(FontPurpose[purpose], char)[0])


def text_width(value: str, role: Text) -> int:
    """Estimate the rendered width of ``value`` from cached glyph advances.

    Ignores kerning, which is within a few pixels for UI text; callers keep a small margin.

    Args:
        value: Text (already passed through :func:`displayable`).
        role: Text role (font).

    Returns:
        Width in pixels.
    """
    return sum(_advance(role.value, char) for char in value)


def _ellipsis(role: Text) -> str:
    """Return "…" if the font for ``role`` has it, else "...".

    Args:
        role: Text role.

    Returns:
        The ellipsis to append when truncating.
    """
    return displayable("…", role)


def fit_title(value: str) -> str:
    """Shorten a top-bar title with an ellipsis so it clears the clock and battery icons.

    Args:
        value: Desired title.

    Returns:
        The title, truncated if needed.
    """
    from devices.device import Device

    limit = int(Device.get_device().screen_width() * _TITLE_WIDTH_SHARE)
    return fit_text(value, Text.HEADING, limit)


def fit_text(value: str, role: Text, max_width: int) -> str:
    """Shorten text with an ellipsis so it fits ``max_width`` in the font for ``role``.

    Args:
        value: Text to fit.
        role: Text role (font).
        max_width: Available width in pixels.

    Returns:
        The text, truncated if needed.
    """
    value = displayable(value, role)
    budget = int(max_width * _FIT_MARGIN)
    if text_width(value, role) <= budget:
        return value
    ellipsis = _ellipsis(role)
    remaining = budget - text_width(ellipsis, role)
    for index, char in enumerate(value):
        remaining -= _advance(role.value, char)
        if remaining < 0:
            return value[:index].rstrip() + ellipsis
    return value


def list_title_width(value_text: str) -> int:
    """Width left for a list row's title next to the icon column and a right-aligned value.

    Mirrors PyUI's descriptive list layout: the icon column is 12.5% of the row, the title
    starts a theme-defined offset after it, and the value is right-aligned with that offset.

    Args:
        value_text: The row's right-aligned value (may be empty).

    Returns:
        Maximum title width in pixels.
    """
    from devices.device import Device
    from themes.theme import Theme

    screen = int(Device.get_device().screen_width())
    gap = int(Theme.get_descriptive_list_text_from_icon_offset())
    used = int(Theme.get_descriptive_list_icon_offset_x()) + screen // 8 + gap * 2
    if value_text:
        used += text_width(value_text, Text.TITLE) + gap
    return max(screen - used, screen // 4)
