"""First-run setup: find the username, get the Web API key (keyboard or file), validate it."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cheevos.core.credentials import (
    looks_like_api_key,
    read_api_key,
    read_username,
    save_api_key,
)
from cheevos.core.sync.session import Credentials
from cheevos.platform.paths import Paths
from cheevos.ui import strings
from cheevos.ui.pyui import primitives as ui
from cheevos.ui.pyui.views import MenuItem, choose
from cheevos.ui.screens.common import busy, message

# (username, key) -> True (accepted), False (rejected), None (couldn't reach RA).
KeyValidator = Callable[[str, str], bool | None]


def untested_device_note(device: str, log: Path) -> None:
    """Say once that this device hasn't been tested yet, and how to report problems.

    Args:
        device: PyUI's device name, e.g. ``"TRIMUI_BRICK"``.
        log: The log file, relative to the SD card.
    """
    message(
        strings.UNTESTED_TITLE,
        [strings.UNTESTED_TEXT.format(device=device), strings.UNTESTED_REPORT.format(log=log)],
    )


def ensure_credentials(
    paths: Paths, validate: KeyValidator, icons: Callable[[str], Path]
) -> Credentials | None:
    """Return the account to use, asking for the API key if there is none yet.

    Args:
        paths: Device paths.
        validate: Checks a key with RA.
        icons: Returns a pixel icon path by name.

    Returns:
        Credentials, or ``None`` if setup cannot finish (no username, or the user exited).
    """
    username = read_username(paths)
    if not username:
        message(strings.SETUP, [strings.NO_USERNAME])
        return None
    key = read_api_key(paths)
    if key:
        return Credentials(username, key)
    key = _ask_for_key(paths, username, validate, icons)
    return Credentials(username, key) if key else None


def _ask_for_key(
    paths: Paths, username: str, validate: KeyValidator, icons: Callable[[str], Path]
) -> str | None:
    """Offer keyboard entry, the key file, or exit until a key is available.

    Args:
        paths: Device paths.
        username: RA username.
        validate: Checks a key with RA.
        icons: Returns a pixel icon path by name.

    Returns:
        The key, or ``None`` if the user exited.
    """
    hint = strings.KEY_FILE_HINT.format(path=paths.api_key_file.relative_to(paths.sdcard))
    items = [
        MenuItem(strings.KEY_ENTER, strings.KEY_ENTER_HINT, icons("sliders"), key="enter"),
        MenuItem(strings.KEY_FILE, hint, icons("info-box"), key="file"),
        MenuItem(
            strings.KEY_CHECK_AGAIN, strings.KEY_CHECK_AGAIN_HINT, icons("reload"), key="check"
        ),
        MenuItem(strings.EXIT, "", icons("lock"), key="exit"),
    ]
    message(strings.SETUP, [strings.KEY_NEEDED, strings.KEY_WHERE])
    while True:
        choice = choose(strings.SETUP, items)
        if choice is None or choice.item.key == "exit":
            return None
        if choice.item.key == "enter":
            key = enter_key(paths, username, validate)
        elif choice.item.key == "check":
            key = read_api_key(paths)
            if not key:
                message(strings.SETUP, [strings.KEY_FILE_MISSING.format(path=paths.api_key_file)])
        else:
            message(strings.KEY_FILE, [hint])
            key = None
        if key:
            return key


def enter_key(paths: Paths, username: str, validate: KeyValidator) -> str | None:
    """Type a key on the on-screen keyboard, validate it, and save it.

    A key that can't be verified because RA is unreachable is saved anyway; the next sync
    reports if RA rejects it.

    Args:
        paths: Device paths.
        username: RA username.
        validate: Checks a key with RA.

    Returns:
        The saved key, or ``None`` if cancelled, malformed or rejected.
    """
    entered = ui.ask_text(strings.KEY_PROMPT, secret=True)
    if entered is None:
        return None
    key = entered.strip()
    if not looks_like_api_key(key):
        message(strings.KEY_PROMPT, [strings.KEY_INVALID_FORMAT])
        return None
    busy(strings.KEY_PROMPT, strings.KEY_CHECKING)
    verdict = validate(username, key)
    if verdict is False:
        message(strings.KEY_PROMPT, [strings.KEY_REJECTED])
        return None
    save_api_key(paths, key)
    if verdict is None:
        message(strings.KEY_PROMPT, [strings.KEY_UNVERIFIED])
    return key
