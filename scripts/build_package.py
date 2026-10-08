"""Package native Cheevos for PyUI with its upstream integration patch."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from cheevos import __version__

REPO = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = REPO / "src" / "cheevos"
DIST = REPO / "dist"
OUTPUT = DIST / "App" / "PyUI" / "main-ui" / "cheevos"
EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", "desktop", "bootstrap.py")


def build(output: Path = OUTPUT) -> Path:
    """Build the native package directory from scratch.

    Args:
        output: Destination ``App/PyUI/main-ui/cheevos`` directory; replaced if it exists.

    Returns:
        The output directory.
    """
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(SOURCE_PACKAGE, output, ignore=EXCLUDED)
    shutil.copy2(REPO / "app" / "cheevos.png", output / "res" / "cheevos.png")
    shutil.copy2(REPO / "LICENSE", output / "LICENSE")
    return output


def archive(package: Path = OUTPUT, version: str = __version__) -> Path:
    """Zip the package with SD-card-relative paths, an install note and the PyUI patch.

    Args:
        package: The built ``App/PyUI/main-ui/cheevos`` directory.
        version: Version for the file name.

    Returns:
        The zip file in ``dist``.
    """
    dist = package.parents[3]
    destination = dist / f"Cheevos-{version}.zip"
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as release:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                release.write(path, path.relative_to(dist))
        release.write(REPO / "integration" / "README.md", "README.md")
        release.write(REPO / "integration" / "spruceos-pyui.patch", "spruceos-pyui.patch")
    return destination


def main() -> int:
    """Build the package and print where it went.

    Returns:
        Process exit code.
    """
    output = build()
    print(f"Built {output.relative_to(REPO)}")
    print(f"Built {archive(output).relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
