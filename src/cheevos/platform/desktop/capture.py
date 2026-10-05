"""Save PyUI's current frame to a PNG file."""

from __future__ import annotations

import ctypes
from pathlib import Path

import sdl2
from display.display import Display
from sdl2 import sdlimage


class CaptureError(RuntimeError):
    """Raised when SDL cannot read back or save the frame."""


def capture_frame(path: Path) -> None:
    """Write the frame PyUI last presented to ``path`` as PNG.

    PyUI draws into an off-screen canvas texture and leaves it as the render target after
    presenting, so reading the current render target returns exactly the displayed frame at
    the logical resolution.

    Args:
        path: Destination PNG path; parent directories are created.

    Raises:
        CaptureError: If the display is not initialised, or reading the pixels or writing the
            PNG fails.
    """
    if Display.renderer is None:
        raise CaptureError("PyUI's display is not initialised")
    renderer = Display.renderer.sdlrenderer
    width, height = _target_size(renderer)
    pixel_format = sdl2.SDL_PIXELFORMAT_ARGB8888
    surface = sdl2.SDL_CreateRGBSurfaceWithFormat(0, width, height, 32, pixel_format)
    if not surface:
        raise CaptureError(f"SDL_CreateRGBSurfaceWithFormat: {sdl2.SDL_GetError().decode()}")
    try:
        contents = surface.contents
        if sdl2.SDL_RenderReadPixels(renderer, None, pixel_format, contents.pixels, contents.pitch):
            raise CaptureError(f"SDL_RenderReadPixels: {sdl2.SDL_GetError().decode()}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if sdlimage.IMG_SavePNG(surface, str(path).encode()):
            raise CaptureError(f"IMG_SavePNG: {sdl2.SDL_GetError().decode()}")
    finally:
        sdl2.SDL_FreeSurface(surface)


def _target_size(renderer: sdl2.SDL_Renderer) -> tuple[int, int]:
    """Return the size of the renderer's current target (PyUI's canvas).

    Args:
        renderer: The SDL renderer PyUI draws with.

    Returns:
        ``(width, height)`` in pixels.
    """
    width, height = ctypes.c_int(), ctypes.c_int()
    target = sdl2.SDL_GetRenderTarget(renderer)
    if target:
        sdl2.SDL_QueryTexture(target, None, None, ctypes.byref(width), ctypes.byref(height))
    else:
        sdl2.SDL_GetRendererOutputSize(renderer, ctypes.byref(width), ctypes.byref(height))
    return width.value, height.value
