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
    loaded = load_settings(tmp_path / "settings.json")
    assert loaded == DEFAULTS
    assert loaded.achievement_grid is True
    assert loaded.awards_view == "carousel"
    assert Settings(BadgeScope.ON_DEVICE_AND_RECENT, 30, DescriptionHiding.OFF, True) == DEFAULTS


@pytest.mark.parametrize("sort", ["order", "unlocked", "locked", "points", "rarity"])
def test_round_trip(tmp_path, sort):
    path = tmp_path / "cheevos" / "settings.json"
    settings = Settings(
        BadgeScope.ALL,
        90,
        DescriptionHiding.STORY,
        False,
        game_list_details=True,
        achievement_grid=True,
        achievement_sort=sort,
        awards_view="list",
    )
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
        "achievement_grid",
        "achievement_sort",
        "awards_view",
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
                "achievement_grid": "grid",
                "achievement_sort": "title",
                "awards_view": "wall",
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


def test_older_file_defaults_the_new_view_without_resetting_existing_choices(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"auto_sync": False, "game_list_details": True}))
    assert load_settings(path) == Settings(auto_sync=False, game_list_details=True)


@pytest.mark.parametrize("sort", [None, True, 3, "title", ["points"], {"sort": "rarity"}])
def test_invalid_achievement_sort_keeps_other_preferences(tmp_path, sort):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"achievement_grid": True, "achievement_sort": sort}))
    assert load_settings(path) == Settings(achievement_grid=True)


@pytest.mark.parametrize("grid", [False, True])
@pytest.mark.parametrize("view", ["carousel", "grid", "list"])
def test_saved_view_preferences_are_preserved_independently(tmp_path, grid, view):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(achievement_grid=grid, awards_view=view))
    stored = path.read_bytes()
    loaded = load_settings(path)
    assert (loaded.awards_view, loaded.achievement_grid) == (view, grid)
    assert path.read_bytes() == stored


@pytest.mark.parametrize("view", [None, True, "wall", "Grid", ["list"]])
def test_absent_or_invalid_awards_view_is_the_carousel(tmp_path, view):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"achievement_grid": True, "awards_view": view}))
    assert load_settings(path) == Settings(achievement_grid=True, awards_view="carousel")
    path.write_text(json.dumps({"achievement_grid": True}))
    assert load_settings(path).awards_view == "carousel"


def test_unknown_fields_are_ignored_and_dropped_on_save(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"achievement_grid": True, "removed_setting": "old"}))
    settings = load_settings(path)
    assert settings == Settings(achievement_grid=True)
    save_settings(path, settings)
    assert "removed_setting" not in json.loads(path.read_text())


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
