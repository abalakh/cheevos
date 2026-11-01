"""Run Cheevos screens on a desktop: ``python -m cheevos.platform.desktop``.

The app runs on PyUI's ``DESKTOP`` device, as it runs on a handheld's: PyUI provides the window,
keyboard, gamepad and scripted input, and the screenshots (SpruceOS
``App/PyUI/docs/desktop_readme.txt``). This module adds Cheevos' side: recorded fixtures or the
live API, the drills, and the command line.

Interactive (window, keyboard/gamepad)::

    python -m cheevos.platform.desktop --res 640x480

Headless capture (scripted input, PNGs in ``build/screens/<WxH>/``)::

    python -m cheevos.platform.desktop --headless --res 752x560 --script "shot:home,down,shot:games"

In another language (a translation in ``res/lang``, or the generated ``Pseudo``; PNGs in
``build/screens/<Language>/<WxH>/``)::

    python -m cheevos.platform.desktop --lang Ukrainian

Keyboard (RetroArch layout plus Menu): arrows = D-pad, X = A, Z = B, S = X, A = Y, Q/W = L1/R1,
1/2 = L2/R2, Enter = Start, Right Shift = Select, M = Menu, F8 = screenshot, Esc = quit.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cheevos.platform.desktop import pyui_setup, translations
from cheevos.ui import language

if TYPE_CHECKING:
    from cheevos.app import AppEnvironment

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SPRUCE_CHECKOUT = _REPO_ROOT / ".spruceos"  # scripts/fetch_pyui.sh


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Parsed command-line options for the desktop runner.

    Attributes:
        width: Logical screen width.
        height: Logical screen height.
        theme: Theme folder name.
        headless: Render with SDL's dummy video driver (no window).
        scale: Integer zoom for the desktop window (ignored when headless).
        script: Scripted input, e.g. ``"shot:home,down,shot:games"`` (empty for interactive use).
        quit_after_script: Exit once the script is consumed (always true when headless).
        out_dir: Root directory for captured PNGs.
        pyui_dir: PyUI ``main-ui`` directory.
        themes_dir: Directory containing theme folders.
        sd_root: Fake SD-card root for configs, caches and saves.
        live: Use the real RetroAchievements API instead of recorded fixtures.
        verbose: Show PyUI's own log output.
        game_id: Optional target for a game-only session launched from Spruce.
        clock: Time the top bar shows instead of the time of day, for screenshots that only
            change when the screens do.
        language: Show the app (and PyUI) in this language instead of English: a translation
            in ``res/lang``, or the generated pseudo-language.
    """

    width: int
    height: int
    theme: str
    headless: bool
    scale: int
    script: str
    quit_after_script: bool
    out_dir: Path
    pyui_dir: Path
    themes_dir: Path
    sd_root: Path
    live: bool
    verbose: bool
    game_id: int | None = None
    clock: dt.time | None = None
    language: str | None = None


def _resolution(text: str) -> tuple[int, int]:
    """Parse ``"640x480"`` into ``(640, 480)``.

    Args:
        text: Resolution as ``WIDTHxHEIGHT``.

    Returns:
        Width and height.

    Raises:
        argparse.ArgumentTypeError: If the text is not a valid resolution.
    """
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {text!r}") from exc
    return width, height


def _time_of_day(text: str) -> dt.time:
    """Parse ``"10:30"`` into a time of day.

    Args:
        text: Time as ``HH:MM`` (24-hour).

    Returns:
        The time.

    Raises:
        argparse.ArgumentTypeError: If the text is not a valid time.
    """
    try:
        return dt.time.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {text!r}") from exc


def _game_id(text: str) -> int:
    """Parse a positive RA game ID.

    Args:
        text: The ID as typed.

    Returns:
        The ID.

    Raises:
        argparse.ArgumentTypeError: If it is not a positive integer.
    """
    try:
        parsed = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive game ID") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive game ID")
    return parsed


def _env_path(name: str, default: Path) -> Path:
    """Return the path in environment variable ``name``, or ``default``.

    Args:
        name: Environment variable name.
        default: Fallback path.

    Returns:
        The resolved path.
    """
    value = os.environ.get(name)
    return Path(value) if value else default


