import json

import pytest

from cheevos.core.files import write_text_atomic
from cheevos.core.settings import (
    DEFAULTS,
    BadgeScope,
    DescriptionHiding,
    Settings,
    load_settings,
    save_settings,
)


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "settings.json") == DEFAULTS
    assert Settings(BadgeScope.ON_DEVICE_AND_RECENT, 30, DescriptionHiding.OFF, True) == DEFAULTS


def test_round_trip(tmp_path):
    path = tmp_path / "cheevos" / "settings.json"
    settings = Settings(BadgeScope.ALL, 90, DescriptionHiding.STORY, False, game_list_details=True)
    save_settings(path, settings)
    assert load_settings(path) == settings
    assert not path.with_name("settings.json.tmp").exists()


def test_saved_json_has_stable_key_order(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, DEFAULTS)
    assert list(json.loads(path.read_text())) == [
        "badge_scope",
        "recent_days",
        "hide_descriptions",
        "auto_sync",
        "game_list_details",
        "untested_note",
    ]


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", "\xff\xfe"])
def test_corrupt_file_gives_defaults(tmp_path, content, caplog):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="latin-1")
    assert load_settings(path) == DEFAULTS
    assert "settings" in caplog.text.lower()


def test_each_invalid_key_falls_back_alone(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "badge_scope": "everything",
                "recent_days": 14,
                "hide_descriptions": "yes",
                "auto_sync": False,
                "game_list_details": "details",
                "unknown_key": 1,
            }
        )
    )
    assert load_settings(path) == Settings(
        badge_scope=DEFAULTS.badge_scope,
        recent_days=DEFAULTS.recent_days,
        hide_descriptions=DEFAULTS.hide_descriptions,
        auto_sync=False,
    )


def test_bool_is_not_a_valid_recent_days(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"recent_days": True, "badge_scope": "none"}))
    loaded = load_settings(path)
    assert loaded.recent_days == 30
    assert loaded.badge_scope is BadgeScope.NONE


def test_atomic_write_replaces_and_sets_mode(tmp_path):
    path = tmp_path / "a" / "b.txt"
    write_text_atomic(path, "one")
    write_text_atomic(path, "two", mode=0o600)
    assert path.read_text() == "two"
    assert path.stat().st_mode & 0o777 == 0o600


def test_atomic_write_survives_chmod_failure(tmp_path, monkeypatch):
    def refuse(self, mode):
        raise PermissionError("FAT32")

    monkeypatch.setattr("pathlib.Path.chmod", refuse)
    path = tmp_path / "key.txt"
    write_text_atomic(path, "secret", mode=0o600)
    assert path.read_text() == "secret"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({"hide_locked_descriptions": True}, DescriptionHiding.ALL),
        ({"hide_locked_descriptions": False}, DescriptionHiding.OFF),
        ({"hide_descriptions": "story", "hide_locked_descriptions": True}, DescriptionHiding.STORY),
    ],
)
def test_spoiler_setting_reads_the_older_on_off_form(tmp_path, stored, expected):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(stored))
    assert load_settings(path).hide_descriptions is expected


def test_untested_note_device_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(untested_note="TRIMUI_BRICK"))
    assert load_settings(path).untested_note == "TRIMUI_BRICK"
    path.write_text(json.dumps({"untested_note": 5}))
    assert load_settings(path).untested_note == ""
