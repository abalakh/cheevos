import datetime as dt
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cheevos.platform.desktop.__main__ import _fix_top_bar_clock, check_language, parse_options
from cheevos.ui import language


def test_clock_is_parsed_as_a_time_of_day():
    assert parse_options(["--clock", "10:30"]).clock == dt.time(10, 30)
    assert parse_options([]).clock is None


def test_clock_must_be_a_time(capsys):
    with pytest.raises(SystemExit):
        parse_options(["--clock", "half past ten"])
    assert "expected HH:MM" in capsys.readouterr().err


def test_fixed_clock_replaces_the_time_pyui_reads(monkeypatch):
    top_bar = SimpleNamespace(datetime=dt.datetime)
    monkeypatch.setitem(sys.modules, "menus.common", SimpleNamespace(top_bar=top_bar))
    _fix_top_bar_clock(dt.time(10, 30))
    # As TopBar.get_current_time_hhmm() reads it, and still formatted by PyUI.
    assert top_bar.datetime.fromtimestamp(time.time()).strftime("%I:%M %p") == "10:30 AM"
    assert top_bar.datetime.now().strftime("%H:%M") == "10:30"


def test_fixed_clock_warns_when_pyui_reads_the_time_another_way(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "menus.common", SimpleNamespace(top_bar=SimpleNamespace()))
    with caplog.at_level(logging.WARNING):
        _fix_top_bar_clock(dt.time(10, 30))
    assert "--clock has no effect" in caplog.text


def test_a_language_gets_its_own_screenshots_folder():
    catalan = parse_options(["--lang", "Catalan"])
    assert catalan.language == "Catalan"
    assert catalan.out_dir.parts[-2:] == ("screens", "Catalan")
    english = parse_options(["--lang", "English"])
    assert english.language is None
    assert english.out_dir.name == "screens"
    assert parse_options(["--lang", "Pseudo", "--out", "shots"]).out_dir == Path("shots")


def test_a_language_needs_a_translation(tmp_path, monkeypatch):
    monkeypatch.setattr(language, "LANG_DIR", tmp_path)
    (tmp_path / "Catalan.json").write_text("{}", encoding="utf-8")
    assert check_language(None) is None
    assert check_language("Catalan") is None
    assert check_language("Pseudo") is None
    problem = check_language("Klingon")
    assert problem is not None
    assert "Translations: Catalan, Pseudo" in problem
