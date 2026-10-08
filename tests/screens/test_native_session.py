"""Exercise repeated native sessions and failures in one real PyUI runtime."""

import os
import subprocess
import sys

import pytest
from test_desktop_runner import PYUI_DIR, png_size

pytestmark = [
    pytest.mark.screens,
    pytest.mark.skipif(not (PYUI_DIR / "mainui.py").is_file(), reason="no PyUI checkout"),
]

PROGRAM = """
import logging
import signal
import threading
from dataclasses import replace
from pathlib import Path
from cheevos.platform.desktop.__main__ import parse_options, _write_pyui_config
from cheevos.ui.pyui import bootstrap

options = parse_options(["--headless", "--res", "640x480", "--script",
    "shot:first,down,a,y,b,b,b,shot:second,down,a,select,b,b,shot:third,b"])
bootstrap.add_pyui_to_path(options.pyui_dir)
host_logger = logging.getLogger("host-test")
bootstrap.install_logger(host_logger)

from cheevos.platform.desktop.capture import capture_frame
from cheevos.platform.desktop.controller import DesktopControllerInterface
from cheevos.platform.desktop.device import DesktopDevice
from cheevos.platform.desktop.window import windowed
from cheevos.platform.desktop.environments import fixture_environment
from cheevos.ui.pyui.native_app import append_entry, run
from cheevos.ui.screens.home import Home
from cheevos.ui.pyui import visible_images, status_bar, title_bar
from display.display import Display
from devices.device import Device
from themes.theme import Theme
from utils.py_ui_state import PyUiState
from utils.logger import PyUiLogger
from menus.app.hidden_apps_manager import AppsManager

out = Path(__import__("sys").argv[1])
controller = DesktopControllerInterface(options.script,
    lambda name: capture_frame(out / (name + ".png")), exit_when_script_ends=True)
setup = bootstrap.PyUiSetup(options.pyui_dir, _write_pyui_config(options),
    options.sd_root / "Saves" / "host-state.json", theme=options.theme,
    user_config_path=options.sd_root / "Saves" / "pyui-common.json")
with windowed(640, 480, 1):
    bootstrap.bootstrap(setup, lambda: DesktopDevice(640, 480,
        options.sd_root / "Saves", options.pyui_dir, controller))
env = replace(fixture_environment(options.sd_root), auto_sync=True)
host_state = PyUiState._config_path, PyUiState._data
host_device = Device.get_device()
host_fonts = dict(Display.fonts)
host_caches = Display._text_texture_cache.cache, Display._image_texture_cache.cache
host_signal = signal.getsignal(signal.SIGTERM)
host_handlers = list(logging.getLogger().handlers)
host_record_factory = logging.getLogRecordFactory()
bottom = lambda *args, **kwargs: None
top = lambda *args, **kwargs: None
Display.bottom_bar.render_bottom_bar = bottom
Display.top_bar.render_top_bar = top
Display.clear("Host Apps")
Display.present()

def restored():
    assert PyUiState._config_path == host_state[0]
    assert PyUiState._data is host_state[1]
    assert Device.get_device() is host_device
    assert Display.fonts == host_fonts
    assert Display._text_texture_cache.cache is host_caches[0]
    assert Display._image_texture_cache.cache is host_caches[1]
    assert Display.bottom_bar.render_bottom_bar is bottom
    assert Display.top_bar.render_top_bar is top
    assert PyUiLogger.get_logger() is host_logger
    assert signal.getsignal(signal.SIGTERM) == host_signal
    assert logging.getLogger().handlers == host_handlers
    assert logging.getLogRecordFactory() is host_record_factory
    assert not [t for t in threading.enumerate() if t.name.startswith("cheevos-")]
    assert visible_images._hooks.new_window() is None
    assert visible_images._hooks.version() == 0
    assert status_bar._bar is None and title_bar._dot is None
    assert not env.paths.media_scratch.exists()
    assert not env.paths.scaled_scratch.exists()
    assert Display.bg_canvas is None
    assert Display.top_bar_text == "Host Apps"

AppsManager.initialize(str(env.paths.user_dir / "host-apps.json"))
entries = []
append_entry(entries)
assert len(entries) == 1
entry = entries[0]
assert entry.get_extra_data().get_label() == "Cheevos"
AppsManager.hide_app(entry.get_extra_data())
hidden = []
append_entry(hidden)
assert not hidden
append_entry(hidden, show_all_apps=True)
assert hidden[0].get_primary_text() == "Cheevos(Hidden)"
AppsManager.show_app(entry.get_extra_data())

for index in range(3):
    assert entry.get_value()(env) == 0
    restored()
    capture_frame(out / ("host" + str(index) + ".png"))

original = Home.run
def broken(self):
    raise RuntimeError("injected screen failure")
Home.run = broken
assert run(env) == 1
Home.run = original
restored()
assert not controller.unplayed
"""


def test_repeated_sessions_restore_host_and_stop_workers_after_a_ui_error(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM, str(tmp_path / "shots")],
        env={
            **os.environ,
            "CHEEVOS_SDCARD_ROOT": str(tmp_path / "sdcard"),
            "SDL_VIDEODRIVER": "dummy",
            "SDL_RENDER_DRIVER": "software",
            "SDL_AUDIODRIVER": "dummy",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for name in ("first", "second", "third", "host0", "host1", "host2"):
        assert png_size(tmp_path / "shots" / f"{name}.png") == (640, 480)
