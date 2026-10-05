import time

import pytest

from cheevos.ui import format as fmt
from cheevos.ui.pyui.text import _plain

NOW = 1_791_158_400


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (5, "just now"),
        (5 * 60, "5 min ago"),
        (3 * 3600, "3 h ago"),
        (30 * 3600, "yesterday"),
        (3 * 86400, "3 days ago"),
    ],
)
def test_ago_relative(elapsed, expected):
    assert fmt.ago(NOW - elapsed, NOW) == expected


def test_ago_falls_back_to_date_after_a_week():
    then = NOW - 10 * 86400
    assert fmt.ago(then, NOW) == time.strftime("%d %b %Y", time.localtime(then))


def test_ago_handles_missing_and_future():
    assert fmt.ago(None, NOW) == ""
    assert fmt.ago(NOW + 60, NOW) == "just now"


def test_points_and_numbers():
    assert fmt.points(1) == "1 pt"
    assert fmt.points(5) == "5 pts"
    assert fmt.number(12843) == "12,843"


@pytest.mark.parametrize(
    ("fraction", "expected"), [(0.41, "41%"), (0.035, "3.5%"), (0.004, "0.4%"), (0, "0%")]
)
def test_percent(fraction, expected):
    assert fmt.percent(fraction) == expected


@pytest.mark.parametrize(
    ("size", "expected"), [(512, "512 B"), (2048, "2.0 KB"), (1_887_437, "1.8 MB")]
)
def test_size(size, expected):
    assert fmt.size(size) == expected


def test_dates_empty_for_none():
    assert fmt.local_datetime(None) == ""
    assert fmt.local_date(None) == ""


@pytest.mark.parametrize(
    ("char", "plain"), [("é", "e"), ("Ü", "U"), ("ñ", "n"), ("ß", "ß"), ("a", "a")]
)
def test_accents_fall_back_to_the_plain_letter(char, plain):

    assert _plain(char) == plain
