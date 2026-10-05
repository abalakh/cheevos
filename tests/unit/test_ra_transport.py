import http.client
import ssl
from pathlib import Path

import pytest

from cheevos.core.errors import NetworkError
from cheevos.core.ra_client.transport import (
    API_HOST,
    MEDIA_HOST,
    FixtureTransport,
    HttpTransport,
    default_ssl_context,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"


# --- FixtureTransport -------------------------------------------------------------------------


def test_fixture_exact_match_by_params():
    transport = FixtureTransport(FIXTURES)
    response = transport.get(
        API_HOST, "/API/API_GetGameInfoAndUserProgress.php?y=K&u=U&g=519&a=1", {}
    )
    assert response.status == 200
    assert b"Final Fantasy Tactics Advance" in response.body
    assert transport.calls == [("API_GetGameInfoAndUserProgress", {"g": "519", "a": "1"})]


def test_fixture_single_recording_ignores_params():
    transport = FixtureTransport(FIXTURES)
    response = transport.get(API_HOST, "/API/API_GetUserSummary.php?y=K&u=U&g=0&a=3", {})
    assert response.status == 200
    assert b'"User": "Balah"' in response.body


def test_fixture_unknown_request_is_404():
    transport = FixtureTransport(FIXTURES)
    missing_game = transport.get(
        API_HOST, "/API/API_GetGameInfoAndUserProgress.php?g=99999&a=1", {}
    )
    unknown_endpoint = transport.get(API_HOST, "/API/API_GetNothing.php", {})
    assert missing_game.status == 404
    assert unknown_endpoint.status == 404


def test_fixture_never_records_credentials():
    transport = FixtureTransport(FIXTURES)
    transport.get(API_HOST, "/API/API_GetUserProfile.php?y=SECRET&u=Balah", {})
    assert transport.calls == [("API_GetUserProfile", {})]


def test_fixture_media(tmp_path):
    (tmp_path / "Badge").mkdir()
    (tmp_path / "Badge" / "1.png").write_bytes(b"png")
    (tmp_path.parent / "outside.png").write_bytes(b"secret")
    transport = FixtureTransport(FIXTURES, media_dir=tmp_path)
    assert transport.get(MEDIA_HOST, "/Badge/1.png", {}).body == b"png"
    assert transport.get(MEDIA_HOST, "/Badge/2.png", {}).status == 404
    assert transport.get(MEDIA_HOST, "/../outside.png", {}).status == 404
    assert FixtureTransport(FIXTURES).get(MEDIA_HOST, "/Badge/1.png", {}).status == 404


# --- HttpTransport ----------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self._headers = headers
        self._body = body

    def read(self):
        return self._body

    def getheaders(self):
        return list(self._headers.items())


class FakeConnection:
    """Replays scripted outcomes: an exception to raise, or (status, headers, body)."""

    def __init__(self, host, timeout, context, script):
        self.host = host
        self.timeout = timeout
        self.context = context
        self.script = script
        self.requests = []
        self.closed = False

    def request(self, method, url, *, headers):
        self.requests.append((method, url, headers))
        outcome = self.script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        self._pending = outcome

    def getresponse(self):
        return FakeResponse(*self._pending)

    def close(self):
        self.closed = True


class Factory:
    def __init__(self, *script):
        self.script = list(script)
        self.connections = []

    def __call__(self, host, timeout, context):
        connection = FakeConnection(host, timeout, context, self.script)
        self.connections.append(connection)
        return connection


OK = (200, {"Content-Type": "application/json", "Retry-After": "5"}, b"{}")


def make(factory):
    return HttpTransport(
        timeout=3.0, connection_factory=factory, ssl_context=ssl.create_default_context()
    )


def test_http_success_and_lowercased_headers():
    factory = Factory(OK)
    response = make(factory).get(API_HOST, "/API/x.php", {"User-Agent": "t"})
    assert response.status == 200
    assert response.headers == {"content-type": "application/json", "retry-after": "5"}
    assert response.body == b"{}"
    connection = factory.connections[0]
    assert (connection.host, connection.timeout) == (API_HOST, 3.0)
    assert connection.requests == [("GET", "/API/x.php", {"User-Agent": "t"})]


def test_http_keeps_one_connection_per_host():
    factory = Factory(OK, OK, OK)
    transport = make(factory)
    transport.get(API_HOST, "/a", {})
    transport.get(API_HOST, "/b", {})
    transport.get(MEDIA_HOST, "/c", {})
    assert [c.host for c in factory.connections] == [API_HOST, MEDIA_HOST]


@pytest.mark.parametrize(
    "dropped",
    [http.client.RemoteDisconnected("gone"), BrokenPipeError(), ConnectionResetError()],
)
def test_http_reconnects_once_after_dropped_keepalive(dropped):
    factory = Factory(dropped, OK)
    response = make(factory).get(API_HOST, "/a", {})
    assert response.status == 200
    assert len(factory.connections) == 2
    assert factory.connections[0].closed


def test_http_gives_up_after_second_drop():
    factory = Factory(ConnectionResetError(), ConnectionResetError())
    with pytest.raises(NetworkError, match=API_HOST):
        make(factory).get(API_HOST, "/a", {})
    assert len(factory.connections) == 2


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        ssl.SSLError("bad cert"),
        OSError("unreachable"),
        http.client.BadStatusLine("x"),
    ],
)
def test_http_maps_failures_to_network_error_and_discards_connection(error):
    factory = Factory(error, OK)
    transport = make(factory)
    with pytest.raises(NetworkError):
        transport.get(API_HOST, "/a", {})
    assert factory.connections[0].closed
    assert transport.get(API_HOST, "/b", {}).status == 200
    assert len(factory.connections) == 2


def test_http_close_closes_all_connections():
    factory = Factory(OK, OK)
    transport = make(factory)
    transport.get(API_HOST, "/a", {})
    transport.get(MEDIA_HOST, "/b", {})
    transport.close()
    assert all(connection.closed for connection in factory.connections)


def test_http_close_ignores_errors():
    factory = Factory(OK)
    transport = make(factory)
    transport.get(API_HOST, "/a", {})

    def broken_close():
        raise OSError("already closed")

    factory.connections[0].close = broken_close
    transport.close()


def test_default_ssl_context_uses_cert_file(monkeypatch, tmp_path):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    assert default_ssl_context().verify_mode == ssl.CERT_REQUIRED
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    with pytest.raises(FileNotFoundError):
        default_ssl_context()


def test_default_connection_factory_is_lazy():
    transport = HttpTransport()
    connection = transport._connection("example.invalid")  # no socket is opened yet
    assert isinstance(connection, http.client.HTTPSConnection)
    transport.close()
