import json

import pytest

from cheevos.core.identification.path_cache import (
    MAX_BYTES,
    MAX_ENTRIES,
    MISS_TTL,
    PathCache,
    path_key,
)
from cheevos.core.identification.result import Identification

NOW = 1_800_000_000.0
ROM = "/mnt/SDCARD/Roms/GBA/Final Fantasy Tactics Advance.gba"


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def file(tmp_path):
    return tmp_path / "Saves" / "cheevos" / "cache" / "rom-identifications.json"


def write(file, payload):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload), encoding="utf-8")


def test_matches_are_saved_and_read_back(file):
    PathCache(file, now=Clock()).remember(ROM, Identification.matched(1479))

    assert PathCache(file, now=Clock()).lookup(ROM) == Identification.matched(1479)
    saved = json.loads(file.read_text(encoding="utf-8"))
    assert saved == {
        "version": 2,
        "entries": {ROM: {"result": {"status": "matched", "game_id": 1479}}},
    }


def test_a_match_has_no_expiry_or_fingerprint(file):
    PathCache(file, now=Clock()).remember(ROM, Identification.matched(1479))

    # A year later, after the ROM was patched in place: the association still stands.
    assert PathCache(file, now=Clock(NOW + 365 * 86400)).lookup(ROM) == Identification.matched(1479)


def test_confirmed_misses_expire_after_a_week(file):
    clock = Clock()
    PathCache(file, now=clock).remember(ROM, Identification.no_match())

    clock.now = NOW + MISS_TTL - 1
    assert PathCache(file, now=clock).lookup(ROM) == Identification.no_match()
    clock.now = NOW + MISS_TTL
    assert PathCache(file, now=clock).lookup(ROM) is None


def test_a_miss_from_the_future_is_stale(file):
    PathCache(file, now=Clock()).remember(ROM, Identification.no_match())

    # The device clock went back (e.g. to 1970 before NTP): check the ROM again.
    assert PathCache(file, now=Clock(NOW - 60)).lookup(ROM) is None


@pytest.mark.parametrize("reason", ["offline", "auth", "hash", "dependency", "unavailable"])
def test_errors_are_never_saved(file, reason):
    cache = PathCache(file, now=Clock())
    cache.remember(ROM, Identification.error(reason))

    assert not file.exists()
    assert cache.lookup(ROM) is None


def test_keys_are_absolute_normalised_paths(file, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    PathCache(file, now=Clock()).remember("Roms/GBA/../GBA/game.gba", Identification.matched(7))

    assert path_key("Roms/GBA/game.gba") == str(tmp_path / "Roms" / "GBA" / "game.gba")
    found = PathCache(file, now=Clock()).lookup(str(tmp_path / "Roms/GBA/game.gba"))
    assert found == Identification.matched(7)


def test_reads_version_1_records_and_drops_their_fingerprints(file):
    write(
        file,
        {
            "version": 1,
            "entries": {
                ROM: {
                    "result": {"status": "matched", "game_id": 1479},
                    "fingerprint": {"size": 8388608, "mtime_ns": 1, "tracks": []},
                },
                "/miss.gba": {"result": {"status": "no_match"}, "checked_at": NOW, "size": 3},
            },
        },
    )
    cache = PathCache(file, now=Clock())
    assert cache.lookup(ROM) == Identification.matched(1479)
    assert cache.lookup("/miss.gba") == Identification.no_match()

    cache.remember("/new.gba", Identification.matched(9))

    saved = json.loads(file.read_text(encoding="utf-8"))
    assert saved["version"] == 2
    assert saved["entries"][ROM] == {"result": {"status": "matched", "game_id": 1479}}
    assert saved["entries"]["/miss.gba"] == {"result": {"status": "no_match"}, "checked_at": NOW}


@pytest.mark.parametrize(
    "result",
    [
        {"status": "matched", "game_id": True},
        {"status": "matched", "game_id": 0},
        {"status": "matched", "game_id": -5},
        {"status": "matched", "game_id": "1479"},
        {"status": "matched"},
        {"status": "error", "reason": "offline"},
        {"status": "cancelled"},
        "matched",
    ],
)
def test_invalid_records_are_skipped(file, result):
    write(
        file,
        {
            "version": 2,
            "entries": {
                ROM: {"result": result},
                "/ok.gba": {"result": {"status": "matched", "game_id": 3}},
            },
        },
    )
    cache = PathCache(file, now=Clock())

    assert cache.lookup(ROM) is None
    assert cache.lookup("/ok.gba") == Identification.matched(3)


def test_saved_virtual_game_ids_read_as_the_game(file):
    # Earlier Spruce builds saved RA's ID for an untested hash (1.1e9 + the game's ID).
    write(
        file,
        {
            "version": 2,
            "entries": {ROM: {"result": {"status": "matched", "game_id": 1_100_001_479}}},
        },
    )

    assert PathCache(file, now=Clock()).lookup(ROM) == Identification.matched(1479)


def test_a_miss_without_a_valid_check_time_is_stale(file):
    write(
        file,
        {
            "version": 2,
            "entries": {
                "/a": {"result": {"status": "no_match"}},
                "/b": {"result": {"status": "no_match"}, "checked_at": True},
                "/c": {"result": {"status": "no_match"}, "checked_at": "yesterday"},
            },
        },
    )
    cache = PathCache(file, now=Clock())
    assert [cache.lookup(path) for path in ("/a", "/b", "/c")] == [None, None, None]


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 3, "entries": {ROM: {"result": {"status": "matched", "game_id": 1}}}},
        {"version": 2, "entries": []},
        {"version": 2},
        [],
        {
            "version": 2,
            "entries": {
                f"/{i}": {"result": {"status": "matched", "game_id": 1}}
                for i in range(MAX_ENTRIES + 1)
            },
        },
    ],
)
def test_unknown_or_oversized_formats_read_as_empty(file, payload):
    write(file, payload)

    assert PathCache(file, now=Clock()).lookup(ROM) is None


