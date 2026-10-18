import json
import os
import signal
import subprocess
import sys
import zipfile
from pathlib import Path

import fake_proxy
import pytest

from cheevos.core.identification.candidates import HashResult
from cheevos.core.identification.identify import Sources, identify_rom
from cheevos.core.identification.path_cache import PathCache
from cheevos.core.identification.result import Identification, IdentificationError
from cheevos.platform import identify_rom as helper
from cheevos.platform.paths import Paths

SRC = Path(__file__).resolve().parents[2] / "src"
NOW = 1_800_000_000.0


class Hasher:
    def supported_extensions(self):
        return frozenset({".gba"})

    def hash_file(self, path):
        return HashResult((fake_proxy.md5(path.read_bytes()),))

    def list_7z_entries(self, path):
        return []

    def hash_7z_entry(self, path, entry):
        return ()


class Ra:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def game_id(self, hash_value):
        self.asked.append(hash_value)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def unused(*_args):
    raise AssertionError("not needed for a saved association")


@pytest.fixture
def paths(tmp_path):
    return Paths(sdcard=tmp_path, platform="Test")


def sources(paths, *, hasher=None, ra=None):
    return Sources(
        load_hasher=(lambda: hasher) if hasher else unused,
        work_dir=paths.identify_work_dir,
        proxy_database=paths.proxy_data_dir / "proxy.sqlite3",
        ra_lookup=(lambda: ra) if ra else unused,
        now=lambda: NOW,
    )


def rom(paths, name="game.gba", data=b"cartridge"):
    path = paths.sdcard / "Roms" / "GBA" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def cache(paths):
    return PathCache(paths.rom_identifications_file, now=lambda: NOW)


# --- orchestration ----------------------------------------------------------------------------


def test_a_saved_association_needs_no_file_hasher_or_network(paths):
    cache(paths).remember("/mnt/SDCARD/Roms/GBA/gone.gba", Identification.matched(1479))

    result = identify_rom(
        "/mnt/SDCARD/Roms/GBA/gone.gba", cache=cache(paths), sources=sources(paths)
    )
    assert result == Identification.matched(1479)


def test_ra_match_is_saved_for_next_time(paths):
    path = rom(paths)
    ra = Ra(1479)

    first = identify_rom(
        str(path), cache=cache(paths), sources=sources(paths, hasher=Hasher(), ra=ra)
    )
    second = identify_rom(str(path), cache=cache(paths), sources=sources(paths))

    assert first == second == Identification.matched(1479)
    assert ra.asked == [fake_proxy.md5(b"cartridge")]


def test_proxy_cached_match_needs_no_network(paths):
    path = rom(paths)
    fake_proxy.proxy_database(
        paths.sdcard, {f"gameid:{fake_proxy.md5(b'cartridge')}": ('{"GameID":228}', 0)}
    )

    result = identify_rom(str(path), cache=cache(paths), sources=sources(paths, hasher=Hasher()))

    assert result == Identification.matched(228)


def test_confirmed_miss_is_saved(paths):
    path = rom(paths)

    result = identify_rom(
        str(path), cache=cache(paths), sources=sources(paths, hasher=Hasher(), ra=Ra(None))
    )

    assert result == Identification.no_match()
    assert cache(paths).lookup(str(path)) == Identification.no_match()


@pytest.mark.parametrize("reason", ["offline", "auth", "network", "rate_limited", "response"])
def test_lookup_errors_are_returned_and_not_saved(paths, reason):
    path = rom(paths)
    ra = Ra(IdentificationError(reason))

    result = identify_rom(
        str(path), cache=cache(paths), sources=sources(paths, hasher=Hasher(), ra=ra)
    )

    assert result == Identification.error(reason)
    assert not paths.rom_identifications_file.exists()


def test_a_missing_rom_is_a_file_error_before_loading_the_hasher(paths):
    result = identify_rom(
        str(paths.sdcard / "Roms" / "missing.gba"), cache=cache(paths), sources=sources(paths)
    )
    assert result == Identification.error("file")


def test_a_directory_is_a_file_error(paths):
    (paths.sdcard / "Roms" / "Folder.gba").mkdir(parents=True)
    result = identify_rom(
        str(paths.sdcard / "Roms" / "Folder.gba"), cache=cache(paths), sources=sources(paths)
    )
    assert result == Identification.error("file")


