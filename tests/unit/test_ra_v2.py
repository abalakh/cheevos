import json
from urllib.parse import parse_qsl, urlsplit

import pytest

from cheevos.core.errors import AuthError
from cheevos.core.ra_client import RaClient, Response
from cheevos.core.ra_client.transport import API_V2_HOST

KEY = "TESTKEY0123456789abcdefTESTKEY01"


class ScriptedTransport:
    """Returns scripted responses in order and records (host, path, params, headers)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, host, path, headers):
        parts = urlsplit(path)
        self.calls.append((host, parts.path, dict(parse_qsl(parts.query)), headers))
        return self.responses.pop(0)


def ok(data):
    return Response(status=200, body=json.dumps(data).encode())


def make(transport):
    return RaClient("Balah", KEY, transport, user_agent="Cheevos/test", min_interval=0)


def events_page(last, *event_ids):
    data = [
        {"id": str(event_id), "attributes": {"title": f"E{event_id}"}} for event_id in event_ids
    ]
    return ok({"meta": {"page": {"lastPage": last}}, "data": data, "included": []})


def test_v2_events_send_the_key_in_a_header_fifty_ids_at_a_time():
    ids = list(range(1, 61))
    transport = ScriptedTransport(events_page(1, *ids[:50]), events_page(1, *ids[50:]))
    events = make(transport).events([*reversed(ids), 1])
    assert [event.event_id for event in events] == ids
    for (host, path, params, headers), chunk in zip(
        transport.calls, (ids[:50], ids[50:]), strict=True
    ):
        assert (host, path) == (API_V2_HOST, "/v2/events")
        assert params == {
            "filter[id]": ",".join(map(str, chunk)),
            "include": "awards",
            "page[size]": "50",
            "page[number]": "1",
        }
        assert headers["X-API-Key"] == KEY  # never in the URL
        assert headers["Accept"] == "application/vnd.api+json"
        assert headers["User-Agent"] == "Cheevos/test"


def test_v2_events_follow_their_pages():
    transport = ScriptedTransport(events_page(2, 1), events_page(2, 2))
    assert [event.event_id for event in make(transport).events([1, 2])] == [1, 2]
    assert [call[2]["page[number]"] for call in transport.calls] == ["1", "2"]


def test_v2_event_points_add_up_across_pages():
    def points(last, *rows):
        data = [
            {
                "attributes": {"achievementPoints": value},
                "relationships": {"event": {"data": {"type": "events", "id": str(event_id)}}},
            }
            for event_id, value in rows
        ]
        return ok({"meta": {"page": {"lastPage": last}}, "data": data})

    transport = ScriptedTransport(points(2, (7, 3), (9, 1)), points(2, (7, 3)))
    assert make(transport).event_points([9, 7]) == {7: 6, 9: 1}
    host, path, params, headers = transport.calls[0]
    assert (host, path) == (API_V2_HOST, "/v2/event-achievements")
    assert params["filter[eventId]"] == "7,9"
    assert params["fields[event-achievements]"] == "achievementPoints,event"
    assert headers["X-API-Key"] == KEY
    assert make(ScriptedTransport()).event_points([]) == {}


def test_v2_rejected_key_is_auth_error():
    transport = ScriptedTransport(Response(status=401, body=b'{"errors":[{"status":"401"}]}'))
    with pytest.raises(AuthError):
        make(transport).events([1])
