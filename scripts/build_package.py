"""Assemble the device package: ``dist/App/Cheevos/`` (extract over the SD card root).

Contents: ``config.json``, ``launch.sh``, ``icon.png`` (when present) and the ``cheevos``
package without the dev-only desktop shim and caches.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = REPO / "src" / "cheevos"
APP_FILES = REPO / "app"
OUTPUT = REPO / "dist" / "App" / "Cheevos"
EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", "desktop")


def build(output: Path = OUTPUT) -> Path:
    """Build the package directory from scratch.

    Args:
        output: Destination ``App/Cheevos`` directory; it is replaced if it exists.

    Returns:
        The output directory.
    """
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for item in sorted(APP_FILES.iterdir()):
        shutil.copy2(item, output / item.name)
    (output / "launch.sh").chmod(0o755)
    shutil.copytree(SOURCE_PACKAGE, output / "cheevos", ignore=EXCLUDED)
    return output


def main() -> int:
    """Build the package and print where it went.

    Returns:
        Process exit code.
    """
    output = build()
    files = sum(1 for path in output.rglob("*") if path.is_file())
    print(f"Built {output.relative_to(REPO)} ({files} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
