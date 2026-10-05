"""Headless smoke test of the desktop runner (needs a SpruceOS checkout for PyUI)."""

import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PYUI_DIR = Path(os.environ.get("CHEEVOS_PYUI_DIR", REPO / ".spruceos/App/PyUI/main-ui"))

pytestmark = [
    pytest.mark.screens,
    pytest.mark.skipif(not (PYUI_DIR / "mainui.py").is_file(), reason="no PyUI checkout"),
]


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


@pytest.mark.parametrize("res", ["640x480", "752x560", "1280x720"])
def test_headless_capture_and_navigation(tmp_path, res):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cheevos.platform.desktop",
            "--headless",
            "--res",
            res,
            "--script",
            "shot:first,down,shot:second",
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, "CHEEVOS_SDCARD_ROOT": str(tmp_path / "sdcard")},
    )
    assert result.returncode == 0, result.stderr
    first, second = tmp_path / res / "first.png", tmp_path / res / "second.png"
    width, height = (int(v) for v in res.split("x"))
    assert png_size(first) == (width, height)
    assert png_size(second) == (width, height)
    assert first.read_bytes() != second.read_bytes(), "moving down should change the frame"
