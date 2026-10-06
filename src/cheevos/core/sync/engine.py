"""The sync engine: fetch from RA into the caches, incrementally and resumably.

Phases: preflight (clock, network) → profile → library (completion progress + recently
played) → details (only planned games, one commit per game) → awards → media (avatar, game
icons, badges for the configured scope). See .agents/sync-and-storage.md.

An interrupted sync needs no explicit resume state: games whose details were not fetched keep
their old fingerprint (or none), so the next plan picks up exactly the remaining ones.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from cheevos.core.errors import (
    AuthError,
    CheevosError,
    NetworkError,
    RateLimitedError,
    RequestCancelledError,
)
from cheevos.core.models import GameProgress
from cheevos.core.ra_client.client import RaClient
from cheevos.core.settings import BadgeScope
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache, avatar_key, badge_key, icon_key
from cheevos.core.sync.planner import DAY, badge_game_ids, merge_library, plan_detail_fetches
from cheevos.core.sync.progress import Failure, Phase, ProgressTracker, SyncStatus

logger = logging.getLogger(__name__)

MEDIA_BATCH = 25  # images per transaction: few commits on the SD's dirsync FAT32
LAST_SYNC_KEY = "last_sync_at"
# Set while a full re-sync is unfinished: details fetched before it are re-fetched.
FULL_SINCE_KEY = "full_resync_since"
# When RA allows requests again after asking for a long pause (wall clock, epoch seconds).
RATE_LIMITED_UNTIL_KEY = "rate_limited_until"
RATE_LIMIT_PAUSE = 60.0  # assumed pause when RA rate-limits without saying for how long


class SyncCancelledError(Exception):
    """Raised inside the engine when cancellation was requested (never escapes ``run``)."""


class _FailedError(Exception):
    """Raised inside the engine to stop with a :class:`Failure` (never escapes ``run``).

    Args:
        failure: The reason.
        retry_at: When RA allows requests again, for ``RATE_LIMITED``.
    """

    def __init__(self, failure: Failure, retry_at: float | None = None) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.retry_at = retry_at


@dataclass(frozen=True, slots=True)
class SyncOptions:
    """What one sync should do.

    Attributes:
        full: Re-fetch every game's details (explicit "Full re-sync").
        badge_scope: Which games' badges to download.
        recent_days: Activity window for the "recent" part of the badge scope.
    """

    full: bool = False
    badge_scope: BadgeScope = BadgeScope.ON_DEVICE_AND_RECENT
    recent_days: int = 30


@dataclass(slots=True)
class SyncDeps:
    """Collaborators for one sync, created on (and owned by) the sync thread.

    SQLite connections must stay on the thread that created them, so these are built inside
    the worker by :class:`BackgroundSync`'s factory.

    Attributes:
        client: RA client.
        data: RA data cache.
        media: Image cache.
        on_device: Returns RA game IDs with a ROM on this SD card.
        close: Releases everything above (connections, sockets).
    """

    client: RaClient
    data: DataCache
    media: MediaCache
    on_device: Callable[[], set[int]] = set
    close: Callable[[], None] = field(default=lambda: None)


class SyncEngine:
    """Runs one sync with the given collaborators.

    Args:
        deps: Client and caches.
        tracker: Progress sink read by the UI.
        cancel: Set to stop at the next request boundary.
        clock: Wall clock (epoch seconds).
        online: Connectivity check.
        clock_ok: Whether the device clock is plausible enough for HTTPS.
    """

    def __init__(
        self,
        deps: SyncDeps,
        tracker: ProgressTracker,
        cancel: threading.Event,
        *,
        clock: Callable[[], float] = time.time,
        online: Callable[[], bool],
        clock_ok: Callable[[float], bool],
    ) -> None:
        self._deps = deps
        self._tracker = tracker
        self._cancel = cancel
        self._clock = clock
        self._online = online
        self._clock_ok = clock_ok

    def run(self, options: SyncOptions) -> SyncStatus:
        """Run every phase; never raises for expected failures.

        Args:
            options: What to sync.

        Returns:
            The final status (``DONE``, ``FAILED`` or ``CANCELLED``).
        """
        self._tracker.reset()
        try:
            self._preflight()
            self._sync_profile()
            games = self._sync_library()
            self._sync_details(games, full=options.full)
            self._sync_awards()
            self._sync_media(games, options)
        except (SyncCancelledError, RequestCancelledError):
            logger.info("Sync cancelled")
            self._tracker.finish(Phase.CANCELLED, at=self._clock())
        except _FailedError as stop:
            logger.info("Sync stopped: %s", stop.failure.value)
            self._tracker.finish(
                Phase.FAILED, failure=stop.failure, at=self._clock(), retry_at=stop.retry_at
            )
        except AuthError:
            logger.warning("Sync failed: API key rejected")
            self._tracker.finish(Phase.FAILED, failure=Failure.AUTH, at=self._clock())
        except RateLimitedError as exc:
            now = self._clock()
            pause = exc.retry_after if exc.retry_after is not None else RATE_LIMIT_PAUSE
            self._deps.data.set_meta(RATE_LIMITED_UNTIL_KEY, str(int(now + pause)))
            logger.warning("Sync stopped: RA asked us to wait %.0fs", pause)
            self._tracker.finish(
                Phase.FAILED, failure=Failure.RATE_LIMITED, at=now, retry_at=now + pause
            )
        except NetworkError as exc:
            logger.warning("Sync failed: network error: %s", exc)
            self._tracker.finish(Phase.FAILED, failure=Failure.NETWORK, at=self._clock())
        except CheevosError:
            logger.exception("Sync failed")
            self._tracker.finish(Phase.FAILED, failure=Failure.ERROR, at=self._clock())
        else:
            now = self._clock()
            self._deps.data.set_meta(LAST_SYNC_KEY, str(int(now)))
            self._deps.data.set_meta(FULL_SINCE_KEY, None)
            self._deps.data.set_meta(RATE_LIMITED_UNTIL_KEY, None)
            self._tracker.finish(Phase.DONE, at=now)
            status = self._tracker.snapshot()
            logger.info(
                "Sync done: %d game details, %d images",
                status.details_fetched,
                status.media_fetched,
            )
        return self._tracker.snapshot()

    def _check_cancel(self) -> None:
        """Stop if cancellation was requested.

        Raises:
            SyncCancelledError: When the cancel event is set.
        """
        if self._cancel.is_set():
            raise SyncCancelledError

    def _preflight(self) -> None:
        """Check the clock, RA's last pause request and the network before any HTTPS request.

        Raises:
            _FailedError: Clock not synced, RA asked us to wait and the time isn't up, or no
                connection to RA.
        """
        self._tracker.phase(Phase.PREFLIGHT)
        now = self._clock()
        if not self._clock_ok(now):
            raise _FailedError(Failure.CLOCK)
        until = self._rate_limited_until()
        if until is not None and until > now:
            raise _FailedError(Failure.RATE_LIMITED, retry_at=until)
        if not self._online():
            raise _FailedError(Failure.OFFLINE)

    def _rate_limited_until(self) -> float | None:
        """Return when RA allows requests again, if a past sync was told to wait.

        Returns:
            The time, or ``None`` when there is none (or it can't be read).
        """
        raw = self._deps.data.get_meta(RATE_LIMITED_UNTIL_KEY)
        try:
            return float(raw) if raw is not None else None
        except ValueError:
            return None

    def _sync_profile(self) -> None:
        """Fetch and store the account summary."""
        self._check_cancel()
        self._tracker.phase(Phase.PROFILE)
        profile = self._deps.client.user_summary()
        self._deps.data.save_profile(profile, int(self._clock()))

    def _sync_library(self) -> list[GameProgress]:
        """Fetch completion progress and recently played games; store the merged library.

        Returns:
            The merged library, most recently active first.
        """
        self._check_cancel()
        self._tracker.phase(Phase.LIBRARY)
        progress = self._deps.client.completion_progress()
        self._check_cancel()
        recent = self._deps.client.recently_played()
        games = merge_library(progress, recent)
        self._deps.data.upsert_games(games)
        return games

    def _sync_details(self, games: list[GameProgress], *, full: bool) -> None:
        """Fetch details for the planned games, committing one game at a time.

        Args:
            games: Merged library.
            full: Re-fetch every game.
        """
        now = int(self._clock())
        if full:
            self._deps.data.set_meta(FULL_SINCE_KEY, str(now))
        pending_full = self._deps.data.get_meta(FULL_SINCE_KEY)
        plan = plan_detail_fetches(
            games,
            self._deps.data.detail_states(),
            now=now,
            full=full,
            refetch_before=int(pending_full) if pending_full else None,
        )
        by_id = {game.game_id: game for game in games}
        self._tracker.phase(Phase.DETAILS, total=len(plan))
        logger.info(
            "Detail plan: %d new, %d changed, %d stale",
            len(plan.never_fetched),
            len(plan.changed),
            len(plan.stale),
        )
        for game_id in plan.ordered:
            self._check_cancel()
            game = by_id[game_id]
            self._tracker.working_on(game.title)
            detail = self._deps.client.game_detail(game_id)
            self._deps.data.save_game_detail(
                detail, fingerprint=game.fingerprint, synced_at=int(self._clock())
            )
            self._tracker.advance(detail=True)

    def _sync_awards(self) -> None:
        """Fetch and store mastery/beaten awards."""
        self._check_cancel()
        self._tracker.phase(Phase.AWARDS)
        counts, awards = self._deps.client.awards()
        self._deps.data.save_awards(counts, awards)

    def _sync_media(self, games: list[GameProgress], options: SyncOptions) -> None:
        """Download missing images: avatar, game icons, and badges for the badge scope.

        Args:
            games: Merged library.
            options: Sync options (badge scope).
        """
        self._check_cancel()
        wanted = dict(self._media_wanted(games, options))
        missing = self._deps.media.missing(wanted)
        self._tracker.phase(Phase.MEDIA, total=len(missing))
        batch: list[tuple[str, bytes]] = []
        for key in missing:
            self._check_cancel()
            try:
                batch.append((key, self._deps.client.media(wanted[key])))
            except NetworkError:
                self._deps.media.put_many(batch)
                raise
            except CheevosError as exc:  # e.g. a badge RA no longer serves: skip it
                logger.warning("Skipping image %s: %s", key, exc)
            self._tracker.advance(media=True)
            if len(batch) >= MEDIA_BATCH:
                self._deps.media.put_many(batch)
                batch = []
        self._deps.media.put_many(batch)

    def _media_wanted(
        self, games: list[GameProgress], options: SyncOptions
    ) -> Iterator[tuple[str, str]]:
        """List the images this sync should have, as ``(cache key, media path)``.

        Args:
            games: Merged library.
            options: Sync options (badge scope).

        Yields:
            Cache key and media-host path pairs.
        """
        profile = self._deps.data.load_profile()
        if profile is not None and profile.user_pic:
            yield avatar_key(profile.username), profile.user_pic
        for game in games:
            if game.image_icon:
                yield icon_key(game.game_id), game.image_icon
        for game_id in self._badge_games(games, options):
            detail = self._deps.data.game_detail(game_id)
            for achievement in detail.achievements if detail else ():
                locked = not achievement.unlocked
                suffix = "_lock" if locked else ""
                path = f"/Badge/{achievement.badge_name}{suffix}.png"
                yield badge_key(achievement.badge_name, locked=locked), path

    def _badge_games(self, games: list[GameProgress], options: SyncOptions) -> list[int]:
        """Select the games whose badges belong in the cache for the configured scope.

        Args:
            games: Merged library.
            options: Sync options.

        Returns:
            Game IDs.
        """
        if options.badge_scope is BadgeScope.NONE:
            return []
        recent_since = int(self._clock()) - options.recent_days * DAY
        return badge_game_ids(
            games,
            on_device=self._deps.on_device(),
            include_all=options.badge_scope is BadgeScope.ALL,
            recent_since=recent_since,
        )


class BackgroundSync:
    """Runs syncs on a worker thread; the UI polls :meth:`status` on its input ticks.

    Args:
        open_deps: Creates the sync collaborators; called on the worker thread with the
            sync's cancel event (its client's waits stop when it is set).
        online: Connectivity check passed to the engine.
        clock_ok: Clock plausibility check passed to the engine.
    """

    def __init__(
        self,
        open_deps: Callable[[threading.Event], SyncDeps],
        *,
        online: Callable[[], bool],
        clock_ok: Callable[[float], bool],
    ) -> None:
        self._open_deps = open_deps
        self._online = online
        self._clock_ok = clock_ok
        self._tracker = ProgressTracker()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def status(self) -> SyncStatus:
        """Return the latest status snapshot."""
        return self._tracker.snapshot()

    def start(self, options: SyncOptions) -> bool:
        """Start a sync unless one is running.

        Args:
            options: What to sync.

        Returns:
            ``True`` if a new sync started.
        """
        if self._thread is not None and self._thread.is_alive():
            return False
        self._cancel.clear()
        self._tracker.reset()
        self._tracker.phase(Phase.PREFLIGHT)
        self._thread = threading.Thread(
            target=self._work, args=(options,), name="cheevos-sync", daemon=True
        )
        self._thread.start()
        return True

    def cancel(self) -> None:
        """Ask a running sync to stop: at once while it waits, else after the current request."""
        self._cancel.set()

    @property
    def cancelling(self) -> bool:
        """Whether a cancel was requested and the sync has not stopped yet."""
        return self._cancel.is_set() and self.status().running

    def join(self, timeout: float | None = None) -> None:
        """Wait for the worker to finish.

        Args:
            timeout: Maximum seconds to wait.
        """
        if self._thread is not None:
            self._thread.join(timeout)

    def _work(self, options: SyncOptions) -> None:
        """Worker body: open collaborators, run the engine, always release them.

        Args:
            options: What to sync.
        """
        try:
            deps = self._open_deps(self._cancel)
        except CheevosError:
            logger.exception("Could not start sync")
            self._tracker.finish(Phase.FAILED, failure=Failure.ERROR, at=time.time())
            return
        try:
            engine = SyncEngine(
                deps, self._tracker, self._cancel, online=self._online, clock_ok=self._clock_ok
            )
            engine.run(options)
        finally:
            deps.close()
