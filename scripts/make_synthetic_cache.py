"""Fill a data cache with a synthetic large account, for performance testing (dev only).

Usage::

    uv run python scripts/make_synthetic_cache.py OUT_DB USERNAME [--games 1000] [--per-game 40]

The cache is disposable: delete the file afterwards and the app rebuilds it on the next sync.
Games get IDs from 900000 up so they never collide with real ones.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from cheevos.core.models import Achievement, AchievementType, AwardKind, GameDetail, GameProgress
from cheevos.core.storage.data_cache import DataCache

FIRST_ID = 900_000
CONSOLES = ["Game Boy Advance", "SNES/Super Famicom", "PlayStation", "Genesis/Mega Drive", "NES"]
WORDS = [
    "Quest",
    "Legend",
    "Saga",
    "Tactics",
    "Dragon",
    "Star",
    "Shadow",
    "Kingdom",
    "Chronicles",
    "Arena",
    "Racing",
]


def _title(rng: random.Random, game_id: int) -> str:
    """Make a plausible, sometimes long, game title.

    Args:
        rng: Random source.
        game_id: Game ID (keeps titles unique).

    Returns:
        The title.
    """
    words = rng.sample(WORDS, rng.randint(2, 6))
    return f"{' '.join(words)} {game_id}"


def _achievements(rng: random.Random, game_id: int, count: int, now: int) -> list[Achievement]:
    """Make a game's achievements, about a quarter unlocked.

    Args:
        rng: Random source.
        game_id: Game ID.
        count: Achievements to create.
        now: Current time.

    Returns:
        The achievements.
    """
    types = [None, None, AchievementType.PROGRESSION, AchievementType.MISSABLE]
    result = []
    for index in range(count):
        unlocked = rng.random() < 0.25  # noqa: PLR2004 — share of unlocked achievements
        when = now - rng.randint(0, 3 * 365 * 86400) if unlocked else None
        result.append(
            Achievement(
                achievement_id=game_id * 1000 + index,
                game_id=game_id,
                title=f"Achievement {index} of {game_id}",
                description="Do something memorable in this synthetic game.",
                points=rng.choice([1, 2, 3, 5, 10, 25]),
                retro_points=rng.randint(1, 60),
                badge_name=str(game_id * 1000 + index),
                display_order=index,
                type=rng.choice(types),
                num_awarded=rng.randint(10, 5000),
                num_awarded_hardcore=rng.randint(0, 3000),
                earned_at=when,
                earned_hardcore_at=when if unlocked and rng.random() < 0.5 else None,  # noqa: PLR2004
            )
        )
    return result


def build(out: Path, username: str, games: int, per_game: int) -> None:
    """Write the synthetic account into ``out``.

    Args:
        out: Database path (created or reset).
        username: Account the cache belongs to.
        games: Number of games.
        per_game: Achievements per game.
    """
    rng = random.Random(42)  # noqa: S311 — deterministic test data, not security
    now = int(time.time())
    cache = DataCache.open(out, username)
    try:
        for game_id in range(FIRST_ID, FIRST_ID + games):
            achievements = _achievements(rng, game_id, per_game, now)
            earned = [a for a in achievements if a.unlocked]
            progress = GameProgress(
                game_id=game_id,
                title=_title(rng, game_id),
                console_id=1,
                console_name=rng.choice(CONSOLES),
                image_icon="",
                max_possible=per_game,
                earned=len(earned),
                earned_hardcore=sum(1 for a in earned if a.hardcore),
                last_unlock_at=max((a.unlocked_at or 0 for a in earned), default=None),
                highest_award=AwardKind.BEATEN_SOFTCORE if rng.random() < 0.05 else None,  # noqa: PLR2004
                highest_award_at=None,
            )
            cache.upsert_games([progress])
            detail = GameDetail(
                game_id,
                progress.title,
                progress.console_name,
                "",
                5000,
                3000,
                2000,
                tuple(achievements),
            )
            cache.save_game_detail(detail, fingerprint=progress.fingerprint, synced_at=now)
    finally:
        cache.close()


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and build the cache.

    Args:
        argv: Arguments without the program name.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("username")
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--per-game", type=int, default=40)
    args = parser.parse_args(argv)
    started = time.monotonic()
    build(args.out, args.username, args.games, args.per_game)
    elapsed = time.monotonic() - started
    print(f"Wrote {args.games} games x {args.per_game} achievements in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
