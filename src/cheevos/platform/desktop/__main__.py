"""Run Cheevos screens on a desktop: ``python -m cheevos.platform.desktop``.

The app runs on PyUI's ``DESKTOP`` device, as it runs on a handheld's: PyUI provides the window,
keyboard, gamepad and scripted input, and the screenshots (SpruceOS
``App/PyUI/docs/desktop_readme.txt``). This module adds Cheevos' side: recorded fixtures or the
live API, the drills, and the command line.

Interactive (window, keyboard/gamepad)::

    python -m cheevos.platform.desktop --res 640x480

Headless capture (scripted input, PNGs in ``build/screens/<WxH>/``)::

    python -m cheevos.platform.desktop --headless --res 752x560 --script "shot:home,down,shot:games"

Keyboard (RetroArch layout plus Menu): arrows = D-pad, X = A, Z = B, S = X, A = Y, Q/W = L1/R1,
1/2 = L2/R2, Enter = Start, Right Shift = Select, M = Menu, F8 = screenshot, Esc = quit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from cheevos.platform.arguments import add_game_argument

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SPRUCE_CHECKOUT = _REPO_ROOT / ".spruceos"  # scripts/fetch_pyui.sh
_DEVICE = "DESKTOP"


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
    add_game_argument(parser)
    parser.add_argument("--res", type=_resolution, default=(640, 480), help="e.g. 640x480")
    parser.add_argument("--theme", default="SPRUCE")
    parser.add_argument("--headless", action="store_true", help="no window; use with --script")
    parser.add_argument("--scale", type=int, default=1, choices=(1, 2, 3), help="window zoom")
    parser.add_argument("--script", default="", help='e.g. "shot:home,down,a,shot:games"')
    parser.add_argument(
        "--quit-after-script", action="store_true", help="exit when the script is consumed"
    )
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / "build" / "screens")
    parser.add_argument("--verbose", action="store_true", help="show PyUI's log output")
    parser.add_argument(
        "--live", action="store_true", help="real RA API with dev/sdcard (default: fixtures)"
    )
    args = parser.parse_args(argv)
    if args.headless and not args.script.strip(", "):
        parser.error("--headless needs --script (otherwise it would wait for input forever)")
    width, height = args.res
    return RunnerOptions(
        width=width,
        height=height,
        theme=args.theme,
        headless=args.headless,
        scale=1 if args.headless else args.scale,
        script=args.script,
        quit_after_script=args.headless or args.quit_after_script,
        out_dir=args.out,
        pyui_dir=_env_path("CHEEVOS_PYUI_DIR", _SPRUCE_CHECKOUT / "App" / "PyUI" / "main-ui"),
        themes_dir=_env_path("CHEEVOS_THEMES_DIR", _SPRUCE_CHECKOUT / "Themes"),
        sd_root=_env_path(
            "CHEEVOS_SDCARD_ROOT",
            _REPO_ROOT / "dev" / ("sdcard" if args.live else "sdcard-fixtures"),
        ),
        live=args.live,
        verbose=args.verbose,
        game_id=args.game_id,
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
            f"PyUI at {options.pyui_dir} has no {_DEVICE} device (SpruceOS predates it); "
            "run `make pyui`"
        )
    from devices.desktop.desktop_options import DesktopOptions

    try:
        DesktopOptions.from_environ()
    except ValueError as exc:  # also a malformed script (ScriptError)
        return str(exc)
    return None


def run(options: RunnerOptions) -> int:
    """Bring up PyUI on its desktop device and run the app.

    Args:
        options: Runner options.

    Returns:
        Process exit code.
    """
    started_at = time.monotonic()
    os.environ.update(desktop_environment(options))
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    # pysdl2-dll is exactly what the desktop should use; its import-time notice is noise.
    warnings.filterwarnings("ignore", message="Using SDL2 binaries from pysdl2-dll")

    from cheevos.ui.pyui import bootstrap

    pyui_logger = _configure_logging(verbose=options.verbose)
    bootstrap.add_pyui_to_path(options.pyui_dir)
    bootstrap.install_logger(pyui_logger)
    if problem := _check_desktop_device(options):
        logger.error("%s", problem)
        return 2

    setup = bootstrap.PyUiSetup(
        main_ui_dir=options.pyui_dir,
        config_path=_write_pyui_config(options),
        state_path=options.sd_root / "Saves" / "cheevos" / "pyui-state.json",
        theme=options.theme,
        user_config_path=options.sd_root / "Saves" / "pyui-common.json",
    )
    bootstrap.bootstrap(setup, lambda: bootstrap.pyui_device(_DEVICE))
    from cheevos import app
    from cheevos.platform.desktop.environments import fixture_environment, live_environment

    env = (
        live_environment(options.sd_root) if options.live else fixture_environment(options.sd_root)
    )
    try:
        app.run(started_at=started_at, env=env, game_id=options.game_id)
    except SystemExit as exc:  # Esc, closing the window, or the end of a headless script
        return int(exc.code or 0)
    return _check_script_finished()


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
