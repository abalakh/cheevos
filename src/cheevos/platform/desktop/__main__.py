"""Run Cheevos screens on a desktop: ``python -m cheevos.platform.desktop``.

Interactive (window, keyboard/gamepad)::

    python -m cheevos.platform.desktop --res 640x480

Headless capture (scripted input, PNGs in ``build/screens/<WxH>/``)::

    python -m cheevos.platform.desktop --headless --res 752x560 --script "shot:home,down,shot:games"

Keyboard (RetroArch defaults): arrows = D-pad, X = A, Z = B, S = X, A = Y, Q/W = L1/R1,
1/2 = L2/R2, Enter = Start, Right Shift = Select, Esc = quit.
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

from cheevos.platform.desktop.script import ScriptError, Step, parse_script

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
        script: Scripted input steps (empty for interactive use).
        quit_after_script: Exit once the script is consumed (always true when headless).
        out_dir: Root directory for captured PNGs.
        pyui_dir: PyUI ``main-ui`` directory.
        themes_dir: Directory containing theme folders.
        sd_root: Fake SD-card root for configs, caches and saves.
        live: Use the real RetroAchievements API instead of recorded fixtures.
        verbose: Show PyUI's own log output.
    """

    width: int
    height: int
    theme: str
    headless: bool
    scale: int
    script: list[Step]
    quit_after_script: bool
    out_dir: Path
    pyui_dir: Path
    themes_dir: Path
    sd_root: Path
    live: bool
    verbose: bool


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

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        The runner options.
    """
    parser = argparse.ArgumentParser(prog="python -m cheevos.platform.desktop")
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
    try:
        script = parse_script(args.script)
    except ScriptError as exc:
        parser.error(str(exc))
    if args.headless and not script:
        parser.error("--headless needs --script (otherwise it would wait for input forever)")
    width, height = args.res
    return RunnerOptions(
        width=width,
        height=height,
        theme=args.theme,
        headless=args.headless,
        scale=1 if args.headless else args.scale,
        script=script,
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
    )


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


def run(options: RunnerOptions) -> int:
    """Bring up PyUI with the desktop device and run the app.

    Args:
        options: Runner options.

    Returns:
        Process exit code.
    """
    started_at = time.monotonic()
    if options.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_RENDER_DRIVER"] = "software"
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    # pysdl2-dll is exactly what the desktop should use; its import-time notice is noise.
    warnings.filterwarnings("ignore", message="Using SDL2 binaries from pysdl2-dll")

    from cheevos.ui.pyui import bootstrap

    pyui_logger = _configure_logging(verbose=options.verbose)
    bootstrap.add_pyui_to_path(options.pyui_dir)
    bootstrap.install_logger(pyui_logger)

    from cheevos.platform.desktop.capture import capture_frame
    from cheevos.platform.desktop.controller import DesktopControllerInterface
    from cheevos.platform.desktop.device import DesktopDevice
    from cheevos.platform.desktop.window import windowed

    shots_dir = options.out_dir / f"{options.width}x{options.height}"

    def on_capture(name: str) -> None:
        """Save the current frame as ``<shots_dir>/<name>.png``."""
        path = shots_dir / f"{name}.png"
        capture_frame(path)
        logger.info("Captured %s", path)

    controller = DesktopControllerInterface(
        options.script, on_capture, exit_when_script_ends=options.quit_after_script
    )
    setup = bootstrap.PyUiSetup(
        main_ui_dir=options.pyui_dir,
        config_path=_write_pyui_config(options),
        state_path=options.sd_root / "Saves" / "cheevos" / "pyui-state.json",
        theme=options.theme,
        user_config_path=options.sd_root / "Saves" / "pyui-common.json",
    )
    saves_dir = options.sd_root / "Saves"
    with windowed(options.width, options.height, options.scale):
        bootstrap.bootstrap(
            setup,
            lambda: DesktopDevice(
                options.width, options.height, saves_dir, options.pyui_dir, controller
            ),
        )
    from cheevos import app
    from cheevos.platform.desktop.environments import fixture_environment, live_environment

    env = (
        live_environment(options.sd_root) if options.live else fixture_environment(options.sd_root)
    )
    try:
        app.run(started_at=started_at, env=env)
    except SystemExit as exc:  # DesktopQuit / ScriptFinished end the run normally
        return int(exc.code or 0)
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
