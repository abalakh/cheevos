import os
from pathlib import Path

import pytest

from cheevos.core.screenshots import ScreenshotIndex, screenshot_directory
from cheevos.platform.paths import Paths

FFTA = "Final Fantasy Tactics Advance (Europe) (En,Fr,De,Es,It)"


def touch(path, mtime):
    path.write_bytes(b"\x89PNG")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def shots(tmp_path):
    directory = tmp_path / "screenshots"
    directory.mkdir()
    touch(directory / f"{FFTA}-cheevo-177850.png", 1000)
    touch(directory / f"{FFTA}-cheevo-177851.png", 1001)
    touch(directory / "Descent (USA)-cheevo-527418.PNG", 1002)
    touch(directory / "Fire Emblem (USA, Australia)-cheevo-101000001.png", 1003)
    touch(directory / f"{FFTA}-700101-001940.png", 1004)  # manual screenshot
    touch(directory / "notes-cheevo-12.txt", 1005)
    (directory / "mupen64plus").mkdir()
    return directory


def test_index_maps_achievements_and_skips_noise(shots):
    index = ScreenshotIndex(shots)
    assert index.lookup(177850) == shots / f"{FFTA}-cheevo-177850.png"
    assert index.lookup(527418) == shots / "Descent (USA)-cheevo-527418.PNG"
    assert index.lookup(101000001) is None  # RA warning pseudo-achievement
    assert index.lookup(12) is None
    assert index.count() == 3


def test_newest_duplicate_wins(shots):
    newer = touch(shots / "Final Fantasy Tactics Advance (USA)-cheevo-177850.png", 2000)
    assert ScreenshotIndex(shots).lookup(177850) == newer


def test_rescans_only_when_directory_changes(shots, monkeypatch):
    index = ScreenshotIndex(shots)
    assert index.count() == 3
    scans = []
    original = ScreenshotIndex._scan

    def counting(self):
        scans.append(1)
        return original(self)

    monkeypatch.setattr(ScreenshotIndex, "_scan", counting)
    index.lookup(177850)
    assert scans == []
    added = touch(shots / "Metroid (USA)-cheevo-42.png", 3000)
    os.utime(shots, (5000, 5000))
    assert index.lookup(42) == added
    assert scans == [1]


def test_missing_directory_is_empty_then_appears(tmp_path):
    directory = tmp_path / "screenshots"
    index = ScreenshotIndex(directory)
    assert index.count() == 0
    directory.mkdir()
    touch(directory / "Game-cheevo-7.png", 10)
    assert index.lookup(7) == directory / "Game-cheevo-7.png"


def test_unreadable_entries_are_skipped(shots, monkeypatch):
    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self.name.endswith("177851.png"):
            raise OSError("vanished")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    index = ScreenshotIndex(shots)
    assert index.lookup(177850) is not None
    assert index.lookup(177851) is None


def test_unlistable_directory_logs_and_is_empty(shots, monkeypatch, caplog):
    def refuse(self):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.iterdir", refuse)
    assert ScreenshotIndex(shots).count() == 0
    assert "Cannot list screenshots" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('"/mnt/SDCARD/Saves/screenshots"', "/mnt/SDCARD/Saves/screenshots"),
        ('"/custom/shots"', "/custom/shots"),
        ('"default"', None),
        ('""', None),
        ('":/screenshots"', None),
    ],
)
def test_screenshot_directory(tmp_path, value, expected):
    paths = Paths(sdcard=tmp_path)
    paths.retroarch_config.parent.mkdir(parents=True)
    paths.retroarch_config.write_text(f"screenshot_directory = {value}\n")
    expected_path = paths.default_screenshot_dir if expected is None else Path(expected)
    assert screenshot_directory(paths) == expected_path


def test_screenshot_directory_without_config(tmp_path):
    paths = Paths(sdcard=tmp_path)
    assert screenshot_directory(paths) == tmp_path / "Saves" / "screenshots"
