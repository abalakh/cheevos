"""Render the screenshots used in the wiki (``docs/images/``) from the showcase drill.

The showcase drill (``CHEEVOS_SIMULATE=showcase``) serves the recorded fixtures with assorted
progress, awards and a made-up account, so the pictures show every kind of progress bar and no
real player. Screens of other themes are added when those themes have been copied into
``dev/themes/`` (see ``TESTING.md``).

Usage: ``uv run python scripts/doc_screens.py`` (or ``make doc-screens``)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "images"
THEMES = REPO / "dev" / "themes"
# Sort the games list by completion (Y > Sort > Completion), so every kind of bar is on screen.
BY_COMPLETION = "y,down,a,down,down,down,a"

# (resolution, theme, script). Shot names become the image file names.
RUNS: list[tuple[str, str | None, str]] = [
    (
        "640x480",
        None,
        ",".join(
            [
                "shot:home",
                "a,shot:profile,x,down,down,down,down,down,down,shot:profile-more,b",
                f"down,a,{BY_COMPLETION},shot:games,select,shot:games-details,select",
                "down,down,a,shot:game,select,shot:game-grid,select",
                "down,a,shot:achievement,a,shot:fullscreen,b,b,b,b",
                "down,a,shot:recent,b",
                "down,a,shot:awards,b",
                "down,a,shot:settings,b",
                "up,up,up,up,start,shot:syncing",
            ]
        ),
    ),
    ("1280x720", None, f"down,a,{BY_COMPLETION},shot:games-1280x720"),
    ("640x480", "MINIMAL", f"down,a,{BY_COMPLETION},shot:theme-minimal"),
    ("640x480", "Pico-8", f"down,a,{BY_COMPLETION},shot:theme-pico-8"),
]


def render(resolution: str, theme: str | None, script: str, out: Path) -> list[Path]:
    """Run one headless walk-through of the showcase drill.

    Args:
        resolution: E.g. ``"640x480"``.
        theme: Theme name from ``dev/themes``, or ``None`` for the bundled SPRUCE theme.
        script: Desktop runner script.
        out: Capture directory.

    Returns:
        The captured images.
    """
    env = {**os.environ, "CHEEVOS_SIMULATE": "showcase"}
    command = [sys.executable, "-m", "cheevos.platform.desktop", "--headless"]
    command += ["--res", resolution, "--script", script, "--out", str(out)]
    if theme is not None:
        env["CHEEVOS_THEMES_DIR"] = str(THEMES)
        command += ["--theme", theme]
    subprocess.run(command, env=env, check=True, capture_output=True)  # noqa: S603 — fixed argv
    return sorted((out / resolution).glob("*.png"))


def main() -> int:
    """Render every run and copy the images into ``docs/images``.

    Returns:
        Process exit code.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    for resolution, theme, script in RUNS:
        if theme is not None and not (THEMES / theme).is_dir():
            print(f"Skipping {theme}: copy it from a device into dev/themes/ first")
            continue
        with tempfile.TemporaryDirectory() as scratch:
            for image in render(resolution, theme, script, Path(scratch)):
                shutil.copyfile(image, OUT / image.name)
                print(f"{OUT.relative_to(REPO) / image.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
