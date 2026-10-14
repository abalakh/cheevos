"""Record real RetroAchievements Web API responses as test/dev fixtures.

Usage::

    uv run python scripts/record_fixtures.py USERNAME [--out tests/fixtures/ra]
    uv run python scripts/record_fixtures.py USERNAME --awards-only --out dev/fixtures/awards

The API key is read from ``$CHEEVOS_API_KEY`` or ``dev/sdcard/Saves/cheevos/apikey.txt``. It is
sent only in the request and never written: saved files contain response bodies only, and the
manifest lists requests without the ``y`` parameter.

Records the profile, summary, completion progress, awards (with their events' tiers, from the
v2 API), recently played games and recent unlocks, plus game details for every game found.
Requests are serial and spaced out to be polite to RA.
``--awards-only`` records just the awards and their events (tiers and points), for the
``awards`` desktop drill: a big account's Awards screen without syncing its whole library.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from cheevos.core.awards import gallery, is_event
from cheevos.core.models import GameProgress, UserProfile
from cheevos.core.ra_client import parse
from cheevos.core.ra_client.client import UNLOCK_PAGE
from cheevos.core.ra_client.parse_awards import parse_awards, parse_event_points, parse_events
from cheevos.core.ra_client.recent import INITIAL_WINDOW, UnlockPage, fetch_recent_unlocks
from cheevos.core.ra_client.v2 import EVENT_ACHIEVEMENT_PAGE, EVENT_PAGE
from cheevos.core.sync.planner import merge_library

REPO = Path(__file__).resolve().parents[1]
KEY_FILE = REPO / "dev" / "sdcard" / "Saves" / "cheevos" / "apikey.txt"
HOST = "retroachievements.org"
V2_HOST = "api.retroachievements.org"
USER_AGENT = "Cheevos/0.1.0.dev0 (fixture recorder)"
SPACING_SECONDS = 0.4


class Recorder:
    """Fetch Web API endpoints over one connection and save their JSON bodies.

    Args:
        key: Web API key (never written to disk).
        username: Account whose data is recorded.
        out_dir: Directory for fixture files.
    """

    def __init__(self, key: str, username: str, out_dir: Path) -> None:
        self._key = key
        self._username = username
        self._out_dir = out_dir
        context = ssl.create_default_context()
        self._connection = http.client.HTTPSConnection(HOST, context=context, timeout=30)
        self._v2 = http.client.HTTPSConnection(V2_HOST, context=context, timeout=30)
        self.manifest: list[dict[str, object]] = []

    def fetch(self, method: str, name: str, **params: object) -> Any:  # noqa: ANN401 — raw JSON
        """Call one endpoint, save its body as ``<name>.json`` and return the parsed JSON.

        Args:
            method: Endpoint name without ``.php``, e.g. ``"API_GetUserSummary"``.
            name: Fixture file stem.
            **params: Query parameters other than ``y`` and ``u``.

        Returns:
            The decoded JSON body.

        Raises:
            RuntimeError: If the response is not HTTP 200.
        """
        query = urlencode({"y": self._key, "u": self._username, **params})
        self._connection.request(
            "GET", f"/API/{method}.php?{query}", headers={"User-Agent": USER_AGENT}
        )
        response = self._connection.getresponse()
        body = response.read()
        if response.status != 200:  # noqa: PLR2004 — HTTP OK
            raise RuntimeError(f"{method} returned HTTP {response.status}")
        data = json.loads(body)
        path = self._out_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.manifest.append({"file": path.name, "method": method, "params": params})
        print(f"  {path.name:45} {len(body):7} B")
        time.sleep(SPACING_SECONDS)
        return data

    def fetch_v2(self, path: str, method: str, name: str, params: dict[str, object]) -> Any:  # noqa: ANN401 — raw JSON
        """Call one v2 resource (the key goes in a header), save its body and return it.

        Args:
            path: Resource path, e.g. ``"/v2/events"``.
            method: Manifest name, e.g. ``"v2/events"``.
            name: Fixture file stem.
            params: Query parameters, recorded as sent.

        Returns:
            The decoded JSON body.

        Raises:
            RuntimeError: If the response is not HTTP 200.
        """
        headers = {"User-Agent": USER_AGENT, "X-API-Key": self._key}
        self._v2.request("GET", f"{path}?{urlencode(params)}", headers=headers)
        response = self._v2.getresponse()
        body = response.read()
        if response.status != 200:  # noqa: PLR2004 — HTTP OK
            raise RuntimeError(f"{method} returned HTTP {response.status}")
        data = json.loads(body)
        file = self._out_dir / f"{name}.json"
        file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.manifest.append({"file": file.name, "method": method, "params": params})
        print(f"  {file.name:45} {len(body):7} B")
        time.sleep(SPACING_SECONDS)
        return data

    def fetch_events(self, awards: Any) -> None:  # noqa: ANN401 — raw JSON
        """Record what the sync asks RA's v2 API about the awards' events: tiers and points.

        One page of events is recorded (fixture mode serves it for every request when the
        account has more than :data:`EVENT_PAGE` events).

        Args:
            awards: The decoded ``API_GetUserAwards`` response.
        """
        parsed = parse_awards(awards)[1]
        ids = sorted({award.data for award in gallery(parsed) if is_event(award)})[:EVENT_PAGE]
        if not ids:
            return
        chunk = ",".join(map(str, ids))
        params: dict[str, object] = {"filter[id]": chunk, "include": "awards"}
        params |= {"page[size]": EVENT_PAGE, "page[number]": 1}
        events = parse_events(self.fetch_v2("/v2/events", "v2/events", "events", params))[0]
        earned = {(award.data, award.extra) for award in parsed if is_event(award)}
        tiered = sorted(
            event.event_id
            for event in events
            if any((event.event_id, tier.tier) in earned for tier in event.tiers)
        )
        number = last = 1
        while tiered and number <= last:
            params = {
                "filter[eventId]": ",".join(map(str, tiered)),
                "fields[event-achievements]": "achievementPoints,event",
                "page[size]": EVENT_ACHIEVEMENT_PAGE,
                "page[number]": number,
            }
            name = f"event_achievements_{number}"
            data = self.fetch_v2("/v2/event-achievements", "v2/event-achievements", name, params)
            last = parse_event_points(data)[1]
            number += 1


def read_key() -> str:
    """Return the API key from the environment or the dev SD-card key file.

    Returns:
        The key, stripped.

    Raises:
        SystemExit: If no key is configured.
    """
    key = os.environ.get("CHEEVOS_API_KEY") or (
        KEY_FILE.read_text(encoding="utf-8").strip() if KEY_FILE.exists() else ""
    )
    if not key:
        raise SystemExit(f"Set CHEEVOS_API_KEY or create {KEY_FILE}")
    return key


def record(recorder: Recorder) -> None:
    """Record the account-level endpoints, then details for every game they mention.

    Args:
        recorder: Configured recorder.
    """
    recorder.fetch("API_GetUserProfile", "user_profile")
    summary = recorder.fetch("API_GetUserSummary", "user_summary", g=5, a=10)
    progress = recorder.fetch("API_GetUserCompletionProgress", "completion_progress", c=500, o=0)
    recorder.fetch_events(recorder.fetch("API_GetUserAwards", "user_awards"))
    recent = recorder.fetch("API_GetUserRecentlyPlayedGames", "recently_played", c=50)
    games = merge_library(
        parse.parse_completion_progress(progress)[0], parse.parse_recently_played(recent)
    )
    record_recent(recorder, parse.parse_user_summary(summary), games)
    game_ids = {int(game["GameID"]) for game in progress["Results"]}
    game_ids |= {int(game["GameID"]) for game in recent}
    for game_id in sorted(game_ids):
        recorder.fetch("API_GetGameInfoAndUserProgress", f"game_{game_id}", g=game_id, a=1)


def record_recent(recorder: Recorder, profile: UserProfile, games: list[GameProgress]) -> None:
    """Record the same bounded history requests as sync, including capped-window retries."""
    start = max(profile.member_since or 0, 0)
    end = max((game.last_unlock_at or 0 for game in games), default=0)
    if not end:
        return
    pages = 0

    def page(first: int, last: int) -> UnlockPage:
        """Save one raw response so FixtureTransport can replay the exact query."""
        nonlocal pages
        data = recorder.fetch(
            "API_GetAchievementsEarnedBetween", f"unlocks_{pages}", f=first, t=last
        )
        pages += 1
        return parse.parse_recent_unlocks(data), len(data) >= UNLOCK_PAGE

    width = (
        end - start + 1 if sum(game.earned for game in games) * 2 < UNLOCK_PAGE else INITIAL_WINDOW
    )
    fetch_recent_unlocks(page, start=start, end=end, initial_window=width)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and record the fixture set.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("--out", type=Path, default=REPO / "tests" / "fixtures" / "ra")
    parser.add_argument("--awards-only", action="store_true", help="record just the awards")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    recorder = Recorder(read_key(), args.username, args.out)
    print(f"Recording {args.username} into {args.out}")
    if args.awards_only:
        recorder.fetch_events(recorder.fetch("API_GetUserAwards", "user_awards"))
    else:
        record(recorder)
    manifest = {"username": args.username, "recorded_at": int(time.time()), "requests": []}
    manifest["requests"] = recorder.manifest
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Done: {len(recorder.manifest)} responses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
