import json
import logging
import sqlite3
from urllib.parse import parse_qsl, urlsplit

import pytest
from fake_proxy import proxy_database

from cheevos.core.errors import NetworkError
from cheevos.core.identification.hash_lookup import (
    MISS_TTL_MS,
    UNKNOWN,
    CachedAnswer,
    ProxyHashCache,
    RaHashLookup,
    parse_gameid_response,
    resolve,
)
from cheevos.core.identification.result import Identification, IdentificationError
from cheevos.core.ra_client.transport import Response

NOW = 1_800_000_000.0
NOW_MS = int(NOW * 1000)
H1, H2, H3 = "1" * 32, "2" * 32, "3" * 32


def body(**fields):
    return json.dumps(fields)


@pytest.fixture
def cache_at(tmp_path):
    def make(entries, **kwargs):
        database = proxy_database(tmp_path, entries, **kwargs)
        return ProxyHashCache(database, now=lambda: NOW), database

    return make


# --- RAOfflineProxy's cache, read-only ---------------------------------------------------------


def test_cached_gameid_match(cache_at):
    cache, _ = cache_at({f"gameid:{H1}": (body(Success=True, GameID=1479), 0)})
    assert cache.lookup(H1) == CachedAnswer(game_id=1479)


def test_cached_achievementsets_match(cache_at):
    cache, _ = cache_at({f"achievementsets:{H1}:player": (body(GameId=228, Sets=[]), 0)})
    assert cache.lookup(H1) == CachedAnswer(game_id=228)


def test_a_gameid_match_comes_before_achievementsets(cache_at):
    cache, _ = cache_at(
        {
            f"gameid:{H1}": (body(Success=True, GameID=1), 0),
            f"achievementsets:{H1}:player": (body(GameId=2), 0),
        }
    )
    assert cache.lookup(H1).game_id == 1


def test_achievementsets_win_over_a_cached_miss(cache_at):
    cache, _ = cache_at(
        {
            f"gameid:{H1}": (body(Success=True, GameID=0), NOW_MS),
            f"achievementsets:{H1}:player": (body(GameId=2), 0),
        }
    )
    assert cache.lookup(H1).game_id == 2


@pytest.mark.parametrize(
    ("cached_at", "expected"),
    [
        (NOW_MS - 1000, CachedAnswer(miss=True)),
        (NOW_MS - MISS_TTL_MS + 1, CachedAnswer(miss=True)),
        (NOW_MS - MISS_TTL_MS, UNKNOWN),  # a week old: ask RA again
        (NOW_MS + 60_000, UNKNOWN),  # the clock went back
    ],
)
def test_cached_miss_lasts_a_week(cache_at, cached_at, expected):
    cache, _ = cache_at({f"gameid:{H1}": (body(Success=True, GameID=0), cached_at)})
    assert cache.lookup(H1) == expected


@pytest.mark.parametrize(
    "response",
    [
        body(GameID=0),  # no explicit Success
        body(Success=False, Code="invalid_credentials", GameID=0),
        body(Success=True, GameID=False),
        body(Success=True, GameID=True),
        body(Success=True, GameID="12"),
        body(Success=True, GameID=-3),
        "[1, 2]",
        "<html>",
    ],
)
def test_unusable_cached_answers_are_unknown(cache_at, response):
    cache, _ = cache_at(
        {
            f"gameid:{H1}": (response, NOW_MS),
            f"achievementsets:{H1}:player": (body(GameId=True), 0),
        }
    )
    assert cache.lookup(H1) == UNKNOWN


def test_missing_database_is_unknown_and_never_created(tmp_path):
    database = tmp_path / "App" / "RAOfflineProxy" / "data" / "proxy.sqlite3"
    cache = ProxyHashCache(database, now=lambda: NOW)

    assert cache.lookup(H1) == UNKNOWN
    assert not database.exists()
    assert not database.parent.exists()


def test_unfamiliar_schema_is_unknown(cache_at, caplog):
    cache, _ = cache_at({}, ddl="CREATE TABLE api_cache (cacheKey TEXT, responseBody TEXT);")
    assert cache.lookup(H1) == UNKNOWN
    assert "schema changed" in caplog.text


def test_corrupt_database_is_unknown(tmp_path):
    database = tmp_path / "proxy.sqlite3"
    database.write_bytes(b"SQLite format 3\x00" + b"\xff" * 200)
    assert ProxyHashCache(database, now=lambda: NOW).lookup(H1) == UNKNOWN


def test_reading_never_writes_the_proxy_database(cache_at):
    cache, database = cache_at({f"gameid:{H1}": (body(Success=True, GameID=0), NOW_MS)})
    before = (database.read_bytes(), database.stat().st_mtime_ns)
    files_before = sorted(database.parent.iterdir())

    cache.lookup(H1)
    cache.lookup(H2)
    cache.close()

    assert (database.read_bytes(), database.stat().st_mtime_ns) == before
    assert sorted(database.parent.iterdir()) == files_before


def test_the_connection_is_read_only(cache_at):
    cache, _ = cache_at({})
    cache.lookup(H1)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        cache._connection.execute("DELETE FROM api_cache")


# --- RA's answer -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (200, {"Success": True, "GameID": 1479}, 1479),
        (200, {"GameID": 1479}, 1479),
        (200, {"Success": True, "GameID": 1_200_001_479}, 1_200_001_479),
        (200, {"Success": True, "GameID": 0}, None),
    ],
)
def test_gameid_answers(status, payload, expected):
    assert parse_gameid_response(status, json.dumps(payload).encode()) == expected


