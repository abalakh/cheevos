"""PyUI controller interface for the desktop: keyboard, gamepad and scripted input."""

from __future__ import annotations

import ctypes
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable

import sdl2
from controller.controller_inputs import ControllerInput
from controller.controller_interface import ControllerInterface

from cheevos.platform.desktop.script import Capture, Press, Step, Wait

logger = logging.getLogger(__name__)

# RetroArch's default keyboard layout, by scancode so it is independent of the OS key layout.
KEYBOARD: dict[int, ControllerInput] = {
    sdl2.SDL_SCANCODE_UP: ControllerInput.DPAD_UP,
    sdl2.SDL_SCANCODE_DOWN: ControllerInput.DPAD_DOWN,
    sdl2.SDL_SCANCODE_LEFT: ControllerInput.DPAD_LEFT,
    sdl2.SDL_SCANCODE_RIGHT: ControllerInput.DPAD_RIGHT,
    sdl2.SDL_SCANCODE_X: ControllerInput.A,
    sdl2.SDL_SCANCODE_Z: ControllerInput.B,
    sdl2.SDL_SCANCODE_S: ControllerInput.X,
    sdl2.SDL_SCANCODE_A: ControllerInput.Y,
    sdl2.SDL_SCANCODE_Q: ControllerInput.L1,
    sdl2.SDL_SCANCODE_W: ControllerInput.R1,
    sdl2.SDL_SCANCODE_1: ControllerInput.L2,
    sdl2.SDL_SCANCODE_2: ControllerInput.R2,
    sdl2.SDL_SCANCODE_RETURN: ControllerInput.START,
    sdl2.SDL_SCANCODE_RSHIFT: ControllerInput.SELECT,
}

# SDL reports Xbox positions; Spruce devices use the Nintendo layout, so map by position.
GAMEPAD: dict[int, ControllerInput] = {
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: ControllerInput.DPAD_UP,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: ControllerInput.DPAD_DOWN,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: ControllerInput.DPAD_LEFT,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: ControllerInput.DPAD_RIGHT,
    sdl2.SDL_CONTROLLER_BUTTON_B: ControllerInput.A,
    sdl2.SDL_CONTROLLER_BUTTON_A: ControllerInput.B,
    sdl2.SDL_CONTROLLER_BUTTON_Y: ControllerInput.X,
    sdl2.SDL_CONTROLLER_BUTTON_X: ControllerInput.Y,
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: ControllerInput.L1,
    sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: ControllerInput.R1,
    sdl2.SDL_CONTROLLER_BUTTON_START: ControllerInput.START,
    sdl2.SDL_CONTROLLER_BUTTON_BACK: ControllerInput.SELECT,
}

_INPUT_EVENTS = (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP, sdl2.SDL_CONTROLLERBUTTONDOWN)


class DesktopQuit(SystemExit):
    """Raised when the window is closed or Esc is pressed."""

    def __init__(self) -> None:
        super().__init__(0)


class ScriptFinished(SystemExit):
    """Raised in headless mode when PyUI asks for input after the script ran out."""

    def __init__(self) -> None:
        super().__init__(0)


