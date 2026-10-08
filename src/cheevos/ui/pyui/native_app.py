"""Expose Cheevos as a native PyUI Apps entry with imports preloaded after a menu frame.

Spruce integration calls ``append_entry`` from AppMenu and ``preload_after_next_frame``
after main-menu construction. Neither call initializes a second PyUI runtime.
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cheevos.platform.paths import Paths
from cheevos.ui import strings

if TYPE_CHECKING:
    from cheevos.app import AppEnvironment

logger = logging.getLogger(__name__)
_preload_scheduled = False


def append_entry(app_list: list[Any], *, show_all_apps: bool = False) -> None:
    """Append Cheevos to the native Apps list, respecting PyUI hiding.

    Args:
        app_list: PyUI's mutable list of Apps entries.
        show_all_apps: Whether hidden apps are currently shown in the host menu.
    """
    from apps.pyui_app import PyUiAppConfig
    from menus.app.app_utils import AppUtils
    from menus.app.hidden_apps_manager import AppsManager
    from menus.language.language import Language
    from views.grid_or_list_entry import GridOrListEntry

    config = PyUiAppConfig(strings.APP_TITLE)
    hidden = AppsManager.is_hidden(config)
    if hidden and not show_all_apps:
        return
    # PyUI's theme override takes priority over the packaged icon.
    icon_folder = Path(__file__).resolve().parents[2] / "res"
    icon = AppUtils.get_icon(str(icon_folder), "cheevos.png")
    app_list.append(
        GridOrListEntry(
            primary_text=config.get_label() + (strings.APP_HIDDEN_SUFFIX if hidden else ""),
            image_path=icon,
            image_path_selected=icon,
            description=Language.label("cheevosDesc", strings.APP_DESCRIPTION),
            icon=icon,
            extra_data=config,
            value=run,
        )
    )


def preload_after_next_frame() -> None:
    """Start background imports after the next completed menu frame, once per process.

    Call on PyUI's UI thread after startup/helper modes have finished and immediately before
    entering the main menu loop. The wrapper restores the exact display descriptor before
    starting the import worker; all session setup and SDL work remain on the UI thread.
    """
    from display.display import Display

    global _preload_scheduled  # noqa: PLW0603 — one frame hook per host process
    if _preload_scheduled:
        return
    _preload_scheduled = True
    descriptor = vars(Display)["present"]
    present = Display.present

    def first_menu_frame() -> None:
        """Restore the renderer and begin imports after the menu is visible."""
        present()
        Display.present = descriptor
        threading.Thread(target=_preload, name="cheevos-preload", daemon=True).start()

    Display.present = staticmethod(first_menu_frame)


def _preload() -> None:
    """Import app code without creating session resources or calling PyUI."""
    try:
        importlib.import_module("cheevos.app")
    except Exception:
        logger.exception("Cheevos preload failed")


def run(env: AppEnvironment | None = None) -> int:
    """Open Cheevos on the UI thread, with an optional fixture environment for tests."""
    started_at = time.monotonic()
    from cheevos import app

    return app.run(started_at=started_at, env=env or app.AppEnvironment(Paths.from_env()))