def test_a_dependency_error_is_returned_and_not_saved(paths):
    path = rom(paths)

    def broken():
        raise IdentificationError("dependency", "ImportError")

    broken_sources = Sources(
        load_hasher=broken,
        work_dir=paths.identify_work_dir,
        proxy_database=paths.proxy_data_dir / "proxy.sqlite3",
        ra_lookup=unused,
        now=lambda: NOW,
    )
    result = identify_rom(str(path), cache=cache(paths), sources=broken_sources)

    assert result == Identification.error("dependency")
    assert not paths.rom_identifications_file.exists()


def test_a_failed_cache_write_still_returns_the_match(paths):
    path = rom(paths)
    paths.cache_dir.parent.mkdir(parents=True, exist_ok=True)
    paths.cache_dir.write_text("not a directory", encoding="utf-8")

    result = identify_rom(
        str(path), cache=cache(paths), sources=sources(paths, hasher=Hasher(), ra=Ra(7))
    )

    assert result == Identification.matched(7)


def test_an_unexpected_failure_is_unavailable(paths, caplog):
    def explode():
        raise ZeroDivisionError

    result = helper.run(
        str(rom(paths)),
        paths=paths,
        sources=Sources(
            load_hasher=explode,
            work_dir=paths.identify_work_dir,
            proxy_database=paths.proxy_data_dir / "proxy.sqlite3",
            ra_lookup=unused,
            now=lambda: NOW,
        ),
    )

    assert result == Identification.error("unavailable")
    assert "ZeroDivisionError" in caplog.text


# --- the command line, in process -------------------------------------------------------------


@pytest.fixture
def cli(paths, monkeypatch):
    monkeypatch.setenv("CHEEVOS_SDCARD_ROOT", str(paths.sdcard))
    monkeypatch.setenv("PLATFORM", "Test")
    monkeypatch.setattr(helper, "_configure_logging", lambda _file: None)
    monkeypatch.setattr(helper.signal, "signal", lambda *_args: None)


def test_main_prints_one_json_object(paths, cli, capsys):
    cache(paths).remember("/Roms/GBA/game.gba", Identification.matched(1479))

    assert helper.main(["--path", "/Roms/GBA/game.gba", "--json"]) == 0
    assert capsys.readouterr().out == '{"status":"matched","game_id":1479}\n'


