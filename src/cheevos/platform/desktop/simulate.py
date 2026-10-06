"""Failure and edge-case drills for desktop fixture mode (``CHEEVOS_SIMULATE``).

``offline`` / ``clock`` / ``auth`` make the sync on open fail at that point. ``empty`` serves
an account with no games. ``proxy`` adds an enabled RAOfflineProxy with queued unlocks.
``showcase`` gives the fixture games assorted progress and awards (mastered, completed, beaten
in both modes, mixed hardcore and casual), with achievement lists to match, and a made-up
account, to review progress bars and the awards wall, and to take the screenshots for the docs
(``scripts/doc_screens.py``).
``untested`` pretends to run on a device Cheevos hasn't been tested on (its one-time note).
``setup`` starts without a key file, on the first-run key screen.
``awards`` serves another account's recorded awards (``record_fixtures.py USER --awards-only``)
to review a big awards wall; images the mirror lacks are fetched live from RA's media host.
"""

from __future__ import annotations

import calendar
import dataclasses
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cheevos.core.ra_client.transport import (
    MEDIA_HOST,
    FixtureTransport,
    HttpTransport,
    Response,
    Transport,
)
from cheevos.platform.paths import Paths

SCENARIOS = (
    "offline",
    "clock",
    "auth",
    "empty",
    "proxy",
    "showcase",
    "awards",
    "untested",
    "setup",
)
NOT_FOUND = 404
# Showcase progress per completion-progress game, in fixture order:
# (hardcore share, casual-only share, AwardType, hardcore award?)
_SHOWCASE = (
    (0.30, 0.35, None, False),  # in progress, both kinds: 30% gold + 35% grey = 65%
    (1.00, 0.00, "Mastery/Completion", True),  # mastered
    (0.40, 0.60, "Mastery/Completion", False),  # completed (100%, some casual)
    (0.45, 0.00, "Game Beaten", True),  # beaten in hardcore
    (0.20, 0.30, "Game Beaten", False),  # beaten in casual
    (0.00, 0.54, None, False),  # casual only
    (0.62, 0.00, None, False),  # hardcore only
)
# The showcase's account: made up, so screenshots for the docs show no real player.
_SHOWCASE_PLAYER = {
    "User": "RetroPlayer",
    "UserPic": "/UserPic/RetroPlayer.png",  # not mirrored: the screens show the fallback icon
    "Motto": "",
    "MemberSince": "2021-03-14 18:22:05",
    "TotalPoints": 4210,
    "TotalSoftcorePoints": 385,
    "TotalTruePoints": 9874,
    "Rank": 12345,
    "TotalRanked": 166966,
}
# Unlocks the showcase invents to match its progress are dated before every recorded one, so
# Recent unlocks still starts with the real unlocks (and their screenshots).
_INVENTED_BEFORE = calendar.timegm((2020, 1, 1, 12, 0, 0))
# Showcase unlocks for the last 30 days: (days ago, points, hardcore?)
_SHOWCASE_UNLOCKS = (
    (0, 10, True),
    (1, 25, True),
    (1, 5, False),
    (2, 10, True),
    (4, 50, True),
    (6, 5, True),
    (9, 10, False),
    (11, 25, True),
    (12, 10, True),
    (16, 100, True),
    (21, 5, True),
    (24, 10, True),
    (28, 25, True),
)
_PROXY_DDL = """
CREATE TABLE api_cache (id INTEGER PRIMARY KEY AUTOINCREMENT, cacheKey TEXT NOT NULL UNIQUE,
    responseBody TEXT NOT NULL, sourceRomPath TEXT, cachedAt INTEGER NOT NULL,
    firstCachedAt INTEGER NOT NULL);
CREATE TABLE pending_awards (id INTEGER PRIMARY KEY AUTOINCREMENT,
    achievementId INTEGER NOT NULL UNIQUE, queryString TEXT NOT NULL, requestBody TEXT NOT NULL,
    userAgent TEXT NOT NULL, queuedAt INTEGER NOT NULL, retryCount INTEGER NOT NULL DEFAULT 0,
    lastError TEXT, status TEXT NOT NULL DEFAULT 'pending',
    payloadHash TEXT NOT NULL DEFAULT '', prevHash TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL DEFAULT '', signedAt INTEGER NOT NULL DEFAULT 0);
"""
# FFTA's next two locked progression achievements, cached with the proxy's "patch" data, and
# Descent's first locked one, played with RetroArch 1.22, which caches no "patch" data.
_PENDING = (177852, 177853, 522844)


