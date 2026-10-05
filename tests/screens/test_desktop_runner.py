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


def run_headless(tmp_path: Path, script: str, res: str = "640x480") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cheevos.platform.desktop",
            "--headless",
            "--res",
            res,
            "--script",
            script,
            "--out",
            str(tmp_path / "shots"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, "CHEEVOS_SDCARD_ROOT": str(tmp_path / "sdcard")},
    )


@pytest.mark.parametrize("res", ["640x480", "752x560", "1280x720"])
def test_headless_capture_and_navigation(tmp_path, res):
    result = run_headless(tmp_path, "shot:first,down,shot:second", res)
    assert result.returncode == 0, result.stderr
    first, second = tmp_path / "shots" / res / "first.png", tmp_path / "shots" / res / "second.png"
    width, height = (int(v) for v in res.split("x"))
    assert png_size(first) == (width, height)
    assert png_size(second) == (width, height)
    assert first.read_bytes() != second.read_bytes(), "moving down should change the frame"


def test_app_exit_before_script_end_fails(tmp_path):
    # B on the home screen quits the app, so the capture after it never happens.
    result = run_headless(tmp_path, "b,shot:never")
    assert result.returncode == 1
    assert "captures not taken: never" in result.stderr
