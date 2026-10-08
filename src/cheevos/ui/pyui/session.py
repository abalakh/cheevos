"""Scope Cheevos's bridge state while borrowing the launcher's PyUI runtime."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from cheevos.platform.paths import Paths
from cheevos.ui.pyui import generated, glyphs, text, texture_budget, visible_images


def _reset() -> None:
    """Release session callbacks and measurements tied to the current theme."""
    visible_images.reset()
    glyphs.reset()
    text.reset()
    generated.reset()


@contextlib.contextmanager
def installed(paths: Paths) -> Iterator[None]:
    """Borrow PyUI without initializing its device, theme, display, controller or logger.

    Args:
        paths: Cheevos's own view state and scratch locations.

    Yields:
        Nothing. The caller runs the app on PyUI's UI thread.
    """
    from controller.controller import Controller
    from devices.device import Device
    from display.display import Display
    from utils.py_ui_state import PyUiState

    state = PyUiState._config_path, PyUiState._data
    background = Display.bg_path, Display.is_custom_theme_background
    title, bottom = Display.top_bar_text, Display.bottom_bar_text
    device = Device.get_device()
    _reset()
    try:
        state_path = paths.user_dir / "pyui-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists():
            state_path.write_text("{}", encoding="utf-8")
        PyUiState.init(str(state_path))
        with texture_budget.installed(Display, device.screen_width(), device.screen_height()):
            yield
    finally:
        PyUiState._config_path, PyUiState._data = state
        _reset()
        Display.unlock_current_image()
        Display.set_new_bg(background[0], is_custom_theme_background=background[1])
        Controller.clear_input_queue()
        Display.clear(title, bottom_bar_text=bottom)
        Display.present()