class DesktopControllerInterface(ControllerInterface):
    """Feeds PyUI from the keyboard, the first SDL game controller, or a script.

    With a script, scripted steps are consumed first; live input is ignored while they last.

    Args:
        script: Steps to replay, or ``None`` for interactive use.
        on_capture: Called with the capture name for each ``shot:`` step.
        exit_when_script_ends: Raise :class:`ScriptFinished` once the script is consumed
            (headless runs); otherwise fall back to live input.
    """

    def __init__(
        self,
        script: Iterable[Step] | None = None,
        on_capture: Callable[[str], None] | None = None,
        *,
        exit_when_script_ends: bool = False,
    ) -> None:
        self._script: deque[Step] = deque(script or ())
        self._scripted = bool(self._script)
        self._on_capture = on_capture
        self._exit_when_script_ends = exit_when_script_ends
        self._event = sdl2.SDL_Event()
        self._gamepad: ctypes.c_void_p | None = None
        self._held_key: int | None = None
        self._held_button: int | None = None
        self.init_controller()

    @property
    def unplayed(self) -> list[Step]:
        """Script steps not consumed yet, e.g. because the app exited before reaching them."""
        return list(self._script)

    def init_controller(self) -> None:
        """Open the first connected SDL game controller, if any."""
        sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_GAMECONTROLLER)
        for index in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(index):
                self._gamepad = sdl2.SDL_GameControllerOpen(index)
                logger.info("Gamepad: %s", sdl2.SDL_GameControllerName(self._gamepad))
                return

    def re_init_controller(self) -> None:
        """Re-scan for game controllers."""
        self.close()
        self.init_controller()

    def close(self) -> None:
        """Release the game controller."""
        if self._gamepad:
            sdl2.SDL_GameControllerClose(self._gamepad)
            self._gamepad = None

    def still_held_down(self) -> bool:
        """Report whether the last pressed key or button is still down (drives PyUI turbo).

        Returns:
            ``True`` while the last live key/button is held; always ``False`` for scripts.
        """
        if self._scripted:
            return False
        if self._held_key is not None:
            state = sdl2.SDL_GetKeyboardState(None)
            return bool(state[self._held_key])
        if self._held_button is not None and self._gamepad:
            return bool(sdl2.SDL_GameControllerGetButton(self._gamepad, self._held_button))
        return False

    def force_refresh(self) -> None:
        """Pump SDL events so key state queries are current."""
        sdl2.SDL_PumpEvents()

    def get_input(self, timeout: int) -> ControllerInput | None:
        """Return the next input, waiting up to ``timeout`` milliseconds for live input.

        Args:
            timeout: Maximum wait in milliseconds.

        Returns:
            The input, or ``None`` on timeout.

        Raises:
            DesktopQuit: The window was closed or Esc pressed.
            ScriptFinished: The script is consumed and ``exit_when_script_ends`` is set.
        """
        if self._scripted:
            return self._next_scripted(timeout)
        if not sdl2.SDL_WaitEventTimeout(ctypes.byref(self._event), max(timeout, 1)):
            return None
        return self._translate(self._event)

    def _next_scripted(self, timeout: int) -> ControllerInput | None:
        """Consume script steps up to and including the next button press.

        Args:
            timeout: PyUI's input timeout in milliseconds; a ``wait`` tick lasts this long, as
                an idle tick does on a device.

        Returns:
            The scripted input, or ``None`` once the script is consumed (interactive mode).

        Raises:
            ScriptFinished: The script is consumed and ``exit_when_script_ends`` is set.
        """
        while self._script:
            step = self._script.popleft()
            if isinstance(step, Wait):
                if step.ticks > 1:
                    self._script.appendleft(Wait(step.ticks - 1))
                time.sleep(max(timeout, 1) / 1000)
                return None  # one idle tick: PyUI redraws and our on_tick handlers run
            if isinstance(step, Capture):
                if self._on_capture is not None:
                    self._on_capture(step.name)
                continue
            if isinstance(step, Press):
                return ControllerInput[step.button]
        if self._exit_when_script_ends:
            raise ScriptFinished
        self._scripted = False
        return None

    def _translate(self, event: sdl2.SDL_Event) -> ControllerInput | None:
        """Map one SDL event to a PyUI input, tracking what is held.

        Args:
            event: Event just received from SDL.

        Returns:
            The mapped input, or ``None`` for events that are not inputs.

        Raises:
            DesktopQuit: For window close or Esc.
        """
        if event.type == sdl2.SDL_QUIT:
            raise DesktopQuit
        if event.type == sdl2.SDL_KEYDOWN and not event.key.repeat:
            scancode = event.key.keysym.scancode
            if scancode == sdl2.SDL_SCANCODE_ESCAPE:
                raise DesktopQuit
            mapped = KEYBOARD.get(scancode)
            if mapped is not None:
                self._held_key, self._held_button = scancode, None
            return mapped
        if event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
            mapped = GAMEPAD.get(event.cbutton.button)
            if mapped is not None:
                self._held_key, self._held_button = None, event.cbutton.button
            return mapped
        if event.type == sdl2.SDL_CONTROLLERDEVICEADDED and not self._gamepad:
            self.init_controller()
        return None

    def clear_input(self) -> None:
        """Forget the last event (PyUI calls this after consuming an input)."""
        self._event.type = 0

    def clear_input_queue(self) -> None:
        """Drop pending live input events; scripted steps are kept."""
        sdl2.SDL_PumpEvents()
        for event_type in _INPUT_EVENTS:
            sdl2.SDL_FlushEvent(event_type)

    def cache_last_event(self) -> None:
        """No-op: only needed by PyUI's SDL interface internals."""

    def restore_cached_event(self) -> None:
        """No-op: only needed by PyUI's SDL interface internals."""
