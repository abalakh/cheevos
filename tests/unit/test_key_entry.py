import json
import logging
import sys
import types

import pytest

from cheevos.app import AppEnvironment, _validator
from cheevos.core.ra_client import Response
from cheevos.platform.paths import Paths
from cheevos.ui.pyui import primitives

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


def fake_pyui(monkeypatch, pyui_log, typed):
    def get_input(self, title, initial):
        pyui_log.warning("SDL Error received on loading %s", typed)
        return typed

    keyboard = types.SimpleNamespace(
        OnScreenKeyboard=type("OnScreenKeyboard", (), {"get_input": get_input})
    )
    logger_module = types.SimpleNamespace(
        PyUiLogger=types.SimpleNamespace(get_logger=lambda: pyui_log)
    )
    for name, module in {
        "display": types.ModuleType("display"),
        "display.on_screen_keyboard": keyboard,
        "utils": types.ModuleType("utils"),
        "utils.logger": logger_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_typing_a_secret_mutes_pyuis_log(monkeypatch, caplog):
    pyui_log = logging.getLogger("cheevos.pyui.test")
    fake_pyui(monkeypatch, pyui_log, "B" * 32)
    caplog.set_level(logging.DEBUG)
    assert primitives.ask_text("Key", secret=True) == "B" * 32
    assert "B" * 32 not in caplog.text
    assert not pyui_log.disabled
    pyui_log.warning("after")
    assert "after" in caplog.text


def test_ordinary_text_entry_keeps_pyuis_log(monkeypatch, caplog):
    pyui_log = logging.getLogger("cheevos.pyui.test")
    fake_pyui(monkeypatch, pyui_log, "hello")
    caplog.set_level(logging.DEBUG)
    assert primitives.ask_text("Name") == "hello"
    assert "hello" in caplog.text
