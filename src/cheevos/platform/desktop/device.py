"""A PyUI device that runs on a desktop window instead of handheld hardware."""

from __future__ import annotations

import abc
import logging
import types
from collections.abc import Callable
from pathlib import Path

from controller.controller_interface import ControllerInterface
from devices.charge.charge_status import ChargeStatus
from devices.device_common import DeviceCommon

logger = logging.getLogger(__name__)

# Seed for the device's system config; any Spruce device JSON works, this one ships with PyUI.
_SYSTEM_CONFIG_SEED = Path("devices/miyoo/mini/mini-flip-system.json")


def _noop_method(name: str) -> Callable[..., None]:
    """Build a stand-in for a hardware method the desktop cannot provide.

    Args:
        name: Method name, used for the debug log.

    Returns:
        A method that logs the call once at debug level and returns ``None``.
    """
    seen = False

    def method(self: object, *args: object, **kwargs: object) -> None:
        """Do nothing; log the first call."""
        nonlocal seen
        if not seen:
            seen = True
            logger.debug("Desktop device: no-op %s()", name)

    method.__name__ = name
    return method


class DesktopDevice(DeviceCommon):
    """PyUI device backed by a desktop window.

    Hardware features (battery, Wi-Fi, volume, power, launching games) are stubbed. Abstract
    methods are filled with no-ops by :func:`_fill_abstract_methods`, and unknown device
    methods PyUI calls duck-typed (it calls some that are not on ``AbstractDevice``) resolve to
    no-ops through ``__getattr__``, so the shim keeps working as PyUI grows.

    Args:
        width: Logical screen width in pixels.
        height: Logical screen height in pixels.
        saves_dir: Directory for PyUI's state and system config files.
        main_ui_dir: PyUI's ``main-ui`` directory (to seed the system config).
        controller: Input source handed to PyUI.
    """

    def __init__(
        self,
        width: int,
        height: int,
        saves_dir: Path,
        main_ui_dir: Path,
        controller: ControllerInterface,
    ) -> None:
        self._width = width
        self._height = height
        self._saves_dir = saves_dir
        self._controller = controller
        saves_dir.mkdir(parents=True, exist_ok=True)
        self._load_system_config(
            str(saves_dir / "desktop-system.json"), main_ui_dir / _SYSTEM_CONFIG_SEED
        )
        super().__init__()

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Resolve device methods PyUI calls that this shim does not define.

        Args:
            name: Attribute name that normal lookup did not find.

        Returns:
            A bound no-op method.

        Raises:
            AttributeError: For dunder and private names, so Python protocols work normally.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return types.MethodType(_noop_method(name), self)

    def screen_width(self) -> int:
        """Return the logical screen width."""
        return self._width

    def screen_height(self) -> int:
        """Return the logical screen height."""
        return self._height

    def output_screen_width(self) -> int:
        """Return the output width (same as logical: no HDMI scaling on desktop)."""
        return self._width

    def output_screen_height(self) -> int:
        """Return the output height (same as logical: no HDMI scaling on desktop)."""
        return self._height

    def should_scale_screen(self) -> bool:
        """Report that the canvas is shown unscaled."""
        return False

    def get_device_name(self) -> str:
        """Return the device name PyUI uses for ``devices`` filters."""
        return "DESKTOP"

    def get_state_path(self) -> str:
        """Return the PyUI state file path inside the desktop saves directory."""
        return str(self._saves_dir / "pyui-state.json")

    def get_controller_interface(self) -> ControllerInterface:
        """Return the desktop input source."""
        return self._controller

    def get_battery_percent(self) -> int:
        """Return a fixed battery level for the top bar."""
        return 87

    def get_charge_status(self) -> ChargeStatus:
        """Report a discharging battery for the top bar."""
        return ChargeStatus.DISCONNECTED

    def supports_wifi(self) -> bool:
        """Hide the Wi-Fi indicator."""
        return False

    def is_wifi_enabled(self) -> bool:
        """Report Wi-Fi as disabled."""
        return False


def _fill_abstract_methods(cls: type) -> type:
    """Replace every remaining abstract method of ``cls`` with a no-op so it can be instantiated.

    Args:
        cls: Class whose abstract methods should be stubbed.

    Returns:
        The same class, now concrete.
    """
    for name in getattr(cls, "__abstractmethods__", frozenset()):
        setattr(cls, name, _noop_method(name))
    abc.update_abstractmethods(cls)
    return cls


_fill_abstract_methods(DesktopDevice)
