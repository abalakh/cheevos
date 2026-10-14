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

from cheevos.core.settings import Settings, load_settings
from cheevos.core.storage.data_cache import DataCache
from cheevos.platform.desktop.no_set_drill import GAME_ID

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
    """Count saturated gold (including its shading) in the top rows of a screenshot."""
    bpp, rows = png_rows(path, top)
    return sum(
        1
        for row in rows
        for x in range(0, len(row), bpp)
        if row[x] > 150
        and row[x + 1] > 110
        and row[x] - row[x + 2] > 80
        and row[x + 1] - row[x + 2] > 60
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


@pytest.mark.parametrize("options_button", ["y", "menu"])
def test_full_walkthrough(tmp_path, options_button):
    script = ",".join(options_button if step == "y" else step for step in WALKTHROUGH.split(","))
    run_app(tmp_path, script)
    names = [token[5:] for token in WALKTHROUGH.split(",") if token.startswith("shot:")]
    assert_shots(tmp_path, names)


@pytest.mark.parametrize(
    "open_screen",
    ["down,a", "down,a,a", "down,a,a,select", "down,down,down,a"],
    ids=["games", "achievements", "badge_grid", "awards"],
)
def test_options_popups_accept_y_and_menu(tmp_path, open_screen):
    run_app(
        tmp_path,
        f"{open_screen},y,shot:y_popup,b,menu,shot:menu_popup",
        simulate="showcase",
    )
    shots = tmp_path / "shots/640x480"
    bpp_y, rows_y = png_rows(shots / "y_popup.png", 300)
    bpp_menu, rows_menu = png_rows(shots / "menu_popup.png", 300)
    assert bpp_y == bpp_menu
    # Compare the popup panel, leaving out the clock and the live background beside it.
    assert [row[: 320 * bpp_y] for row in rows_y[56:]] == [
        row[: 320 * bpp_menu] for row in rows_menu[56:]
    ]


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


def test_badge_grid_wraps_to_the_last_page_and_comes_back_to_it_from_a_card(tmp_path):
    # Fire Emblem (87 badges): up from the first wraps to the last, partial page.
    run_app(tmp_path, "down,a,a,select,shot:first,up,shot:last,a,shot:card,b,shot:back")
    assert_shots(tmp_path, ["first", "last", "card", "back"])
    shots = tmp_path / "shots" / "640x480"
    below_clock = [png_rows(shots / f"{name}.png", 480)[1][64:] for name in ("first", "last")]
    assert below_clock[0] != below_clock[1]
    assert png_rows(shots / "back.png", 480)[1][64:] == below_clock[1]


def test_view_preferences_survive_exit_and_restart(tmp_path):
    run_app(
        tmp_path,
        "down,a,select,shot:details,down,a,select,y,down,down,a,down,down,down,a,shot:grid,b,b,b",
    )
    settings_file = tmp_path / "sdcard/Saves/cheevos/settings.json"
    assert load_settings(settings_file) == Settings(
        game_list_details=True, achievement_grid=True, achievement_sort="points"
    )

    # Restart on the same card, then change the layout through Y. Exhausting the script raises
    # SystemExit, which must save the final choice just like B on Home in the first run.
    run_app(
        tmp_path,
        "down,a,shot:restored_details,down,a,shot:restored_grid,y,a,up,a,shot:list,"
        "y,down,down,a,down,a,shot:rarity",
    )
    shots = tmp_path / "shots" / "640x480"
    for name in ("details", "grid"):
        # Ignore the top-bar clock when comparing the views before and after restart.
        expected = png_rows(shots / f"{name}.png", 480)[1][64:]
        assert png_rows(shots / f"restored_{name}.png", 480)[1][64:] == expected
    assert load_settings(settings_file) == Settings(
        game_list_details=True, achievement_grid=False, achievement_sort="rarity"
    )


def test_game_without_an_achievement_set_returns_to_the_list(tmp_path):
    script = (
        "down,a,shot:games,a,shot:loading,wait:4,shot:no_set,b,shot:after_b,"
        "a,a,shot:after_a,select,shot:details"
    )
    run_app(tmp_path, script, simulate="noset")
    assert_shots(tmp_path, ["games", "loading", "no_set", "after_b", "after_a", "details"])
    shots = tmp_path / "shots" / "640x480"
    assert (shots / "loading.png").read_bytes() != (shots / "no_set.png").read_bytes()
    # Ignore the top-bar clock; returning preserves the row selection and scroll position.
    rows = png_rows(shots / "games.png", 480)[1][64:]
    assert png_rows(shots / "after_b.png", 480)[1][64:] == rows
    assert png_rows(shots / "after_a.png", 480)[1][64:] == rows
    data = DataCache.open(tmp_path / "sdcard-noset/Saves/cheevos/cache/data.db", "Balah")
    game, detail = data.game(GAME_ID), data.game_detail(GAME_ID)
    assert game is not None
    assert detail is not None
    assert game.max_possible == game.earned == game.earned_hardcore == 0
    assert detail.achievements == ()
    data.close()


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


@pytest.mark.parametrize("res", ["640x480", "752x560", "1280x720", "720x720", "480x800"])
def test_awards_views_keep_the_selection_through_games_options_and_view_switches(tmp_path, res):
    # Showcase awards, newest first: Descent (a mastered game), then Find the Pixel (an event).
    script = (
        "down,down,down,a,shot:carousel,a,shot:game,b,shot:from_game,"
        "right,shot:event,a,shot:event_a,y,shot:options,b,shot:from_options,"
        "select,shot:grid,select,shot:list,select,shot:carousel_again"
    )
    run_app(tmp_path, script, res=res, simulate="showcase")
    names = [token[5:] for token in script.split(",") if token.startswith("shot:")]
    assert_shots(tmp_path, names, res)
    shots = tmp_path / "shots" / res
    height = int(res.split("x")[1])

    def below_clock(name):
        return png_rows(shots / f"{name}.png", height)[1][height // 6 :]

    assert below_clock("game") != below_clock("carousel")
    assert below_clock("from_game") == below_clock("carousel")
    for name in ("event_a", "from_options", "carousel_again"):  # A on an event does nothing
        assert below_clock(name) == below_clock("event")
    assert len({bytes(b"".join(below_clock(name))) for name in ("event", "grid", "list")}) == 3


def test_awards_view_is_saved_on_exit(tmp_path):
    # Drills start from a clean card, so restoring it is covered by test_ui_awards.py.
    run_app(
        tmp_path, "down,down,down,a,right,select,shot:grid,select,shot:list", simulate="showcase"
    )
    settings_file = tmp_path / "sdcard-showcase/Saves/cheevos/settings.json"
    assert load_settings(settings_file) == Settings(awards_view="list")  # nothing else changed
