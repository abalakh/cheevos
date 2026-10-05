import json

from cheevos.core.local_games import local_games, on_device_game_ids
from cheevos.core.models import LocalGame
from cheevos.core.proxy import ProxyReader
from cheevos.platform.paths import Paths

FFTA_ROM = "/mnt/SDCARD/Roms/GBA/Final Fantasy Tactics Advance (Europe).gba"


def write_pyui_cache(paths, entries):
    paths.pyui_cheevos_cache.parent.mkdir(parents=True, exist_ok=True)
    paths.pyui_cheevos_cache.write_text(json.dumps(entries))


def write_proxy_ids(paths, text):
    paths.proxy_data_dir.mkdir(parents=True, exist_ok=True)
    (paths.proxy_data_dir / "cached_game_ids.txt").write_text(text)


def test_nothing_known(tmp_path):
    paths = Paths(sdcard=tmp_path)
    assert local_games(paths, ProxyReader(paths)) == []


def test_combines_pyui_cache_and_proxy_ids(tmp_path):
    paths = Paths(sdcard=tmp_path)
    write_pyui_cache(
        paths,
        [
            {
                "rom_file_path": FFTA_ROM,
                "game_system_name": "GBA",
                "display_name": "Final Fantasy Tactics Advance",
                "game_id": 519,
            },
            {"rom_file_path": "/mnt/SDCARD/Roms/PS/Descent.chd", "game_id": "3830"},
            {"rom_file_path": "/no/id.gba", "game_id": None},
            {"rom_file_path": "", "game_id": 5},
            {"rom_file_path": "/bool.gba", "game_id": True},
            {"rom_file_path": "/zero.gba", "game_id": 0},
            "not a dict",
        ],
    )
    write_proxy_ids(paths, "519\n1446\n")
    assert local_games(paths, ProxyReader(paths)) == [
        LocalGame(519, FFTA_ROM, "GBA", "pyui-cheevos-cache"),
        LocalGame(3830, "/mnt/SDCARD/Roms/PS/Descent.chd", "", "pyui-cheevos-cache"),
        LocalGame(1446, "", "", "raofflineproxy"),
    ]
    assert on_device_game_ids(paths, ProxyReader(paths)) == {519, 3830, 1446}


def test_unreadable_pyui_cache_is_ignored(tmp_path, caplog):
    paths = Paths(sdcard=tmp_path)
    paths.pyui_cheevos_cache.parent.mkdir(parents=True)
    paths.pyui_cheevos_cache.write_text("{broken")
    write_proxy_ids(paths, "7\n")
    assert on_device_game_ids(paths, ProxyReader(paths)) == {7}
    assert "Cannot read" in caplog.text
    paths.pyui_cheevos_cache.write_text('{"not": "a list"}')
    assert on_device_game_ids(paths, ProxyReader(paths)) == {7}