@pytest.mark.parametrize(
    ("status", "raw", "reason"),
    [
        (200, body(GameID=0), "response"),  # a zero without Success isn't a confirmed miss
        (200, body(Success=True, GameID=True), "response"),
        (200, body(Success=True, GameID="1479"), "response"),
        (200, body(Success=True), "response"),
        (200, body(Success=False, Code="invalid_parameter", Error="..."), "response"),
        (200, "[]", "response"),
        (200, "<html>captive portal</html>", "response"),
        (200, "", "response"),
        (401, body(Success=False, Code="invalid_credentials"), "auth"),
        (403, body(Success=False, Code="access_denied"), "auth"),
        (403, body(Success=False, Code="unsupported_client", GameID=0), "response"),
        (429, "", "rate_limited"),
        (500, "", "network"),
        (503, body(Success=False), "network"),
        (404, "<html>Not Found</html>", "network"),
        (422, body(Success=False, Code="missing_parameter"), "response"),
    ],
)
def test_unusable_gameid_answers_are_errors(status, raw, reason):
    with pytest.raises(IdentificationError) as error:
        parse_gameid_response(status, raw.encode())
    assert error.value.reason == reason


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, host, path, headers):
        self.calls.append((host, path, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ok(game_id):
    return Response(status=200, body=json.dumps({"Success": True, "GameID": game_id}).encode())


def test_ra_lookup_sends_only_the_hash():
    transport = Transport(ok(1479))

    assert RaHashLookup(transport, "Cheevos/test").game_id(H1) == 1479

    host, path, headers = transport.calls[0]
    assert host == "retroachievements.org"
    assert urlsplit(path).path == "/dorequest.php"
    assert dict(parse_qsl(urlsplit(path).query)) == {"r": "gameid", "m": H1}
    assert headers["User-Agent"] == "Cheevos/test"


def test_ra_lookup_unreachable_is_offline():
    lookup = RaHashLookup(Transport(NetworkError("DNS failure")), "Cheevos/test")

    with pytest.raises(IdentificationError) as error:
        lookup.game_id(H1)
    assert error.value.reason == "offline"


def test_ra_lookups_are_spaced_like_the_proxy():
    clock = [100.0]
    sleeps = []
    lookup = RaHashLookup(
        Transport(ok(0), ok(0)), "Cheevos/test", clock=lambda: clock[0], sleep=sleeps.append
    )

    lookup.game_id(H1)
    clock[0] += 0.1
    lookup.game_id(H2)

    assert sleeps == [pytest.approx(0.2)]


# --- the order of candidates -------------------------------------------------------------------


class Resolver:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def game_id(self, hash_value):
        self.asked.append(hash_value)
        answer = self.answers[hash_value]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_first_candidate_with_a_game_wins_in_hasher_order(cache_at):
    # H1 is unknown to the proxy; H2 has a cached match. RA is asked about H1 first.
    cache, _ = cache_at({f"gameid:{H2}": (body(Success=True, GameID=2), 0)})
    ra = Resolver({H1: 1})

    assert resolve((H1, H2), cache, lambda: ra) == Identification.matched(1)
    assert ra.asked == [H1]


def test_a_cached_miss_skips_ra_for_that_candidate(cache_at):
    cache, _ = cache_at({f"gameid:{H1}": (body(Success=True, GameID=0), NOW_MS)})
    ra = Resolver({H2: 5})

    assert resolve((H1, H2), cache, lambda: ra) == Identification.matched(5)
    assert ra.asked == [H2]


def test_every_candidate_missing_is_no_match(cache_at):
    cache, _ = cache_at({})
    ra = Resolver({H1: None, H2: None})

    assert resolve((H1, H2), cache, lambda: ra) == Identification.no_match()


@pytest.mark.parametrize(
    ("ra_id", "game_id"),
    [
        (1479, 1479),
        (1_000_001_479, 1479),  # incompatible hash
        (1_100_001_479, 1479),  # untested hash
        (1_200_001_479, 1479),  # patch required
        (1_000_000_000, 1_000_000_000),  # RAWeb decodes only IDs above a base
    ],
)
def test_virtual_game_ids_decode_to_the_game(cache_at, ra_id, game_id):
    cache, _ = cache_at({f"gameid:{H1}": (body(Success=True, GameID=ra_id), 0)})
    ra = Resolver({H2: ra_id})

    assert resolve((H1,), cache, lambda: ra) == Identification.matched(game_id)
    assert resolve((H2,), cache, lambda: ra) == Identification.matched(game_id)


def test_the_hash_compatibility_is_logged(cache_at, caplog):
    caplog.set_level(logging.INFO)
    cache, _ = cache_at({})

    resolve((H1,), cache, lambda: Resolver({H1: 1_100_001_479}))

    assert "Matched game 1479 from RA (hash: untested)" in caplog.text


def test_cached_answers_create_no_ra_lookup(cache_at):
    cache, _ = cache_at({f"gameid:{H1}": (body(Success=True, GameID=9), 0)})

    def no_network():
        raise AssertionError("RA must not be contacted")

    assert resolve((H1,), cache, no_network) == Identification.matched(9)


def test_an_error_stops_at_that_candidate(cache_at):
    cache, _ = cache_at({})
    ra = Resolver({H1: IdentificationError("offline"), H2: 2})

    with pytest.raises(IdentificationError):
        resolve((H1, H2), cache, lambda: ra)
    assert ra.asked == [H1]


def test_candidates_are_normalised_and_validated(cache_at):
    cache, _ = cache_at({})
    ra = Resolver({H3: 3})

    assert resolve((" " + H3.upper() + " ",), cache, lambda: ra) == Identification.matched(3)
    with pytest.raises(IdentificationError) as error:
        resolve(("not-a-hash",), cache, lambda: ra)
    assert error.value.reason == "hash"
