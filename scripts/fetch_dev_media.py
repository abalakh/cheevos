"""Mirror the media host for every image the recorded fixtures reference (desktop dev only).

Fills ``dev/media-host/`` with the host's own paths (``UserPic/<user>.png``,
``Images/<id>.png``, ``Badge/<name>.png`` and ``Badge/<name>_lock.png``) so the desktop
runner's fixture mode serves real images offline. Media needs no API key. Existing files are
skipped.

Usage: ``uv run python scripts/fetch_dev_media.py [--games 519,3830]`` (default: all games)
"""

from __future__ import annotations

import argparse
import http.client
import json
import ssl
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "ra"
MIRROR = REPO / "dev" / "media-host"
MEDIA_HOST = "media.retroachievements.org"
USER_AGENT = "Cheevos/0.1.0.dev0 (dev media fetcher)"


class MediaFetcher:
    """Download media files over one keep-alive connection, skipping existing files."""

    def __init__(self) -> None:
        self._connection = http.client.HTTPSConnection(
            MEDIA_HOST, context=ssl.create_default_context(), timeout=30
        )
        self.downloaded = 0
        self.skipped = 0

    def fetch(self, path: str, destination: Path) -> None:
        """Save ``https://media.retroachievements.org<path>`` to ``destination``.

        Args:
            path: URL path starting with ``/``.
            destination: Output file.

        Raises:
            RuntimeError: If the server does not answer HTTP 200.
        """
        if destination.exists():
            self.skipped += 1
            return
        self._connection.request("GET", path, headers={"User-Agent": USER_AGENT})
        response = self._connection.getresponse()
        body = response.read()
        if response.status != 200:  # noqa: PLR2004 — HTTP OK
            raise RuntimeError(f"{path}: HTTP {response.status}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        self.downloaded += 1


def load(name: str) -> object:
    """Load one fixture file.

    Args:
        name: Fixture file stem.

    Returns:
        The decoded JSON.
    """
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def mirror(fetcher: MediaFetcher, path: str) -> None:
    """Fetch one media path into the mirror under the same relative path.

    Args:
        fetcher: Media fetcher.
        path: Media-host path, e.g. ``"/Badge/198102.png"``.
    """
    fetcher.fetch(path, MIRROR / path.lstrip("/"))


def fetch_game(fetcher: MediaFetcher, game_id: int) -> None:
    """Fetch a game's icon and both badge variants of each achievement.

    Args:
        fetcher: Media fetcher.
        game_id: RA game ID with a ``game_<id>.json`` fixture.
    """
    game = load(f"game_{game_id}")
    assert isinstance(game, dict)  # noqa: S101 — fixture shape, dev script
    mirror(fetcher, game["ImageIcon"])
    for achievement in game["Achievements"].values():
        mirror(fetcher, f"/Badge/{achievement['BadgeName']}.png")
        mirror(fetcher, f"/Badge/{achievement['BadgeName']}_lock.png")


def main(argv: list[str] | None = None) -> int:
    """Download the avatar, all game icons, and badges for the selected games.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--games", default="", help="comma-separated game IDs (default: all)")
    args = parser.parse_args(argv)
    fetcher = MediaFetcher()
    summary = load("user_summary")
    assert isinstance(summary, dict)  # noqa: S101 — fixture shape, dev script
    mirror(fetcher, summary["UserPic"])
    recorded = sorted(int(path.stem.split("_")[1]) for path in FIXTURES.glob("game_*.json"))
    wanted = [int(part) for part in args.games.split(",") if part] or recorded
    for game_id in wanted:
        fetch_game(fetcher, game_id)
    print(
        f"Media mirror {MIRROR.relative_to(REPO)}: {fetcher.downloaded} new, {fetcher.skipped} kept"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