@dataclass(frozen=True, slots=True)
class Simulation:
    """How a scenario changes the fixture environment.

    Attributes:
        online: Connectivity check result.
        clock_ok: Clock plausibility result.
        transport: Factory for the transport, or ``None`` to keep the fixture one.
        auto_sync: Run a sync when the app opens (to show the failure).
        seeds_card: The transport serves different data, so the pre-sync uses it too.
        device: Pretend to be this PyUI device (e.g. one Cheevos hasn't been tested on).
    """

    online: bool = True
    clock_ok: bool = True
    transport: Callable[[], Transport] | None = None
    auto_sync: bool = False
    seeds_card: bool = False
    device: str | None = None


class _Rejecting:
    """Transport that answers every API call like RA does for a revoked key."""

    def get(self, host: str, path: str, headers: dict[str, str]) -> Response:
        """Return HTTP 401."""
        return Response(status=401, body=b'{"message":"Unauthenticated."}')


class _Showcase:
    """Fixture transport whose games have assorted progress and matching awards.

    Args:
        base: The fixture transport.
    """

    def __init__(self, base: Transport) -> None:
        self._base = base
        self._games: list[dict] = []
        self._targets: dict[int, tuple[int, int]] = {}  # game ID -> (hardcore, all) unlocks

    def get(self, host: str, path: str, headers: dict[str, str]) -> Response:
        """Serve the recording, with progress, awards and recent unlocks rewritten."""
        if "API_GetAchievementsEarnedBetween" in path:
            end = int(parse_qs(urlsplit(path).query).get("t", ["0"])[0]) or int(time.time())
            return Response(status=200, body=json.dumps(_recent_unlocks(end)).encode())
        response = self._base.get(host, path, headers)
        if response.status != 200:  # noqa: PLR2004 — HTTP OK
            return response
        if "API_GetUserSummary" in path or "API_GetUserProfile" in path:
            body = {**json.loads(response.body), **_SHOWCASE_PLAYER}
        elif "API_GetUserCompletionProgress" in path:
            body = self._progress(json.loads(response.body))
        elif "API_GetUserAwards" in path:
            body = self._awards()
        elif "API_GetGameInfoAndUserProgress" in path:
            body = self._game(json.loads(response.body))
        else:
            return response
        return dataclasses.replace(response, body=json.dumps(body).encode())

    def _progress(self, data: dict) -> dict:
        """Give each game one of the showcase shapes.

        Args:
            data: Recorded ``API_GetUserCompletionProgress`` response.

        Returns:
            The rewritten response.
        """
        for game, (hardcore, casual, award, in_hardcore) in zip(
            data["Results"], _SHOWCASE, strict=False
        ):
            total = int(game["MaxPossible"])
            game["NumAwardedHardcore"] = round(total * hardcore)
            game["NumAwarded"] = round(total * (hardcore + casual))
            kind = None
            if award == "Mastery/Completion":
                kind = "mastered" if in_hardcore else "completed"
            elif award == "Game Beaten":
                kind = "beaten-hardcore" if in_hardcore else "beaten-softcore"
            game["HighestAwardKind"] = kind
            game["HighestAwardDate"] = game["MostRecentAwardedDate"] if kind else None
            self._targets[int(game["GameID"])] = (game["NumAwardedHardcore"], game["NumAwarded"])
        self._games = data["Results"]
        return data

    def _game(self, data: dict) -> dict:
        """Unlock a game's achievements to match its showcase progress in the games list.

        The real unlocks stay as recorded (more hardcore ones than the showcase wants become
        casual). Invented ones are spread through the list, so a page mixes unlocked and locked
        rows, with hardcore ones spread among them, and dated before every recorded unlock, so
        Recent unlocks still starts with the real ones.

        Args:
            data: Recorded ``API_GetGameInfoAndUserProgress`` response.

        Returns:
            The rewritten response.
        """
        target = self._targets.get(int(data.get("ID") or 0))
        if target is None:
            return data
        hardcore, unlocked = target
        ordered = sorted(data["Achievements"].values(), key=lambda a: (a["DisplayOrder"], a["ID"]))
        real = [a for a in ordered if a.get("DateEarned")]
        invented = _spread([a for a in ordered if not a.get("DateEarned")], unlocked - len(real))
        for index, achievement in enumerate(invented):
            achievement["DateEarned"] = _ra_time(_INVENTED_BEFORE - (len(invented) - index) * 3_600)
        real_hardcore = [a for a in real if a.get("DateEarnedHardcore")]
        for achievement in real_hardcore[hardcore:]:
            achievement["DateEarnedHardcore"] = None
        for achievement in _spread(invented, hardcore - len(real_hardcore)):
            achievement["DateEarnedHardcore"] = achievement["DateEarned"]
        earned = sum(1 for a in ordered if a.get("DateEarned"))
        earned_hardcore = sum(1 for a in ordered if a.get("DateEarnedHardcore"))
        data["NumAwardedToUser"], data["NumAwardedToUserHardcore"] = earned, earned_hardcore
        data["UserCompletion"] = f"{100 * earned / max(len(ordered), 1):.2f}%"
        data["UserCompletionHardcore"] = f"{100 * earned_hardcore / max(len(ordered), 1):.2f}%"
        return data

    def _awards(self) -> dict:
        """Build ``API_GetUserAwards`` for the showcase games.

        Returns:
            The response.
        """
        rows = []
        for game, (_hc, _casual, award, in_hardcore) in zip(self._games, _SHOWCASE, strict=False):
            if award is None:
                continue
            rows.append(
                {
                    "AwardedAt": game["MostRecentAwardedDate"],
                    "AwardType": award,
                    "AwardData": game["GameID"],
                    "AwardDataExtra": int(in_hardcore),
                    "Title": game["Title"],
                    "ConsoleID": game["ConsoleID"],
                    "ConsoleName": game["ConsoleName"],
                    "ImageIcon": game["ImageIcon"],
                    "DisplayOrder": len(rows),
                }
            )
        kinds = [(row["AwardType"], row["AwardDataExtra"]) for row in rows]
        return {
            "TotalAwardsCount": len(rows),
            "MasteryAwardsCount": kinds.count(("Mastery/Completion", 1)),
            "CompletionAwardsCount": kinds.count(("Mastery/Completion", 0)),
            "BeatenHardcoreAwardsCount": kinds.count(("Game Beaten", 1)),
            "BeatenSoftcoreAwardsCount": kinds.count(("Game Beaten", 0)),
            "VisibleUserAwards": rows,
        }


