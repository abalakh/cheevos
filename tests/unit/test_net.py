import calendar
import urllib.error
from contextlib import contextmanager
from email.message import Message

import pytest

from cheevos.core.net import clock_plausible, is_online


def recording_opener(calls, outcome=None):
    @contextmanager
    def opener(request, timeout, context):
        calls.append((request.get_method(), request.full_url, timeout, context))
        if outcome is not None:
            raise outcome
        yield object()

    return opener


def test_online_when_host_answers():
    calls = []
    assert is_online(opener=recording_opener(calls), timeout=1.5)
    assert calls == [("HEAD", "https://retroachievements.org/", 1.5, None)]


def test_http_error_still_counts_as_online():
    error = urllib.error.HTTPError("https://x/", 503, "busy", Message(), None)
    assert is_online(opener=recording_opener([], error))


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("no route"), TimeoutError("slow"), OSError("tls"), ValueError("odd")],
)
def test_offline_on_connection_failures(error, caplog):
    caplog.set_level("INFO")
    assert not is_online(host="example.org", opener=recording_opener([], error))
    assert "unreachable" in caplog.text


def test_default_opener_is_used_without_network(monkeypatch):
    calls = []
    monkeypatch.setattr("urllib.request.urlopen", recording_opener(calls))
    assert is_online()
    assert calls[0][0] == "HEAD"


def test_clock_plausibility():
    assert not clock_plausible(0)  # 1970: before NTP sync on a device without RTC
    assert not clock_plausible(calendar.timegm((2025, 12, 31, 23, 59, 59)))
    assert clock_plausible(calendar.timegm((2026, 1, 1, 0, 0, 0)))
    assert clock_plausible(calendar.timegm((2026, 1, 1, 0, 0, 0)), min_year=2026)
    assert not clock_plausible(calendar.timegm((2026, 6, 1, 0, 0, 0)), min_year=2027)
    assert clock_plausible()