def test_main_reports_errors_as_json_with_a_failure_status(paths, cli, capsys):
    assert helper.main(["--path", str(paths.sdcard / "missing.gba"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "error", "reason": "file"}


def test_main_prints_a_summary_without_json(paths, cli, capsys):
    # Saved now: main() checks a miss's age against the real clock.
    PathCache(paths.rom_identifications_file).remember("/Roms/miss.gba", Identification.no_match())
    helper.main(["--path", "/Roms/miss.gba"])
    assert capsys.readouterr().out == "no match\n"


def test_main_refuses_relative_paths(cli, capsys):
    with pytest.raises(SystemExit) as exit_:
        helper.main(["--path", "Roms/game.gba", "--json"])
    assert exit_.value.code == 2
    assert capsys.readouterr().out == ""


# --- the real process ---------------------------------------------------------------------------


def run_helper(sdcard, rom_path, *extra, env=None, **kwargs):
    """Run the helper as Spruce does and return (process, the modules it loaded)."""
    probe = (
        "import json, runpy, sys\n"
        "sys.argv = ['identify-rom.sh'] + sys.argv[1:]\n"
        "try:\n"
        "    runpy.run_module('cheevos.platform.identify_rom', run_name='__main__')\n"
        "finally:\n"
        "    print(json.dumps(sorted(sys.modules)), file=sys.stderr)\n"
    )
    environment = {
        "PYTHONPATH": str(SRC),
        "CHEEVOS_SDCARD_ROOT": str(sdcard),
        "PLATFORM": "Test",
        "PATH": os.environ.get("PATH", ""),
        **(env or {}),
    }
    command = [sys.executable, "-c", probe, "--path", str(rom_path), *extra, "--json"]
    return subprocess.run(
        command, capture_output=True, text=True, env=environment, check=False, **kwargs
    )


def loaded_modules(process):
    return set(json.loads(process.stderr.strip().splitlines()[-1]))


NEVER = {
    "sdl2",
    "cheevos.app",
    "cheevos.ui",
    "cheevos.core.sync.engine",
    "cheevos.core.storage.data_cache",
    "cheevos.core.ra_client.client",
    "raofflineproxy.main",
    "raofflineproxy.rom_browser",
    "raofflineproxy.storage",
    "raofflineproxy.network",
    "raofflineproxy.service",
    "raofflineproxy.menu_sdl",
}


def test_saved_association_loads_no_hashing_storage_or_network_code(tmp_path):
    cache_file = Paths(sdcard=tmp_path).rom_identifications_file
    PathCache(cache_file).remember("/Roms/GBA/game.gba", Identification.matched(1479))

    process = run_helper(tmp_path, "/Roms/GBA/game.gba")

    assert process.returncode == 0
    assert json.loads(process.stdout) == {"status": "matched", "game_id": 1479}
    loaded = loaded_modules(process)
    lazy = {
        "zipfile",
        "sqlite3",
        "ssl",
        "http.client",
        "raofflineproxy",
        "cheevos.core.identification.candidates",
        "cheevos.core.identification.hash_lookup",
        "cheevos.core.ra_client.transport",
    }
    assert sorted((NEVER | lazy) & loaded) == []
    assert not any(name.startswith(("cheevos.ui", "raofflineproxy")) for name in loaded)


def test_unknown_rom_matched_from_the_proxy_cache_leaves_the_proxy_untouched(tmp_path):
    package = fake_proxy.install(tmp_path)
    game = tmp_path / "Roms" / "GBA" / "game.zip"
    game.parent.mkdir(parents=True)
    with zipfile.ZipFile(game, "w") as archive:
        archive.writestr("Game.gba", b"zipped cartridge")
    database = fake_proxy.proxy_database(
        tmp_path, {f"gameid:{fake_proxy.md5(b'zipped cartridge')}": ('{"GameID":1479}', 0)}
    )
    proxy_files = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in database.parent.iterdir()}
    package_files = sorted(p.name for p in package.iterdir())

    process = run_helper(tmp_path, game)

    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"status": "matched", "game_id": 1479}
    loaded = loaded_modules(process)
    assert "raofflineproxy.rom_hashing" in loaded
    assert sorted(NEVER & loaded) == []
    assert "ssl" not in loaded  # answered from the proxy's cache
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in database.parent.iterdir()} == (
        proxy_files
    )
    assert sorted(p.name for p in package.iterdir()) == package_files  # no __pycache__ either
    saved = json.loads(Paths(sdcard=tmp_path).rom_identifications_file.read_text())
    assert saved["entries"][str(game)] == {"result": {"status": "matched", "game_id": 1479}}
    assert list(Paths(sdcard=tmp_path).identify_work_dir.iterdir()) == []


def test_import_failure_in_the_installed_proxy_is_a_structured_error(tmp_path):
    fake_proxy.install(tmp_path, rom_hashing="from .main import apply_scan_batch_cooldown\n")
    game = tmp_path / "Roms" / "game.gba"
    game.parent.mkdir(parents=True)
    game.write_bytes(b"cartridge")

    process = run_helper(tmp_path, game)

    assert process.returncode == 1
    assert json.loads(process.stdout) == {"status": "error", "reason": "dependency"}
    log = (tmp_path / "Saves" / "spruce" / "cheevos-Test.log").read_text()
    assert "importing raofflineproxy.rom_hashing" in log


def test_sigterm_during_hashing_removes_the_extraction(tmp_path):
    fake_proxy.install(tmp_path)
    game = tmp_path / "Roms" / "GBA" / "game.zip"
    game.parent.mkdir(parents=True)
    with zipfile.ZipFile(game, "w") as archive:
        archive.writestr("Game.gba", b"zipped cartridge")
    work = tmp_path / "Saves" / "cheevos" / "cache" / "identify-work" / "lookup-test"
    probe_env = {"FAKE_HASH_BLOCK": "1"}
    environment = {
        "PYTHONPATH": str(SRC),
        "CHEEVOS_SDCARD_ROOT": str(tmp_path),
        "PLATFORM": "Test",
        **probe_env,
    }
    command = [
        sys.executable,
        "-m",
        "cheevos.platform.identify_rom",
        "--path",
        str(game),
        "--work-dir",
        str(work),
        "--json",
    ]
    pipe = subprocess.PIPE
    with subprocess.Popen(
        command, stdin=pipe, stdout=pipe, stderr=pipe, env=environment
    ) as process:
        assert process.stderr is not None
        try:
            assert process.stderr.readline() == b"hashing\n"  # blocked in the proxy's hasher
            assert [p.name[:9] for p in work.iterdir()] == ["rom-hash-"]
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()

    assert process.returncode == 128 + signal.SIGTERM
    assert list(work.iterdir()) == []
    assert not Paths(sdcard=tmp_path).rom_identifications_file.exists()