def _spread(items: list[dict], count: int) -> list[dict]:
    """Pick ``count`` items spread evenly through a list.

    Args:
        items: Items in order.
        count: How many to pick (all of them if it's more than the list holds).

    Returns:
        The picked items, in order.
    """
    if count >= len(items):
        return list(items)
    return [items[(2 * i + 1) * len(items) // (2 * count)] for i in range(max(count, 0))]


def _ra_time(seconds: int) -> str:
    """Format epoch seconds the way RA does (UTC).

    Args:
        seconds: Epoch seconds.

    Returns:
        E.g. ``"2026-08-21 17:02:50"``.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(seconds))


def _recent_unlocks(end: int) -> list[dict]:
    """Invent a month of unlocks ending at ``end`` (``API_GetAchievementsEarnedBetween`` rows).

    Args:
        end: Window end (epoch seconds).

    Returns:
        Rows, oldest first.
    """
    rows = []
    for index, (days_ago, points, hardcore) in enumerate(_SHOWCASE_UNLOCKS):
        when = time.gmtime(end - days_ago * 86_400 - 3_600)
        rows.append(
            {
                "Date": time.strftime("%Y-%m-%d %H:%M:%S", when),
                "HardcoreMode": int(hardcore),
                "AchievementID": 900_000 + index,
                "Points": points,
                "GameID": 519,
                "ConsoleName": "Game Boy Advance",
            }
        )
    return sorted(rows, key=lambda row: row["Date"])


class _BorrowedAwards:
    """Fixture data with another account's awards; images missing from the mirror come live.

    Args:
        base: The fixture transport.
        awards: Recorded ``API_GetUserAwards`` response.
    """

    def __init__(self, base: Transport, awards: Path) -> None:
        self._base = base
        self._awards = awards
        self._live: Transport | None = None

    def get(self, host: str, path: str, headers: dict[str, str]) -> Response:
        """Serve the borrowed awards, the fixtures, or a live image."""
        if host != MEDIA_HOST and "API_GetUserAwards" in path:
            return Response(status=200, body=self._awards.read_bytes())
        response = self._base.get(host, path, headers)
        if host == MEDIA_HOST and response.status == NOT_FOUND:
            self._live = self._live or HttpTransport()
            return self._live.get(host, path, headers)
        return response


def simulation(
    name: str | None,
    fixtures: Path,
    base: Callable[[], Transport] | None = None,
    awards: Path | None = None,
) -> Simulation:
    """Return the environment tweaks for a scenario.

    Args:
        name: Scenario name, or ``None``/empty for none.
        fixtures: Normal fixture directory (``empty`` uses its sibling ``ra-empty``).
        base: The normal fixture transport factory (``showcase`` and ``awards`` wrap it).
        awards: Directory recorded with ``--awards-only`` (the ``awards`` drill).

    Returns:
        The tweaks.

    Raises:
        ValueError: For an unknown scenario, or ``awards`` without recorded awards.
    """
    if not name:
        return Simulation()
    if name not in SCENARIOS:
        raise ValueError(f"unknown CHEEVOS_SIMULATE {name!r}; choose from {SCENARIOS}")
    empty = fixtures.parent / "ra-empty"
    source = base or (lambda: FixtureTransport(fixtures))
    drills = {
        "offline": Simulation(online=False, auto_sync=True),
        "clock": Simulation(clock_ok=False, auto_sync=True),
        "auth": Simulation(transport=_Rejecting, auto_sync=True),
        "empty": Simulation(transport=lambda: FixtureTransport(empty), seeds_card=True),
        "showcase": Simulation(transport=lambda: _Showcase(source()), seeds_card=True),
        "untested": Simulation(device="TRIMUI_BRICK"),
    }
    if name == "awards":
        recorded = (awards or Path()) / "user_awards.json"
        if not recorded.is_file():
            raise ValueError(
                f"no {recorded}; record one first: uv run python scripts/record_fixtures.py "
                "USERNAME --awards-only --out dev/fixtures/awards"
            )
        borrowed = Simulation(
            transport=lambda: _BorrowedAwards(source(), recorded), seeds_card=True
        )
        drills["awards"] = borrowed
    return drills.get(name, Simulation())


def prepare_card(name: str | None, paths: Paths, fixtures: Path) -> None:
    """Adjust the fake SD card for a scenario (``proxy`` adds files, ``setup`` drops the key).

    Args:
        name: Scenario name.
        paths: Fake card paths.
        fixtures: Fixture directory (for patch data).
    """
    if name == "setup":
        paths.api_key_file.unlink(missing_ok=True)
    if name != "proxy":
        return
    data = paths.proxy_data_dir
    data.mkdir(parents=True, exist_ok=True)
    (data / "online_state.json").write_text('{"online": false}', encoding="utf-8")
    (data / "cached_game_ids.txt").write_text("519\n3830\n", encoding="utf-8")
    _write_proxy_db(data / "proxy.sqlite3", fixtures)
    paths.spruce_config.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "menuOptions": {
            "RetroAchievements Settings": {
                "enableOfflineProxy": {"selected": "True"},
                "username": {"selected": ""},
            }
        }
    }
    paths.spruce_config.write_text(json.dumps(config), encoding="utf-8")


def _write_proxy_db(path: Path, fixtures: Path) -> None:
    """Create a proxy database with FFTA's patch data and three queued unlocks.

    Args:
        path: Database file (replaced).
        fixtures: Fixture directory with ``game_519.json``.
    """
    path.unlink(missing_ok=True)
    game = json.loads((fixtures / "game_519.json").read_text(encoding="utf-8"))
    patch = {
        "PatchData": {
            "ID": 519,
            "Title": game["Title"],
            "Achievements": [
                {"ID": int(a["ID"]), "Title": a["Title"], "Points": int(a["Points"])}
                for a in game["Achievements"].values()
            ],
        }
    }
    now_ms = int(time.time() * 1000)
    with sqlite3.connect(path) as db:
        db.executescript(_PROXY_DDL)
        db.execute(
            "INSERT INTO api_cache (cacheKey, responseBody, cachedAt, firstCachedAt) "
            "VALUES (?, ?, ?, ?)",
            ("patch:519:balah", json.dumps(patch), now_ms, now_ms),
        )
        for offset, achievement in enumerate(_PENDING):
            db.execute(
                "INSERT INTO pending_awards (achievementId, queryString, requestBody, userAgent,"
                " queuedAt) VALUES (?, '', '', '', ?)",
                (achievement, now_ms - (offset + 1) * 3_600_000),
            )
    path.chmod(0o644)
