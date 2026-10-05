"""Rasterize the SVG icon sources into the PNGs that ship with the app (dev-only, uses SDL).

- ``assets/icons/cheevos.svg`` -> ``app/cheevos.png``: the Apps-menu icon, drawn at the
  largest size SpruceOS themes use (105 px at 1280x720) so PyUI only ever scales it down.
- ``assets/pixelarticons/<name>.svg`` -> ``src/cheevos/res/icons/<size>/<name>.png``: list
  icons, recoloured to the theme accent and rendered at exact multiples of their 24 px grid
  (24, 48 and 72 px) so every pixel edge stays sharp. A few also get a muted variant
  (:data:`MUTED_ICONS`).

Usage: ``uv run python scripts/render_icons.py``
"""

from __future__ import annotations

import ctypes
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using SDL2 binaries from pysdl2-dll")

import sdl2  # noqa: E402 — after silencing pysdl2-dll's import-time notice
from sdl2 import sdlimage  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
APP_ICON_SOURCE = REPO / "assets" / "icons" / "cheevos.svg"
APP_ICON_OUTPUT = REPO / "app" / "cheevos.png"
APP_ICON_SIZE = 105
PIXEL_SOURCE_DIR = REPO / "assets" / "pixelarticons"
PIXEL_OUTPUT_DIR = REPO / "src" / "cheevos" / "res" / "icons"
PIXEL_GRID = 24
# 24 px: bottom-bar status; 48 px: lists on 640-752 px wide screens; 72 px: lists above.
PIXEL_SCALES = (1, 2, 3)
ACCENT = "#D7B45F"  # SPRUCE theme accent (sampled from its app icons)
MUTED = "#7C6F64"  # SPRUCE's muted text (locked rows), like RA's grey locked badges
# Extra renderings in the muted colour: source name -> output name. The grey lock stands in for
# a locked achievement's badge until it's downloaded (the gold trophy for an unlocked one).
MUTED_ICONS = {"lock": "lock-muted"}


class RenderError(RuntimeError):
    """Raised when SDL cannot rasterize or save an icon."""


def _sized_svg(svg: str, size: int) -> bytes:
    """Return ``svg`` with its rendered size set to ``size`` px (the viewBox is kept).

    Args:
        svg: SVG source text.
        size: Output width and height in pixels.

    Returns:
        UTF-8 encoded SVG.
    """
    svg = re.sub(r'\swidth="[^"]*"', f' width="{size}"', svg, count=1)
    svg = re.sub(r'\sheight="[^"]*"', f' height="{size}"', svg, count=1)
    return svg.encode("utf-8")


def render_svg(svg: str, size: int, output: Path) -> None:
    """Rasterize SVG text to a ``size``x``size`` PNG with SDL_image (nanosvg).

    Args:
        svg: SVG source text.
        size: Output width and height in pixels.
        output: Destination PNG path; parent directories are created.

    Raises:
        RenderError: If loading or saving fails.
    """
    data = _sized_svg(svg, size)
    buffer = ctypes.create_string_buffer(data, len(data))
    stream = sdl2.SDL_RWFromConstMem(buffer, len(data))
    surface = sdlimage.IMG_Load_RW(stream, 1)
    if not surface:
        raise RenderError(f"IMG_Load_RW: {sdlimage.IMG_GetError().decode()}")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if sdlimage.IMG_SavePNG(surface, str(output).encode()):
            raise RenderError(f"IMG_SavePNG: {sdl2.SDL_GetError().decode()}")
    finally:
        sdl2.SDL_FreeSurface(surface)


def render_pixel_icons() -> int:
    """Render every pixelarticons source at each scale in the accent colour.

    Returns:
        Number of PNGs written.
    """
    count = 0
    for source in sorted(PIXEL_SOURCE_DIR.glob("*.svg")):
        text = source.read_text(encoding="utf-8")
        outputs = [(source.stem, ACCENT)]
        if source.stem in MUTED_ICONS:
            outputs.append((MUTED_ICONS[source.stem], MUTED))
        for name, color in outputs:
            svg = text.replace("currentColor", color)
            for scale in PIXEL_SCALES:
                size = PIXEL_GRID * scale
                render_svg(svg, size, PIXEL_OUTPUT_DIR / str(size) / f"{name}.png")
                count += 1
    return count


def main() -> int:
    """Render all icons.

    Returns:
        Process exit code.
    """
    render_svg(APP_ICON_SOURCE.read_text(encoding="utf-8"), APP_ICON_SIZE, APP_ICON_OUTPUT)
    print(f"App icon: {APP_ICON_OUTPUT.relative_to(REPO)} ({APP_ICON_SIZE}px)")
    count = render_pixel_icons()
    print(f"Pixel icons: {count} PNGs in {PIXEL_OUTPUT_DIR.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
