"""Everything screens need, bundled once by the app and passed to every screen."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cheevos.core.local_games import on_device_game_ids
from cheevos.core.models import PendingAward, Unlock
from cheevos.core.proxy import ProxyReader
from cheevos.core.screenshots import ScreenshotIndex
from cheevos.core.settings import Settings, save_settings
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache
from cheevos.core.sync.engine import BackgroundSync, SyncOptions
from cheevos.core.sync.session import Credentials
from cheevos.platform.paths import Paths
from cheevos.ui.media import MediaResolver

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    """Shared state for the UI thread.

    Attributes:
        paths: Device paths.
        credentials: Signed-in account.
        settings: Current settings (replaced by :meth:`update_settings`).
        data: RA data cache (UI-thread connection).
        media_cache: Image cache (UI-thread connection).
        media: Image resolver with lazy fetching.
        sync: Background sync runner.
        proxy: RAOfflineProxy reader.
        screenshots: Unlock screenshot index.
        icons: Directory of pixel icons sized for this screen.
        validate_key: Checks a Web API key with RA (``None`` result: unreachable).
        fetch_unlocks: Fetches the user's unlocks in a time window, blocking (``None``:
            offline or RA unreachable).
        clock: Wall clock.
    """

    paths: Paths
    credentials: Credentials
    settings: Settings
    data: DataCache
    media_cache: MediaCache
    media: MediaResolver
    sync: BackgroundSync
    proxy: ProxyReader
    screenshots: ScreenshotIndex
    icons: Path
    validate_key: Callable[[str, str], bool | None]
    fetch_unlocks: Callable[[int, int], list[Unlock] | None]
    clock: Callable[[], float] = time.time
    _on_device: set[int] | None = field(default=None, repr=False)

    def icon(self, name: str) -> Path:
        """Return a bundled pixel icon.

        Args:
            name: Icon name, e.g. ``"trophy"``.

        Returns:
            The icon path.
        """
        return self.icons / f"{name}.png"

    def start_sync(self, *, full: bool = False) -> bool:
        """Start a background sync with the current settings.

        Args:
            full: Re-fetch every game's details.

        Returns:
            ``True`` if a new sync started (``False`` if one is already running).
        """
        options = SyncOptions(
            full=full,
            badge_scope=self.settings.badge_scope,
            recent_days=self.settings.recent_days,
        )
        return self.sync.start(options)

    def update_settings(self, settings: Settings) -> None:
        """Replace and persist the settings.

        Args:
            settings: New settings.
        """
        self.settings = settings
        save_settings(self.paths.settings_file, settings)

    def on_device_ids(self) -> set[int]:
        """Return RA game IDs with a ROM on this SD card (computed once per app run)."""
        if self._on_device is None:
            self._on_device = on_device_game_ids(self.paths, self.proxy)
        return self._on_device

    def proxy_active(self) -> bool:
        """Whether RAOfflineProxy is installed and turned on."""
        return self.proxy.installed() and self.proxy.enabled()

    def pending_by_game(self) -> dict[int, int]:
        """Count queued RAOfflineProxy unlocks per game that RA doesn't know about yet.

        Returns:
            Game ID to number of unlocks waiting to sync (games the proxy can't name are left
            out).
        """
        pending = self.pending_awards()
        if not pending:
            return {}
        synced = self.data.unlocked_among(pending)
        counts = Counter(
            award.game_id
            for award in pending.values()
            if award.game_id is not None and award.achievement_id not in synced
        )
        return dict(counts)

    def pending_awards(self) -> dict[int, PendingAward]:
        """Return unlocks waiting in RAOfflineProxy's queue, by achievement ID."""
        if not self.proxy_active():
            return {}
        return {
            award.achievement_id: award
            for award in self.proxy.pending_awards(self.credentials.username)
        }