def parse_options(argv: list[str] | None = None) -> RunnerOptions:
    """Parse command-line arguments.

    The script itself is checked by PyUI's desktop device, once PyUI is importable.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        The runner options.
    """
    parser = argparse.ArgumentParser(prog="python -m cheevos.platform.desktop")
    parser.add_argument(
        "--game-id",
        type=_game_id,
        help="open this RA game only, as Spruce's game menu does",
    )
    parser.add_argument("--res", type=_resolution, default=(640, 480), help="e.g. 640x480")
    parser.add_argument("--theme", default="SPRUCE")
    parser.add_argument("--headless", action="store_true", help="no window; use with --script")
    parser.add_argument("--scale", type=int, default=1, choices=(1, 2, 3), help="window zoom")
    parser.add_argument("--script", default="", help='e.g. "shot:home,down,a,shot:games"')
    parser.add_argument(
        "--quit-after-script", action="store_true", help="exit when the script is consumed"
    )
    parser.add_argument(
        "--lang",
        metavar="LANGUAGE",
        help=f'a translation in res/lang, e.g. "Ukrainian", or "{translations.PSEUDO}"',
    )
    parser.add_argument(
        "--out", type=Path, help="screenshots (default: build/screens[/<LANGUAGE>])"
    )
    parser.add_argument("--verbose", action="store_true", help="show PyUI's log output")
    parser.add_argument(
        "--clock", type=_time_of_day, help="top-bar time, e.g. 10:30 (default: the time of day)"
    )
    parser.add_argument(
        "--live", action="store_true", help="real RA API with dev/sdcard (default: fixtures)"
    )
    args = parser.parse_args(argv)
    if args.headless and not args.script.strip(", "):
        parser.error("--headless needs --script (otherwise it would wait for input forever)")
    width, height = args.res
    lang = None if args.lang in (None, "", language.ENGLISH) else args.lang
    screens = _REPO_ROOT / "build" / "screens"
    return RunnerOptions(
        width=width,
        height=height,
        theme=args.theme,
        headless=args.headless,
        scale=1 if args.headless else args.scale,
        script=args.script,
        quit_after_script=args.headless or args.quit_after_script,
        out_dir=args.out or (screens / lang if lang else screens),
        pyui_dir=_env_path("CHEEVOS_PYUI_DIR", _SPRUCE_CHECKOUT / "App" / "PyUI" / "main-ui"),
        themes_dir=_env_path("CHEEVOS_THEMES_DIR", _SPRUCE_CHECKOUT / "Themes"),
        sd_root=_env_path(
            "CHEEVOS_SDCARD_ROOT",
            _REPO_ROOT / "dev" / ("sdcard" if args.live else "sdcard-fixtures"),
        ),
        live=args.live,
        verbose=args.verbose,
        game_id=args.game_id,
        clock=args.clock,
        language=lang,
    )


def desktop_environment(options: RunnerOptions) -> dict[str, str]:
    """Return the ``PYUI_DESKTOP_*`` variables that configure PyUI's desktop device.

    Args:
        options: Runner options.

    Returns:
        Variable names and values.
    """
    return {
        "PYUI_DESKTOP_RES": f"{options.width}x{options.height}",
        "PYUI_DESKTOP_SCALE": str(options.scale),
        "PYUI_DESKTOP_HEADLESS": "1" if options.headless else "",
        "PYUI_DESKTOP_SCRIPT": options.script,
        "PYUI_DESKTOP_EXIT_AFTER_SCRIPT": "1" if options.quit_after_script else "",
        # Where PyUI writes (its device config): the fake card, as before the device moved.
        "PYUI_DESKTOP_DATA": str(options.sd_root),
        "PYUI_DESKTOP_SHOTS": str(options.out_dir / f"{options.width}x{options.height}"),
    }


def _write_pyui_config(options: RunnerOptions) -> Path:
    """Write the PyUI config that points PyUI at the themes directory.

    Args:
        options: Runner options.

    Returns:
        Path of the written config file.
    """
    config_path = options.sd_root / "Saves" / "pyui-config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {"theme": options.theme, "themeDir": f"{options.themes_dir}{os.sep}"}
    if options.language not in (None, translations.PSEUDO):
        config["language"] = options.language  # PyUI's own text too; the app follows it
    config_path.write_text(json.dumps(config, indent=4), encoding="utf-8")
    return config_path


def _configure_logging(*, verbose: bool) -> logging.Logger:
    """Send logs to stderr and create the logger that receives PyUI's records.

    Args:
        verbose: Show PyUI's info-level messages (otherwise warnings and above only).

    Returns:
        The logger to inject into PyUI.
    """
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    pyui_logger = logging.getLogger("cheevos.pyui")
    pyui_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    return pyui_logger


def _check_desktop_device(options: RunnerOptions) -> str | None:
    """Check that PyUI has a desktop device and accepts the options.

    Call after PyUI is on ``sys.path``.

    Args:
        options: Runner options.

    Returns:
        What is wrong, or ``None`` when the device can start.
    """
    if not (options.pyui_dir / "devices" / "desktop").is_dir():
        return (
            f"PyUI at {options.pyui_dir} has no {pyui_setup.DEVICE} device (SpruceOS predates it); "
            "run `make pyui`"
        )
    from devices.desktop.desktop_options import DesktopOptions

    try:
        DesktopOptions.from_environ()
    except ValueError as exc:  # also a malformed script (ScriptError)
        return str(exc)
    return None


