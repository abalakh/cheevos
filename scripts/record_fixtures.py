"""Record real RetroAchievements Web API responses as test/dev fixtures.

Usage::

    uv run python scripts/record_fixtures.py USERNAME [--out tests/fixtures/ra]
    uv run python scripts/record_fixtures.py USERNAME --awards-only --out dev/fixtures/awards

The API key is read from ``$CHEEVOS_API_KEY`` or ``dev/sdcard/Saves/cheevos/apikey.txt``. It is
sent only in the request and never written: saved files contain response bodies only, and the
manifest lists requests without the ``y`` parameter.

Records the profile, summary, completion progress, awards and recently played games, plus game
details for every game found. Requests are serial and spaced out to be polite to RA.
``--awards-only`` records just the awards (one request), for the ``awards`` desktop drill: a
big account's awards wall without syncing its whole library.
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

REPO = Path(__file__).resolve().parents[1]
KEY_FILE = REPO / "dev" / "sdcard" / "Saves" / "cheevos" / "apikey.txt"
HOST = "retroachievements.org"
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
        self._connection = http.client.HTTPSConnection(
            HOST, context=ssl.create_default_context(), timeout=30
        )
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
    recorder.fetch("API_GetUserSummary", "user_summary", g=5, a=10)
    progress = recorder.fetch("API_GetUserCompletionProgress", "completion_progress", c=500, o=0)
    recorder.fetch("API_GetUserAwards", "user_awards")
    recent = recorder.fetch("API_GetUserRecentlyPlayedGames", "recently_played", c=50)
    game_ids = {int(game["GameID"]) for game in progress["Results"]}
    game_ids |= {int(game["GameID"]) for game in recent}
    for game_id in sorted(game_ids):
        recorder.fetch("API_GetGameInfoAndUserProgress", f"game_{game_id}", g=game_id, a=1)


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
        recorder.fetch("API_GetUserAwards", "user_awards")
    else:
        record(recorder)
    manifest = {"username": args.username, "recorded_at": int(time.time()), "requests": []}
    manifest["requests"] = recorder.manifest
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Done: {len(recorder.manifest)} responses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
