import pytest

from cheevos.core.errors import NetworkError
from cheevos.core.net import is_online
from cheevos.core.ra_client.transport import Response


class Probe:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []
        self.closed = False

    def head(self, host, path, headers):
        self.calls.append((host, path, headers))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def close(self):
        self.closed = True


@pytest.mark.parametrize("status", [200, 301, 401, 429, 503])
def test_any_http_answer_counts_as_online(status):
    probe = Probe(Response(status))
    assert is_online(transport=probe)
    assert probe.calls == [("retroachievements.org", "/", {})]
    assert not probe.closed


@pytest.mark.parametrize("error", [NetworkError("offline"), ValueError("odd")])
def test_connection_failure_counts_as_offline(error, caplog):
    probe = Probe(error)
    caplog.set_level("INFO")
    assert not is_online(host="example.org", transport=probe)
    assert "unreachable" in caplog.text


@pytest.mark.parametrize("outcome", [Response(200), NetworkError("offline")])
def test_default_transport_is_closed_and_receives_timeout(monkeypatch, outcome):
    probe = Probe(outcome)
    timeouts = []

    def factory(*, timeout):
        timeouts.append(timeout)
        return probe

    monkeypatch.setattr("cheevos.core.net.HttpTransport", factory)
    assert is_online(timeout=1.5) == isinstance(outcome, Response)
    assert timeouts == [1.5]
    assert probe.closed
