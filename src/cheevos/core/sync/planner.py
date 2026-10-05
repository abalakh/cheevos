"""Decide what a sync must fetch. Pure functions: no I/O, no clock, fully deterministic.

A sync always refreshes the cheap list-level data (profile, completion progress, recently
played). Per-game details (achievement sets, unlock dates) are the expensive part, so they are
re-fetched only when something about the game changed (.agents/sync-and-storage.md):

1. never fetched;
2. fingerprint changed (an unlock, a new award, a revised set);
3. details older than ``stale_after``: a small budget per sync, oldest first, so text or badge
   edits on RA eventually show up;
4. everything, on an explicit full re-sync.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from cheevos.core.models import GameProgress

DAY = 24 * 60 * 60
DEFAULT_STALE_AFTER = 30 * DAY
DEFAULT_STALE_BUDGET = 20


@dataclass(frozen=True, slots=True)
class PlanPolicy:
    """How eagerly unchanged details are refreshed.

    Attributes:
        stale_after: Age in seconds after which unchanged details are refreshed.
        stale_budget: Maximum number of stale refreshes per sync.
    """

    stale_after: int = DEFAULT_STALE_AFTER
    stale_budget: int = DEFAULT_STALE_BUDGET


# Stored detail state per game: (fingerprint at last detail fetch, when it was fetched).
DetailState = tuple[str | None, int | None]


@dataclass(frozen=True, slots=True)
class DetailPlan:
    """Games whose details a sync will fetch, grouped by reason.

    Attributes:
        never_fetched: No details cached yet (most recently active first).
        changed: Fingerprint differs from the cached details (most recently active first).
        stale: Unchanged but older than the staleness limit (oldest fetch first, budgeted).
    """

    never_fetched: tuple[int, ...] = ()
    changed: tuple[int, ...] = ()
    stale: tuple[int, ...] = ()

    @property
    def ordered(self) -> tuple[int, ...]:
        """All planned game IDs in fetch order."""
        return self.never_fetched + self.changed + self.stale

    def __len__(self) -> int:
        """Return the number of planned fetches."""
        return len(self.never_fetched) + len(self.changed) + len(self.stale)


def merge_library(
    progress: Iterable[GameProgress], recently_played: Iterable[GameProgress]
) -> list[GameProgress]:
    """Combine completion progress with recently played games.

    Completion progress omits games played without any unlock; recently played adds those and
    contributes ``last_played_at`` for the others.

    Args:
        progress: Games from ``GetUserCompletionProgress``.
        recently_played: Games from ``GetUserRecentlyPlayedGames``.

    Returns:
        One entry per game, most recently active first, then by title.
    """
    games = {game.game_id: game for game in progress}
    for played in recently_played:
        known = games.get(played.game_id)
        if known is None:
            games[played.game_id] = played
        elif played.last_played_at is not None:
            games[played.game_id] = _with_last_played(known, played.last_played_at)
    return sorted(games.values(), key=lambda game: (-activity(game), game.title.lower()))


def _with_last_played(game: GameProgress, last_played_at: int) -> GameProgress:
    """Return ``game`` with ``last_played_at`` set (models are frozen).

    Args:
        game: Game from completion progress.
        last_played_at: Time from recently played.

    Returns:
        The updated game.
    """
    return GameProgress(
        game_id=game.game_id,
        title=game.title,
        console_id=game.console_id,
        console_name=game.console_name,
        image_icon=game.image_icon,
        max_possible=game.max_possible,
        earned=game.earned,
        earned_hardcore=game.earned_hardcore,
        last_unlock_at=game.last_unlock_at,
        highest_award=game.highest_award,
        highest_award_at=game.highest_award_at,
        last_played_at=last_played_at,
    )


def activity(game: GameProgress) -> int:
    """Return the latest known activity time of a game (0 if none).

    Args:
        game: The game.

    Returns:
        ``max(last_unlock_at, last_played_at)`` in epoch seconds.
    """
    return max(game.last_unlock_at or 0, game.last_played_at or 0)


def plan_detail_fetches(
    games: Sequence[GameProgress],
    states: Mapping[int, DetailState],
    *,
    now: int,
    full: bool = False,
    refetch_before: int | None = None,
    policy: PlanPolicy = PlanPolicy(),  # noqa: B008 — immutable dataclass default
) -> DetailPlan:
    """Plan which games need their details fetched.

    Games without achievements (``max_possible == 0``) are never planned: there is nothing to
    show for them beyond the list-level data.

    Args:
        games: Library from :func:`merge_library` (activity order is preserved).
        states: Cached detail state per game ID.
        now: Current time (epoch seconds).
        full: Fetch every game (explicit full re-sync).
        refetch_before: Treat details fetched before this time as changed (an interrupted full
            re-sync carries on until every game has been fetched again).
        policy: Staleness rules.

    Returns:
        The plan.
    """
    with_achievements = [game for game in games if game.max_possible > 0]
    if full:
        return DetailPlan(changed=tuple(game.game_id for game in with_achievements))
    never: list[int] = []
    changed: list[int] = []
    stale: list[tuple[int, int]] = []
    for game in with_achievements:
        fingerprint, synced_at = states.get(game.game_id, (None, None))
        if synced_at is None:
            never.append(game.game_id)
        elif fingerprint != game.fingerprint or (
            refetch_before is not None and synced_at < refetch_before
        ):
            changed.append(game.game_id)
        elif now - synced_at >= policy.stale_after:
            stale.append((synced_at, game.game_id))
    oldest_first = [game_id for _, game_id in sorted(stale)][: max(policy.stale_budget, 0)]
    return DetailPlan(tuple(never), tuple(changed), tuple(oldest_first))


def badge_game_ids(
    games: Sequence[GameProgress],
    *,
    on_device: set[int],
    include_all: bool,
    recent_since: int | None,
) -> list[int]:
    """Select the games whose badges a sync should download (.agents/sync-and-storage.md).

    Args:
        games: The library.
        on_device: Game IDs with a ROM on this SD card.
        include_all: Scope "All games".
        recent_since: Games active at or after this time count as recent; ``None`` disables
            the recent rule (scope "None" passes an empty ``on_device`` and ``None``).

    Returns:
        Game IDs in library order.
    """
    selected = []
    for game in games:
        recent = recent_since is not None and activity(game) >= recent_since
        if include_all or game.game_id in on_device or recent:
            selected.append(game.game_id)
    return selected
