"""Assemble the device package: ``dist/App/Cheevos/`` and ``dist/Cheevos-<version>.zip``.

Contents: ``config.json``, ``launch.sh``, ``cheevos.png`` and the ``cheevos`` package without
the dev-only desktop shim and caches. The zip holds ``App/Cheevos/``, so it extracts to the SD
card root; the release job in ``.github/workflows/ci.yml`` publishes it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from cheevos import __version__

REPO = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = REPO / "src" / "cheevos"
APP_FILES = REPO / "app"
DIST = REPO / "dist"
OUTPUT = DIST / "App" / "Cheevos"
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


def archive(package: Path = OUTPUT, version: str = __version__) -> Path:
    """Zip the package directory with its ``App/Cheevos/`` prefix.

    Args:
        package: The built ``App/Cheevos`` directory.
        version: Version for the file name.

    Returns:
        The zip file, next to the ``App`` directory.
    """
    sd_root = package.parents[1]
    base = sd_root / f"Cheevos-{version}"
    return Path(shutil.make_archive(str(base), "zip", sd_root, package.relative_to(sd_root)))


def main() -> int:
    """Build the package and print where it went.

    Returns:
        Process exit code.
    """
    output = build()
    files = sum(1 for path in output.rglob("*") if path.is_file())
    print(f"Built {output.relative_to(REPO)} ({files} files)")
    print(f"Built {archive(output).relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
