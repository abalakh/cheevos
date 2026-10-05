"""Keep PyUI in a normal desktop window.

PyUI opens a fullscreen window at the monitor's resolution, which suits a handheld but would
take over a desktop screen and stretch the UI. While :func:`windowed` is active, window creation
goes to a plain window of the device's logical size times ``scale``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

import sdl2
import sdl2.ext


@contextmanager
def windowed(width: int, height: int, scale: int) -> Iterator[None]:
    """Redirect ``sdl2.ext.Window`` creation to a non-fullscreen window.

    PyUI looks up ``sdl2.ext.Window`` at call time, so swapping the attribute is enough;
    PyUI's own code stays untouched. The original factory is restored on exit.

    Args:
        width: Logical screen width.
        height: Logical screen height.
        scale: Integer zoom applied to the window size.

    Yields:
        Nothing; wrap the call that initialises PyUI's display.
    """
    original = sdl2.ext.Window

    def make_window(_title: str, **_kwargs: object) -> sdl2.ext.Window:
        """Create the desktop window, ignoring PyUI's size and fullscreen flag."""
        return original(
            "Cheevos (desktop)",
            size=(width * scale, height * scale),
            flags=sdl2.SDL_WINDOW_SHOWN,
        )

    with mock.patch.object(sdl2.ext, "Window", new=make_window):
        yield