def _fix_top_bar_clock(shown: dt.time) -> None:
    """Make PyUI's top bar show ``shown`` instead of the time of day.

    Only the time PyUI reads is replaced: it still formats it as the user config asks (12 or
    24 hours, AM/PM). Call after PyUI is on ``sys.path``.

    Args:
        shown: Time to show.
    """
    from menus.common import top_bar

    day = dt.date(2026, 1, 1)  # the top bar shows no date

    class FixedDatetime(dt.datetime):
        """``datetime`` whose current time is always ``shown``."""

        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> FixedDatetime:
            """Return the fixed time."""
            return cls.combine(day, shown)

        @classmethod
        def fromtimestamp(cls, timestamp: float, /, tz: dt.tzinfo | None = None) -> FixedDatetime:
            """Return the fixed time, whatever the timestamp."""
            return cls.combine(day, shown)

    if getattr(top_bar, "datetime", None) is not dt.datetime:
        logger.warning("PyUI's top bar no longer reads datetime; --clock has no effect")
    top_bar.datetime = FixedDatetime


def check_language(name: str | None) -> str | None:
    """Check that the app has a translation for a language.

    Args:
        name: The language, or ``None`` for English.

    Returns:
        What is wrong, or ``None``.
    """
    if name in (None, translations.PSEUDO) or (language.LANG_DIR / f"{name}.json").is_file():
        return None
    available = sorted(path.stem for path in language.LANG_DIR.glob("*.json"))
    return (
        f"No translation at {language.LANG_DIR / f'{name}.json'}. Translations: "
        f"{', '.join([*available, translations.PSEUDO])} (the name is PyUI's file name for it)"
    )


def _app_environment(options: RunnerOptions) -> AppEnvironment:
    """Create the app's environment: recorded fixtures or the live API, in the chosen language.

    Args:
        options: Runner options.

    Returns:
        The environment.
    """
    from cheevos.platform.desktop.environments import fixture_environment, live_environment

    sd_root = options.sd_root
    env = live_environment(sd_root) if options.live else fixture_environment(sd_root)
    if options.language != translations.PSEUDO:
        return env  # PyUI's language, which the PyUI config sets
    lang_dir = sd_root / "Saves" / "cheevos" / "lang"
    translations.write(lang_dir, translations.PSEUDO, translations.pseudo())
    return dataclasses.replace(env, language=translations.PSEUDO, lang_dir=lang_dir)


def run(options: RunnerOptions) -> int:
    """Bring up PyUI on its desktop device and run the app.

    Args:
        options: Runner options.

    Returns:
        Process exit code.
    """
    started_at = time.monotonic()
    if problem := check_language(options.language) or start_pyui(options):
        logger.error("%s", problem)
        return 2
    from cheevos import native

    try:
        native.session(_app_environment(options), started_at=started_at, game_id=options.game_id)
    except SystemExit as exc:  # Esc, closing the window, or the end of a headless script
        return int(exc.code or 0)
    return _check_script_finished()


def start_pyui(options: RunnerOptions) -> str | None:
    """Bring up PyUI on its desktop device, as PyUI's launcher would before opening the app.

    Args:
        options: Runner options.

    Returns:
        Why PyUI can't start, or ``None`` once it is up.
    """
    os.environ.update(desktop_environment(options))
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    # pysdl2-dll is exactly what the desktop should use; its import-time notice is noise.
    warnings.filterwarnings("ignore", message="Using SDL2 binaries from pysdl2-dll")

    pyui_logger = _configure_logging(verbose=options.verbose)
    pyui_setup.add_pyui_to_path(options.pyui_dir)
    pyui_setup.install_logger(pyui_logger)
    if problem := _check_desktop_device(options):
        return problem

    setup = pyui_setup.PyUiSetup(
        main_ui_dir=options.pyui_dir,
        config_path=_write_pyui_config(options),
        state_path=options.sd_root / "Saves" / "cheevos" / "pyui-state.json",
        theme=options.theme,
        user_config_path=options.sd_root / "Saves" / "pyui-common.json",
    )
    pyui_setup.start(setup)
    if options.clock is not None:
        _fix_top_bar_clock(options.clock)
    return None


def _check_script_finished() -> int:
    """Fail the run if the app exited before its script ended.

    Returns:
        Process exit code: 1 if script steps were left, else 0.
    """
    from devices.desktop.desktop_script import Capture
    from devices.device import Device

    if unplayed := Device.get_device().get_controller_interface().unplayed:
        # Usually a B too many: the script drifted from the screens and left the app early.
        captures = [step.name for step in unplayed if isinstance(step, Capture)]
        logger.error(
            "The app exited with %d script steps left; captures not taken: %s",
            len(unplayed),
            ", ".join(captures) or "none",
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Process exit code.
    """
    return run(parse_options(argv))


if __name__ == "__main__":
    sys.exit(main())
