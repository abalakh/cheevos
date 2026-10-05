"""Scripted input for headless runs: parse ``"down,down,a,shot:game_detail"`` into steps.

This module does not import PyUI; button names are resolved to ``ControllerInput`` members by
the controller interface.
"""

from __future__ import annotations

from dataclasses import dataclass

# Script token -> PyUI ControllerInput member name.
BUTTONS: dict[str, str] = {
    "up": "DPAD_UP",
    "down": "DPAD_DOWN",
    "left": "DPAD_LEFT",
    "right": "DPAD_RIGHT",
    "a": "A",
    "b": "B",
    "x": "X",
    "y": "Y",
    "l1": "L1",
    "r1": "R1",
    "l2": "L2",
    "r2": "R2",
    "start": "START",
    "select": "SELECT",
    "menu": "MENU",
}

_CAPTURE_PREFIX = "shot:"
_WAIT_PREFIX = "wait:"


@dataclass(frozen=True, slots=True)
class Press:
    """Press and release one button.

    Attributes:
        button: PyUI ``ControllerInput`` member name, e.g. ``"DPAD_DOWN"``.
    """

    button: str


@dataclass(frozen=True, slots=True)
class Capture:
    """Save the currently displayed frame.

    Attributes:
        name: File stem for the PNG, e.g. ``"home"``.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Wait:
    """Let PyUI run idle input ticks (about 1/12 s each), e.g. while a sync finishes.

    Attributes:
        ticks: Number of idle ticks.
    """

    ticks: int


Step = Press | Capture | Wait


class ScriptError(ValueError):
    """Raised for an unknown or malformed script token."""


def parse_script(text: str) -> list[Step]:
    """Parse a comma-separated input script.

    Tokens are button names (see :data:`BUTTONS`), ``shot:<name>`` captures, or ``wait:<ticks>``
    idle ticks. Whitespace and empty tokens are ignored; matching is case-insensitive for
    buttons.

    Args:
        text: Script such as ``"down, down, a, shot:game_detail"``.

    Returns:
        Steps in order.

    Raises:
        ScriptError: If a token is not a known button or has an empty capture name.
    """
    steps: list[Step] = []
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        if token.lower().startswith(_WAIT_PREFIX):
            count = token[len(_WAIT_PREFIX) :].strip()
            if not count.isdigit() or int(count) < 1:
                raise ScriptError(f"invalid wait in {token!r}")
            steps.append(Wait(int(count)))
            continue
        if token.lower().startswith(_CAPTURE_PREFIX):
            name = token[len(_CAPTURE_PREFIX) :].strip()
            if not name or "/" in name:
                raise ScriptError(f"invalid capture name in {token!r}")
            steps.append(Capture(name))
            continue
        button = BUTTONS.get(token.lower())
        if button is None:
            raise ScriptError(f"unknown button {token!r}; expected one of {sorted(BUTTONS)}")
        steps.append(Press(button))
    return steps
