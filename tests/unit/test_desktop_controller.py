import importlib
import sys
from dataclasses import dataclass
from enum import Enum
from types import ModuleType, SimpleNamespace

import pytest

from cheevos.platform.desktop.script import BUTTONS, Capture, Press, Wait

ControllerInput = Enum("ControllerInput", sorted(set(BUTTONS.values())))


@dataclass
class Clock:
    now: float = 0.0

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def desktop_controller(monkeypatch):
    # Unit tests also run without a PyUI checkout; only its enum and base class are needed.
    for name, module in {
        "controller": ModuleType("controller"),
        "controller.controller_inputs": SimpleNamespace(ControllerInput=ControllerInput),
        "controller.controller_interface": SimpleNamespace(ControllerInterface=object),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "cheevos.platform.desktop.controller"
    # Track the import in monkeypatch's undo stack so the fake PyUI types don't leak.
    monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, name)
    module = importlib.import_module(name)
    monkeypatch.setattr(module.DesktopControllerInterface, "init_controller", lambda self: None)
    return module


@pytest.mark.parametrize("tick_seconds", [1 / 12, 0.05])
def test_wait_ticks_return_to_the_ui_before_the_next_capture(
    monkeypatch, desktop_controller, tick_seconds
):
    clock, captures = Clock(), []
    monkeypatch.setattr(desktop_controller.time, "sleep", clock.sleep)
    controller = desktop_controller.DesktopControllerInterface(
        [Wait(30), Capture("loaded"), Press("A")], captures.append
    )

    def poll():
        # PyUI retries within one UI tick after truncating a seconds timeout to milliseconds.
        deadline = clock.now + tick_seconds
        while clock.now < deadline:
            pressed = controller.get_input(int((deadline - clock.now) * 1000))
            if pressed is not None:
                return pressed
        return None

    for _ in range(30):
        assert poll() is None
        assert captures == []
    assert clock.now >= 30 * tick_seconds
    assert poll().name == "A"
    assert captures == ["loaded"]