def test_unreadable_or_oversized_files_read_as_empty(file):
    file.parent.mkdir(parents=True)
    file.write_bytes(b"\xff{not json")
    assert PathCache(file, now=Clock()).lookup(ROM) is None

    file.write_text(" " * (MAX_BYTES + 1), encoding="utf-8")
    assert PathCache(file, now=Clock()).lookup(ROM) is None


def test_keeps_the_newest_256_entries(file):
    cache = PathCache(file, now=Clock())
    for index in range(MAX_ENTRIES + 10):
        cache.remember(f"/rom-{index}.gba", Identification.matched(index + 1))

    saved = json.loads(file.read_text(encoding="utf-8"))["entries"]
    assert len(saved) == MAX_ENTRIES
    assert "/rom-9.gba" not in saved
    assert "/rom-10.gba" in saved
    assert next(reversed(saved)) == f"/rom-{MAX_ENTRIES + 9}.gba"


def test_remembering_a_path_again_makes_it_newest(file):
    cache = PathCache(file, now=Clock())
    cache.remember("/a.gba", Identification.no_match())
    cache.remember("/b.gba", Identification.matched(2))
    cache.remember("/a.gba", Identification.matched(1))

    saved = json.loads(file.read_text(encoding="utf-8"))["entries"]
    assert list(saved) == ["/b.gba", "/a.gba"]
    assert saved["/a.gba"] == {"result": {"status": "matched", "game_id": 1}}


def test_drops_the_oldest_entries_to_stay_within_256_kb(file):
    cache = PathCache(file, now=Clock())
    long_name = "x" * 2000
    for index in range(200):
        cache.remember(f"/{long_name}-{index}.gba", Identification.matched(index + 1))

    assert file.stat().st_size <= MAX_BYTES
    saved = json.loads(file.read_text(encoding="utf-8"))["entries"]
    assert len(saved) < 200
    assert f"/{long_name}-199.gba" in saved
    assert PathCache(file, now=Clock()).lookup(f"/{long_name}-199.gba") == Identification.matched(
        200
    )


def test_a_failed_write_does_not_fail_the_lookup(tmp_path, caplog):
    blocker = tmp_path / "cache"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    cache = PathCache(blocker / "rom-identifications.json", now=Clock())

    cache.remember(ROM, Identification.matched(1479))

    assert cache.lookup(ROM) == Identification.matched(1479)  # still known for this run
    assert "Could not save" in caplog.text


def test_writes_are_atomic(file, monkeypatch):
    cache = PathCache(file, now=Clock())
    cache.remember("/a.gba", Identification.matched(1))
    before = file.read_bytes()

    def fail(*_args, **_kwargs):
        raise OSError("SD card removed")

    monkeypatch.setattr("cheevos.core.files.os.fsync", fail)
    cache.remember("/b.gba", Identification.matched(2))

    assert file.read_bytes() == before
