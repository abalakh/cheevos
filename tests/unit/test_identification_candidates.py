import json
import logging
import shutil
import zipfile
from pathlib import Path

import pytest

from cheevos.core.identification import candidates
from cheevos.core.identification.candidates import (
    COPY_CHUNK,
    HashResult,
    hash_candidates,
    select_archive_rom_names,
)
from cheevos.core.identification.result import IdentificationError

EXTENSIONS = frozenset({".gba", ".nes", ".sfc", ".md", ".chd"})


class FakeHasher:
    """Content hashes for files, arcade (name) hashes for archives; 7z is JSON."""

    def __init__(self):
        self.hashed: list[tuple[str, bytes]] = []
        self.seen_in: list[Path] = []

    def supported_extensions(self):
        return EXTENSIONS

    def hash_file(self, path):
        if path.suffix in {".zip", ".7z"}:
            self.hashed.append((path.name, b""))
            return HashResult((f"arcade:{path.name}",))
        if path.suffix == ".chd":
            return HashResult((), "Could not hash disc.chd")
        data = path.read_bytes()
        self.hashed.append((path.name, data))
        self.seen_in.append(path.parent)
        return HashResult((f"content:{data.decode()}", f"alt:{data.decode()}"))

    def list_7z_entries(self, path):
        return list(json.loads(path.read_text()))

    def hash_7z_entry(self, path, entry):
        content = json.loads(path.read_text())[entry]
        return () if content == "!unreadable" else (f"7z:{content}",)


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def work(tmp_path):
    return tmp_path / "Saves" / "cheevos" / "cache" / "identify-work" / "lookup-1"


def test_plain_rom_is_hashed_in_place(tmp_path, work):
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"cart")

    assert hash_candidates(rom, FakeHasher(), work) == ("content:cart", "alt:cart")
    assert not work.exists()


def test_single_rom_zip_is_extracted_to_the_work_dir_and_removed(tmp_path, work):
    archive = make_zip(tmp_path / "game.zip", {"Game (USA).gba": b"zipped"})
    hasher = FakeHasher()

    assert hash_candidates(archive, hasher, work) == ("content:zipped", "alt:zipped")
    # Hashed under its own name (rc_hash picks the console by extension), on the SD card.
    assert hasher.hashed == [("Game (USA).gba", b"zipped")]
    assert hasher.seen_in[0].parent == work
    assert hasher.seen_in[0].name.startswith("rom-hash-")
    assert list(work.iterdir()) == []


def test_extraction_streams_in_64_kb_chunks(tmp_path, work, monkeypatch):
    archive = make_zip(tmp_path / "game.zip", {"game.gba": b"x" * (3 * COPY_CHUNK + 5)})
    lengths = []
    real_copy = shutil.copyfileobj

    def spy(source, target, length=0):
        lengths.append(length)
        return real_copy(source, target, length)

    monkeypatch.setattr(candidates.shutil, "copyfileobj", spy)

    hash_candidates(archive, FakeHasher(), work)

    assert lengths == [64 * 1024]


@pytest.mark.parametrize(
    ("entries", "hashed"),
    [
        ({"game": b"no extension"}, "game"),  # a lone file is a ROM whatever its name
        ({"game.sfc": b"rom", "readme.txt": b"notes"}, "game.sfc"),
        ({"__MACOSX/._game.gba": b"fork", "game.gba": b"real"}, "game.gba"),
        ({"Folder/": b"", "Folder/game.nes": b"nes"}, "game.nes"),
        ({"dir/..": b"dots", "game.gba": b"rom"}, "game.gba"),
    ],
)
def test_zip_rom_entry_selection(tmp_path, work, entries, hashed):
    archive = make_zip(tmp_path / "set.zip", entries)
    hasher = FakeHasher()

    hash_candidates(archive, hasher, work)

    assert [name for name, _ in hasher.hashed] == [hashed]


@pytest.mark.parametrize(
    "entries",
    [
        {"set.p1": b"program", "set.c1": b"graphics"},  # an arcade set
        {},
    ],
)
def test_zip_without_a_rom_entry_uses_the_arcade_hash(tmp_path, work, entries):
    archive = make_zip(tmp_path / "mslug.zip", entries)

    assert hash_candidates(archive, FakeHasher(), work) == ("arcade:mslug.zip",)


def test_unreadable_zip_uses_the_arcade_hash(tmp_path, work):
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"not a zip at all")

    assert hash_candidates(archive, FakeHasher(), work) == ("arcade:broken.zip",)


def test_zip_with_several_roms_cannot_be_identified(tmp_path, work):
    archive = make_zip(tmp_path / "pack.zip", {"a.gba": b"1", "b.gba": b"2"})

    with pytest.raises(IdentificationError) as error:
        hash_candidates(archive, FakeHasher(), work)
    assert error.value.reason == "hash"


def test_a_corrupt_entry_is_a_hash_error_and_leaves_nothing(tmp_path, work):
    archive = make_zip(tmp_path / "game.zip", {"game.gba": b"cartridge data" * 100})
    data = bytearray(archive.read_bytes())
    start = data.index(b"game.gba") + len("game.gba")  # the local header's name, then data
    data[start + 10 : start + 20] = b"\x00" * 10
    archive.write_bytes(bytes(data))

    with pytest.raises(IdentificationError) as error:
        hash_candidates(archive, FakeHasher(), work)
    assert error.value.reason == "hash"
    assert list(work.iterdir()) == []


def test_extraction_is_removed_when_hashing_is_interrupted(tmp_path, work):
    archive = make_zip(tmp_path / "game.zip", {"game.gba": b"zipped"})

    class Interrupted(FakeHasher):
        def hash_file(self, path):
            assert path.is_file()
            raise SystemExit(143)  # what the helper's SIGTERM handler raises

    with pytest.raises(SystemExit):
        hash_candidates(archive, Interrupted(), work)
    assert list(work.iterdir()) == []


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ({"game.md": "megadrive"}, ("7z:megadrive",)),
        ({"game.md": "!unreadable"}, ("arcade:game.7z",)),  # entry unreadable: arcade hash
        ({"set.p1": "a", "set.c1": "b"}, ("arcade:game.7z",)),
        ({"._game.md": "fork", "game.md": "megadrive"}, ("7z:megadrive",)),
    ],
)
def test_7z_rules(tmp_path, work, content, expected):
    archive = tmp_path / "game.7z"
    archive.write_text(json.dumps(content))

    assert hash_candidates(archive, FakeHasher(), work) == expected


def test_7z_with_several_roms_cannot_be_identified(tmp_path, work):
    archive = tmp_path / "pack.7z"
    archive.write_text(json.dumps({"a.md": "1", "b.md": "2"}))

    with pytest.raises(IdentificationError):
        hash_candidates(archive, FakeHasher(), work)


def test_no_candidates_is_a_hash_error(tmp_path, work, caplog):
    caplog.set_level(logging.INFO)
    disc = tmp_path / "disc.chd"
    disc.write_bytes(b"disc")

    with pytest.raises(IdentificationError) as error:
        hash_candidates(disc, FakeHasher(), work)
    assert error.value.reason == "hash"
    assert "Could not hash disc.chd" in caplog.text


def test_select_archive_rom_names_matches_extensions_case_insensitively():
    names = ["GAME.GBA", "notes.txt"]
    assert select_archive_rom_names(names, EXTENSIONS) == ["GAME.GBA"]
    assert select_archive_rom_names(["a.txt", "b.txt"], EXTENSIONS) == []
    assert select_archive_rom_names(["only.bin"], EXTENSIONS) == ["only.bin"]
