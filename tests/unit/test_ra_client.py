import json
import logging
from calendar import timegm
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest

import cheevos
from cheevos.core.errors import ApiPayloadError, AuthError, NetworkError, RateLimitedError
from cheevos.core.ra_client import FixtureTransport, RaClient, RedactingFilter, Response
from cheevos.core.ra_client.client import default_user_agent
from cheevos.core.ra_client.redact import install_redaction
from cheevos.core.ra_client.transport import API_HOST, MEDIA_HOST

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
KEY = "TESTKEY0123456789abcdefTESTKEY01"


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


class ScriptedTransport:
    """Returns scripted responses in order and records (host, path params) of each call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, host, path, headers):
        parts = urlsplit(path)
        self.calls.append((host, parts.path, dict(parse_qsl(parts.query)), headers))
        return self.responses.pop(0)


def ok(data):
    return Response(status=200, body=json.dumps(data).encode())


def make(transport, clock=None, **kwargs):
    clock = clock or FakeClock()
    return RaClient(
        "Balah",
        KEY,
        transport,
        user_agent="Cheevos/test",
        clock=clock,
        sleep=clock.sleep,
        **kwargs,
    )


# --- happy paths over the recorded fixtures ---------------------------------------------------


def fixture_client(media_dir=None):
    transport = FixtureTransport(FIXTURES, media_dir=media_dir)
    return make(transport), transport


def test_validate_key():
    client, transport = fixture_client()
    assert client.validate_key() is True
    assert transport.calls == [("API_GetUserProfile", {})]


def test_user_summary():
    client, transport = fixture_client()
    profile = client.user_summary(recent_achievements=7)
    assert profile.username == "Balah"
    assert profile.total_ranked == 166966
    assert transport.calls == [("API_GetUserSummary", {"g": "1", "a": "7"})]
    assert profile.last_game_title == "Fire Emblem: The Blazing Blade"


def test_completion_progress():
    client, transport = fixture_client()
    games = client.completion_progress()
    assert len(games) == 7
    assert games[0].title == "Final Fantasy Tactics Advance"
    assert transport.calls == [("API_GetUserCompletionProgress", {"c": "500", "o": "0"})]


def test_recently_played():
    client, transport = fixture_client()
    games = client.recently_played()
    assert len(games) == 12
    assert transport.calls == [("API_GetUserRecentlyPlayedGames", {"c": "50"})]


def test_game_detail():
    client, _ = fixture_client()
    detail = client.game_detail(519)
    assert len(detail.achievements) == 138
    unlocked = {a.achievement_id: a.earned_hardcore_at for a in detail.achievements if a.unlocked}
    assert unlocked == {
        177850: timegm((2026, 8, 21, 17, 2, 50, 0, 0, 0)),
        177851: timegm((2026, 8, 22, 11, 42, 13, 0, 0, 0)),
    }


def test_game_detail_not_recorded_is_payload_error():
    client, _ = fixture_client()
    with pytest.raises(ApiPayloadError, match="404"):
        client.game_detail(99999)


def test_awards():
    client, _ = fixture_client()
    counts, awards = client.awards()
    assert counts.mastered == 0
    assert awards == []


def test_media(tmp_path):
    (tmp_path / "Badge").mkdir()
    (tmp_path / "Badge" / "198102.png").write_bytes(b"\x89PNG")
    client, _ = fixture_client(media_dir=tmp_path)
    assert client.media("/Badge/198102.png") == b"\x89PNG"
    with pytest.raises(ApiPayloadError, match="404"):
        client.media("/Badge/missing.png")
    with pytest.raises(ApiPayloadError, match="invalid media path"):
        client.media("Badge/198102.png")


def test_media_server_error_is_network_error():
    client = make(ScriptedTransport(Response(status=503)))
    with pytest.raises(NetworkError):
        client.media("/Badge/1.png")


# --- request shape ----------------------------------------------------------------------------


def test_requests_carry_credentials_and_user_agent():
    transport = ScriptedTransport(ok({"User": "Balah"}))
    make(transport).validate_key()
    host, path, params, headers = transport.calls[0]
    assert (host, path) == (API_HOST, "/API/API_GetUserProfile.php")
    assert params == {"y": KEY, "u": "Balah"}
    assert headers["User-Agent"] == "Cheevos/test"


def test_media_uses_media_host():
    transport = ScriptedTransport(Response(status=200, body=b"img"))
    make(transport).media("/UserPic/Balah.png")
    assert transport.calls[0][:2] == (MEDIA_HOST, "/UserPic/Balah.png")


def test_default_user_agent():
    assert default_user_agent("MiyooMini") == f"Cheevos/{cheevos.__version__} (SpruceOS; MiyooMini)"


# --- pagination and throttling ----------------------------------------------------------------


def page(total, *game_ids):
    return ok(
        {"Count": len(game_ids), "Total": total, "Results": [{"GameID": g} for g in game_ids]}
    )


def test_completion_progress_paginates_until_total():
    transport = ScriptedTransport(page(3, 1, 2), page(3, 3))
    games = make(transport).completion_progress()
    assert [g.game_id for g in games] == [1, 2, 3]
    assert [call[2]["o"] for call in transport.calls] == ["0", "2"]


def test_completion_progress_stops_on_empty_page():
    transport = ScriptedTransport(page(10, 1), page(10))
    assert [g.game_id for g in make(transport).completion_progress()] == [1]
    assert len(transport.calls) == 2


def test_api_requests_are_throttled():
    clock = FakeClock()
    transport = ScriptedTransport(ok({"User": "a"}), ok({"User": "a"}), Response(200, body=b"img"))
    client = make(transport, clock, min_interval=0.5)
    client.validate_key()
    client.validate_key()
    client.media("/Badge/1.png")
    assert clock.sleeps == [0.5]


def test_no_throttle_wait_when_enough_time_passed():
    clock = FakeClock()
    transport = ScriptedTransport(ok({"User": "a"}), ok({"User": "a"}))
    client = make(transport, clock, min_interval=0.5)
    client.validate_key()
    clock.now += 2
    client.validate_key()
    assert clock.sleeps == []


# --- error mapping ----------------------------------------------------------------------------


UNAUTHENTICATED = {
    "message": "Unauthenticated.",
    "errors": [{"status": "401", "code": "unauthorized", "title": "Unauthenticated."}],
}


@pytest.mark.parametrize(
    "response",
    [
        Response(status=401, body=json.dumps(UNAUTHENTICATED).encode()),
        Response(status=403, body=b"forbidden"),
        ok(UNAUTHENTICATED),
        ok({"errors": [{"code": "unauthorized"}]}),
    ],
)
def test_auth_errors(response):
    with pytest.raises(AuthError):
        make(ScriptedTransport(response)).validate_key()


def test_rate_limit_waits_retry_after_then_succeeds():
    clock = FakeClock()
    transport = ScriptedTransport(
        Response(status=429, headers={"retry-after": "7"}), ok({"User": "Balah"})
    )
    assert make(transport, clock, min_interval=0).validate_key()
    assert clock.sleeps == [7.0]


def test_rate_limit_without_header_uses_backoff_and_gives_up():
    clock = FakeClock()
    transport = ScriptedTransport(*[Response(status=429, headers={"retry-after": "soon"})] * 3)
    with pytest.raises(RateLimitedError) as raised:
        make(transport, clock, min_interval=0, max_retries=2).validate_key()
    assert raised.value.retry_after is None
    assert clock.sleeps == [1.0, 2.0]


def test_rate_limit_error_carries_retry_after():
    transport = ScriptedTransport(*[Response(status=429, headers={"retry-after": "30"})] * 2)
    with pytest.raises(RateLimitedError) as raised:
        make(transport, min_interval=0, max_retries=1).validate_key()
    assert raised.value.retry_after == 30.0


def test_server_errors_back_off_then_fail():
    clock = FakeClock()
    transport = ScriptedTransport(*[Response(status=503)] * 4)
    with pytest.raises(NetworkError, match="503"):
        make(transport, clock, min_interval=0).validate_key()
    assert clock.sleeps == [1.0, 2.0, 4.0]
    assert len(transport.calls) == 4


def test_server_error_then_success():
    clock = FakeClock()
    transport = ScriptedTransport(Response(status=502), ok({"User": "Balah"}))
    assert make(transport, clock, min_interval=0).validate_key()
    assert clock.sleeps == [1.0]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response(status=200, body=b"<html>"), "not valid JSON"),
        (Response(status=404, body=b"{}"), "not found"),
        (Response(status=418, body=b""), "unexpected status"),
        (Response(status=400, body=b"<html>"), "unexpected status"),
    ],
)
def test_payload_errors(response, message):
    with pytest.raises(ApiPayloadError, match=message):
        make(ScriptedTransport(response)).validate_key()


def test_network_errors_propagate():
    class Failing:
        def get(self, host, path, headers):
            raise NetworkError("down")

    with pytest.raises(NetworkError):
        make(Failing()).validate_key()


# --- key redaction ----------------------------------------------------------------------------


def test_api_key_never_reaches_logs(caplog):
    caplog.set_level(logging.DEBUG)
    clock = FakeClock()
    transport = ScriptedTransport(
        Response(status=503), ok({"User": "Balah"}), Response(status=401, body=b"{}")
    )
    client = make(transport, clock, min_interval=0)
    client.validate_key()
    with pytest.raises(AuthError):
        client.validate_key()
    log = logging.getLogger("cheevos.test")
    log.warning("requested https://retroachievements.org/API/x.php?y=%s&u=Balah", KEY)
    log.error("raw key %s in text", KEY)
    logging.getLogger("other.library").info("url ?u=a&y=%s", "zzzz")
    assert caplog.records, "expected log output"
    assert KEY not in caplog.text
    assert "zzzz" not in caplog.text
    assert "y=***" in caplog.text


def fail_with_url():
    raise ValueError(f"bad url /API/x.php?y={KEY}&u=Balah")


def test_tracebacks_are_scrubbed_too(caplog):
    install_redaction(KEY)
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger("cheevos.test")
    try:
        fail_with_url()
    except ValueError:
        log.exception("Sync failed")
    log.warning("where am I", stack_info=True)
    assert "ValueError: bad url /API/x.php?y=***&u=Balah" in caplog.text
    assert KEY not in caplog.text


def test_redacting_filter_on_a_record():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "q?y=%s&u=1", ("abc",), None)
    assert RedactingFilter().filter(record)
    assert record.getMessage() == "q?y=***&u=1"


def test_redacting_filter_leaves_clean_records_alone():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "count=%d", (3,), None)
    RedactingFilter().filter(record)
    assert (record.msg, record.args) == ("count=%d", (3,))


def test_redacting_filter_survives_bad_format_args():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "%d %d y=secret", ("a",), None)
    RedactingFilter().filter(record)
    assert record.getMessage() == "%d %d y=***"


def unlock_row(index: int, date: str) -> dict:
    return {"AchievementID": index, "Date": date, "Points": 5, "HardcoreMode": 1, "GameID": 1}


def test_unlocks_between_pages_past_ras_row_cap(monkeypatch):
    monkeypatch.setattr("cheevos.core.ra_client.client.UNLOCK_PAGE", 3)
    first = [unlock_row(i, f"2026-10-0{i} 10:00:00") for i in (1, 2, 3)]
    second = [unlock_row(3, "2026-10-03 10:00:00"), unlock_row(4, "2026-10-04 10:00:00")]
    transport = ScriptedTransport(ok(first), ok(second))
    unlocks = make(transport).unlocks_between(100, 2_000_000_000)
    assert [u.achievement_id for u in unlocks] == [1, 2, 3, 4]  # the repeated row is dropped
    starts = [call[2]["f"] for call in transport.calls]
    assert starts == ["100", str(unlocks[2].unlocked_at)]
