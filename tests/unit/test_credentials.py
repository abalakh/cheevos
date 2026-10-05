import json
import logging

import pytest

from cheevos.core.credentials import (
    looks_like_api_key,
    read_api_key,
    read_retroarch_setting,
    read_spruce_ra_setting,
    read_username,
    save_api_key,
)
from cheevos.platform.paths import Paths

KEY = "A" * 16 + "b" * 8 + "12345678"


def spruce_config(paths: Paths, *, username: str = "", stored_pw_field: str = "x") -> None:
    paths.spruce_config.parent.mkdir(parents=True, exist_ok=True)
    paths.spruce_config.write_text(
        json.dumps(
            {
                "menuOptions": {
                    "RetroAchievements Settings": {
                        "modeToggle": {"options": ["Manual", "Disabled"], "selected": "Manual"},
                        "username": {"type": "freeText", "selected": username},
                        "password": {"type": "freeText", "selected": stored_pw_field},
                        "enableOfflineProxy": {"options": ["True", "False"], "selected": "False"},
                    }
                }
            }
        )
    )


def retroarch_config(paths: Paths, text: str) -> None:
    paths.retroarch_config.parent.mkdir(parents=True, exist_ok=True)
    paths.retroarch_config.write_text(text)


@pytest.fixture
def paths(tmp_path):
    return Paths(sdcard=tmp_path, platform="MiyooMini")


def test_username_from_spruce_settings(paths):
    spruce_config(paths, username="  Balah ")
    retroarch_config(paths, 'cheevos_username = "Other"\n')
    assert read_username(paths) == "Balah"


def test_username_falls_back_to_retroarch_in_manual_mode(paths):
    spruce_config(paths, username="")
    retroarch_config(
        paths,
        '# comment\ncheevos_enable = "true"\ncheevos_username = "Balah"\ncheevos_password = ""\n',
    )
    assert read_username(paths) == "Balah"


def test_no_username_anywhere(paths):
    spruce_config(paths, username="  ")
    retroarch_config(paths, 'cheevos_username = ""\n')
    assert read_username(paths) is None


def test_no_config_files(paths):
    assert read_username(paths) is None
    assert read_spruce_ra_setting(paths, "username") is None


def test_corrupt_or_unexpected_spruce_config(paths, caplog):
    paths.spruce_config.parent.mkdir(parents=True)
    paths.spruce_config.write_text("{broken")
    assert read_spruce_ra_setting(paths, "username") is None
    assert "Cannot read Spruce settings" in caplog.text
    paths.spruce_config.write_text(json.dumps({"menuOptions": []}))
    assert read_spruce_ra_setting(paths, "username") is None
    paths.spruce_config.write_text(
        json.dumps({"menuOptions": {"RetroAchievements Settings": {"username": {"selected": 5}}}})
    )
    assert read_spruce_ra_setting(paths, "username") is None


def test_password_is_never_returned(paths):
    spruce_config(paths, username="", stored_pw_field="hunter2")
    retroarch_config(paths, 'cheevos_password = "hunter2"\n')
    assert read_username(paths) is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('cheevos_username = "Balah"', "Balah"),
        ('cheevos_username="Balah"', "Balah"),
        ("cheevos_username = Balah # trailing comment", "Balah"),
        ('cheevos_username = "Bal ah" # quoted spaces', "Bal ah"),
        ('cheevos_username = "unterminated', "unterminated"),
        ('cheevos_username = ""', ""),
    ],
)
def test_retroarch_value_forms(tmp_path, line, expected):
    cfg = tmp_path / "retroarch.cfg"
    cfg.write_text(f"{line}\n")
    assert read_retroarch_setting(cfg, "cheevos_username") == expected


def test_retroarch_last_occurrence_wins_and_ignores_similar_keys(tmp_path):
    cfg = tmp_path / "retroarch.cfg"
    cfg.write_text(
        'cheevos_username_extra = "nope"\n'
        '#cheevos_username = "commented"\n'
        "garbage line without equals\n"
        'cheevos_username = "first"\n'
        'cheevos_username = "second"\n'
    )
    assert read_retroarch_setting(cfg, "cheevos_username") == "second"
    assert read_retroarch_setting(cfg, "missing_key") is None
    assert read_retroarch_setting(tmp_path / "absent.cfg", "cheevos_username") is None


def test_retroarch_config_override(tmp_path):
    custom = tmp_path / "custom.cfg"
    custom.write_text('cheevos_username = "Override"\n')
    paths = Paths(sdcard=tmp_path, retroarch_config_override=custom)
    assert read_username(paths) == "Override"


def test_api_key_round_trip(paths):
    assert read_api_key(paths) is None
    save_api_key(paths, f"  {KEY}\n")
    assert paths.api_key_file.read_text() == f"{KEY}\n"
    assert read_api_key(paths) == KEY


def test_api_key_first_non_empty_line(paths):
    paths.api_key_file.parent.mkdir(parents=True)
    paths.api_key_file.write_text(f"\n   \n {KEY} \nsecond\n")
    assert read_api_key(paths) == KEY
    paths.api_key_file.write_text("\n \n")
    assert read_api_key(paths) is None


def test_saving_the_key_never_logs_it(paths, caplog):
    caplog.set_level("DEBUG")
    save_api_key(paths, KEY)
    assert KEY not in caplog.text


def test_a_key_read_from_the_file_is_masked_in_logs_at_once(paths, caplog):
    other = "B" * 32
    paths.api_key_file.parent.mkdir(parents=True, exist_ok=True)
    paths.api_key_file.write_text(other + "\n")
    assert read_api_key(paths) == other
    caplog.set_level("DEBUG")
    logging.getLogger("other.library").error("rendering %s failed", other)
    assert other not in caplog.text


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (KEY, True),
        (f"  {KEY}\n", True),
        (KEY[:-1], False),
        (KEY + "x", False),
        (KEY[:-1] + "-", False),
        ("é" * 32, False),
        ("", False),
    ],
)
def test_api_key_shape(text, ok):
    assert looks_like_api_key(text) is ok
