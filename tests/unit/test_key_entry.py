import json
import logging
import sys
import types

import pytest

from cheevos.app import AppEnvironment, _validator
from cheevos.core.ra_client import Response
from cheevos.platform.paths import Paths
from cheevos.ui.pyui import generated, primitives, status_bar
from cheevos.ui.pyui.buttons import Button

KEY = "A" * 32


class Answer:
    """A transport that answers every request with one status."""

    def __init__(self, status):
        self.status = status

    def get(self, host, path, headers):
        body = json.dumps({"User": "Balah"} if self.status == 200 else {}).encode()
        return Response(status=self.status, body=body)


@pytest.mark.parametrize(("status", "verdict"), [(200, True), (401, False), (404, None)])
def test_key_check_answers_instead_of_raising(tmp_path, status, verdict):
    paths = Paths(sdcard=tmp_path, platform="MiyooMini")
    env = AppEnvironment(paths=paths, transport_factory=lambda: Answer(status))
    assert _validator(env)("Balah", KEY) is verdict


def fake_pyui(monkeypatch, pyui_log, get_input, entry=None):
    """Stand in for the PyUI modules ``ask_text`` uses; returns the fake ``Theme``."""

    class Theme:
        @classmethod
        def keyboard_entry_bg(cls):
            return entry

        @staticmethod
        def background():
            return None

    keyboard = types.SimpleNamespace(
        OnScreenKeyboard=type("OnScreenKeyboard", (), {"get_input": get_input})
    )
    logger_module = types.SimpleNamespace(
        PyUiLogger=types.SimpleNamespace(get_logger=lambda: pyui_log)
    )
    for name, module in {
        "display": types.ModuleType("display"),
        "display.on_screen_keyboard": keyboard,
        "display.display": types.SimpleNamespace(Display=types.SimpleNamespace(bg_path=None)),
        "themes": types.ModuleType("themes"),
        "themes.theme": types.SimpleNamespace(Theme=Theme),
        "utils": types.ModuleType("utils"),
        "utils.logger": logger_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return Theme


def typing(pyui_log, typed):
    """A keyboard that logs what it fails to draw, as PyUI does when memory runs low."""

    def get_input(self, title, initial):
        pyui_log.warning("SDL Error received on loading %s", typed)
        return typed

    return get_input


def test_typing_a_secret_mutes_pyuis_log(monkeypatch, caplog):
    pyui_log = logging.getLogger("cheevos.pyui.test")
    fake_pyui(monkeypatch, pyui_log, typing(pyui_log, "B" * 32))
    caplog.set_level(logging.DEBUG)
    assert primitives.ask_text("Key", secret=True) == "B" * 32
    assert "B" * 32 not in caplog.text
    assert not pyui_log.disabled
    pyui_log.warning("after")
    assert "after" in caplog.text


def test_ordinary_text_entry_keeps_pyuis_log(monkeypatch, caplog):
    pyui_log = logging.getLogger("cheevos.pyui.test")
    fake_pyui(monkeypatch, pyui_log, typing(pyui_log, "hello"))
    caplog.set_level(logging.DEBUG)
    assert primitives.ask_text("Name") == "hello"
    assert "hello" in caplog.text


def test_keyboard_field_spans_the_screen_while_open(monkeypatch, tmp_path):
    # PyUI draws the field a sixteenth of the screen width tall at the image's own aspect.
    pytest.importorskip("sdl2.sdlimage")
    monkeypatch.setitem(generated._state, "scratch", tmp_path / "scratch")
    entry = tmp_path / "bg-list-l.png"
    entry.write_bytes(generated.encode_png(640, 90, bytes((80, 73, 69, 255)) * (640 * 90)))
    seen = []

    def get_input(self, title, initial):
        seen.append(theme.keyboard_entry_bg())
        return "x"

    theme = fake_pyui(monkeypatch, logging.getLogger("cheevos.pyui.test"), get_input, str(entry))
    assert primitives.ask_text("Key") == "x"
    loaded = generated.load_rgba(seen[0])
    assert loaded is not None
    width, height, pixels = loaded
    assert (width, height) == (256, 16)
    assert pixels[:4] == bytes((80, 73, 69, 255))
    assert theme.keyboard_entry_bg() == str(entry)


def test_keyboard_shows_its_hints_instead_of_the_sync_status(monkeypatch):
    bar = status_bar._Bar(lambda detailed: None, lambda: None)
    bar.hints = ((Button.Y, "Filter"),)
    monkeypatch.setattr(status_bar, "_bar", bar)
    hints = ((Button.START, "Done"), (Button.B, "Delete"))
    seen = []

    def get_input(self, title, initial):
        seen.append((bar.hints, bar.hidden, status_bar.press_start()))
        return "x"

    fake_pyui(monkeypatch, logging.getLogger("cheevos.pyui.test"), get_input)
    assert primitives.ask_text("Key", hints=hints) == "x"
    assert seen == [(hints, 1, False)]  # Start submits the text, it doesn't sync
    assert (bar.hints, bar.hidden) == (((Button.Y, "Filter"),), 0)
