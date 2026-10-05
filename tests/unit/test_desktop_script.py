import pytest

from cheevos.platform.desktop.script import Capture, Press, ScriptError, Wait, parse_script


def test_parses_buttons_and_captures_in_order():
    assert parse_script("shot:home, down,DOWN , a,shot:game_detail") == [
        Capture("home"),
        Press("DPAD_DOWN"),
        Press("DPAD_DOWN"),
        Press("A"),
        Capture("game_detail"),
    ]


def test_ignores_empty_tokens():
    assert parse_script(" , ,b,") == [Press("B")]


def test_empty_script():
    assert parse_script("") == []


def test_parses_waits():
    assert parse_script("wait:3,a") == [Wait(3), Press("A")]


@pytest.mark.parametrize("script", ["jump", "shot:", "shot:a/b", "wait:", "wait:0", "wait:x"])
def test_rejects_invalid_tokens(script):
    with pytest.raises(ScriptError):
        parse_script(script)
