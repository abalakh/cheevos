"""Headless walk-throughs of the real app on fixtures, including failure drills.

Renders every main screen; asserts the run is clean and each capture exists at the right size.
The PNGs are for human review (CI uploads them), not pixel-golden comparisons.
"""

import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PYUI_DIR = Path(os.environ.get("CHEEVOS_PYUI_DIR", REPO / ".spruceos/App/PyUI/main-ui"))

pytestmark = [
    pytest.mark.screens,
    pytest.mark.skipif(not (PYUI_DIR / "mainui.py").is_file(), reason="no PyUI checkout"),
]

WALKTHROUGH = (
    "shot:home,a,shot:profile,b,down,a,shot:games,select,shot:games_details,select,"
    "y,shot:games_options,b,"
    "down,a,shot:game,y,a,down,a,shot:game_grid,select,shot:game_list,b,b,down,a,shot:recent,b,"
    "down,a,shot:awards,a,down,a,shot:settings,down,down,down,down,down,down,down,down,a,"
    "shot:about"
)


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


def png_rows(path: Path, count: int) -> tuple[int, list[bytes]]:
    """Decode the first ``count`` rows of an 8-bit RGB or RGBA PNG (as SDL_image saves them)."""
    data, pos, idat = path.read_bytes(), 8, b""
    width = bpp = 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, _height, depth, color = struct.unpack(">IIBB", body[:10])
            assert depth == 8
            assert color in (2, 6)
            bpp = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw, stride = zlib.decompress(idat), width * bpp
    rows, previous = [], bytes(stride)
    for y in range(count):
        kind, line = (
            raw[y * (stride + 1)],
            bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)]),
        )
        for i in range(stride):
            a, b = line[i - bpp] if i >= bpp else 0, previous[i]
            c = previous[i - bpp] if i >= bpp else 0
            p = a + b - c
            predictor = [0, a, b, (a + b) // 2, min((a, b, c), key=lambda v: abs(p - v))][kind]
            line[i] = (line[i] + predictor) & 0xFF
        rows.append(bytes(line))
        previous = rows[-1]
    return bpp, rows


def gold_pixels(path: Path, top: int) -> int:
    """Count RA-gold pixels (an award dot) in the top ``top`` rows of a screenshot."""
    bpp, rows = png_rows(path, top)
    return sum(
        1
        for row in rows
        for x in range(0, len(row), bpp)
        if row[x] > 235 and 195 < row[x + 1] < 235 and row[x + 2] < 30
    )


def run_app(tmp_path: Path, script: str, *, res: str = "640x480", simulate: str = "") -> str:
    env = {**os.environ, "CHEEVOS_SDCARD_ROOT": str(tmp_path / "sdcard")}
    if simulate:
        env["CHEEVOS_SIMULATE"] = simulate
    result = subprocess.run(
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
        timeout=120,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "Traceback" not in result.stderr, result.stderr[-2000:]
    return result.stderr


def assert_shots(tmp_path: Path, names, res: str = "640x480") -> None:
    width, height = (int(v) for v in res.split("x"))
    for name in names:
        path = tmp_path / "shots" / res / f"{name}.png"
        assert path.is_file(), f"missing capture {name}"
        assert png_size(path) == (width, height)


def test_full_walkthrough(tmp_path):
    run_app(tmp_path, WALKTHROUGH)
    names = [token[5:] for token in WALKTHROUGH.split(",") if token.startswith("shot:")]
    assert_shots(tmp_path, names)


def test_unlock_screenshot(tmp_path):
    # Real screenshots (dev/sdcard) are git-ignored; without them the fixture card has stand-ins.
    run_app(tmp_path, "down,a,down,a,down,a,shot:achievement,a,shot:screenshot")
    shots = tmp_path / "shots" / "640x480"
    assert (shots / "achievement.png").read_bytes() != (shots / "screenshot.png").read_bytes()


@pytest.mark.parametrize(
    ("scenario", "script", "shots"),
    [
        ("auth", "wait:24,shot:home,start,shot:enter_key", ["home", "enter_key"]),
        ("setup", "shot:welcome,a,shot:keyboard,b,b", ["welcome", "keyboard"]),
        ("empty", "shot:home,down,a,shot:games", ["home", "games"]),
        (
            "proxy",
            "down,a,shot:games,b,down,a,shot:recent,b,down,down,a,shot:settings",
            ["games", "recent", "settings"],
        ),
        (
            "showcase",
            "down,a,shot:games,b,up,a,shot:profile,x,shot:profile_more,r1,r1,shot:profile_end,"
            "b,down,down,down,a,shot:awards",
            ["games", "profile", "profile_more", "profile_end", "awards"],
        ),
        # Metroid, last in the games list, isn't in the working set: it loads when opened.
        ("ondemand", "down,a,up,a,shot:loading,wait:30,shot:loaded", ["loading", "loaded"]),
    ],
)
def test_drills(tmp_path, scenario, script, shots):
    stderr = run_app(tmp_path, script, simulate=scenario)
    assert_shots(tmp_path, shots)
    if scenario == "auth":
        assert "API key rejected" in stderr
    if scenario == "ondemand":
        assert "Loaded game 1487 on request" in stderr
        frames = tmp_path / "shots" / "640x480"
        assert (frames / "loading.png").read_bytes() != (frames / "loaded.png").read_bytes()


# From the keyboard's top-left key, types 1234567890qwertyuiopasdfghjklzxc: a well-formed key.
KEY_ROWS = (
    ["down", "right", *["a", "right"] * 10],  # 1 to 0
    ["down", *["left"] * 11, *["a", "right"] * 10],  # q to p
    ["down", *["left"] * 9, *["a", "right"] * 9],  # a to l
    ["down", *["left"] * 8, *["a", "right"] * 3],  # z to c
)
TYPE_A_KEY = ",".join(step for row in KEY_ROWS for step in row)


def test_first_run_with_a_typed_key(tmp_path):
    run_app(tmp_path, f"a,{TYPE_A_KEY},start,wait:6,shot:home", simulate="setup")
    assert_shots(tmp_path, ["home"])
    key_file = tmp_path / "sdcard-setup" / "Saves" / "cheevos" / "apikey.txt"
    assert key_file.read_text() == "1234567890qwertyuiopasdfghjklzxc\n"


def test_start_syncs_from_any_screen(tmp_path):
    # Fixture mode syncs once before the UI starts; Start on the games list syncs again.
    stderr = run_app(tmp_path, "down,a,start,shot:games_sync,wait:24,shot:games_synced")
    assert_shots(tmp_path, ["games_sync", "games_synced"])
    assert stderr.count("Sync done") == 2


def test_games_list_is_kept_while_its_games_are_unchanged(tmp_path):
    # Back from a game, even after a sync stored the same games again, the list is shown as it
    # was; a new sort rebuilds it.
    script = "down,a,a,wait:2,b,a,start,wait:24,b,shot:games_kept,y,down,a,down,a,shot:sorted"
    stderr = run_app(tmp_path, script)
    assert_shots(tmp_path, ["games_kept", "sorted"])
    assert stderr.count("Sync done") == 2
    assert stderr.count("game rows in") == 2


def test_award_dot_follows_its_title(tmp_path):
    # Descent, the showcase's fourth game, is mastered: a gold dot between title and count.
    script = "down,a,down,down,down,a,shot:game,y,shot:popup,b,a,shot:card,b,b,shot:games"
    run_app(tmp_path, script, simulate="showcase")
    shots = tmp_path / "shots" / "640x480"
    gold = {
        name: gold_pixels(shots / f"{name}.png", 56) for name in ("game", "popup", "card", "games")
    }
    assert gold["game"] > 20  # the dot is ~12 px across at 640x480
    assert gold["popup"] == gold["game"]  # a popup over the screen keeps it
    assert gold["card"] == gold["games"] == 0  # other screens never get a stale dot
