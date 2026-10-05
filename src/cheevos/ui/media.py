"""Image paths for screens: cached RA images when available, pixel-icon fallbacks otherwise.

Screens ask on every render (PyUI's ``icon_searcher`` runs per frame), so a miss is memoized
until the background fetcher stores something new; until then a missing image costs a set
lookup, not a database query.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from cheevos.core.models import Achievement, UserProfile
from cheevos.core.storage.media_cache import MediaCache, avatar_key, badge_key, icon_key


class ImageFetcher(Protocol):
    """Background downloader interface (implemented by ``LazyMediaFetcher``)."""

    @property
    def version(self) -> int:
        """Changes whenever a newly downloaded image becomes available."""
        ...

    def request(self, key: str, media_path: str) -> None:
        """Ask for ``media_path`` to be downloaded into the cache under ``key``."""
        ...


class MediaResolver:
    """Resolve image cache keys to files PyUI can load.

    Args:
        media: Image cache (opened on the UI thread).
        icons_dir: Directory of bundled pixel icons used as fallbacks.
        fetcher: Background downloader for missing images (a ``LazyMediaFetcher``), or ``None``
            (offline / no key).
    """

    def __init__(
        self, media: MediaCache, icons_dir: Path, fetcher: ImageFetcher | None = None
    ) -> None:
        self._media = media
        self._icons = icons_dir
        self._fetcher = fetcher
        self._missing: set[str] = set()
        self._seen_version = self.version

    @property
    def version(self) -> int:
        """The fetcher's version (0 without a fetcher); changes when new images arrive."""
        return self._fetcher.version if self._fetcher is not None else 0

    def resolve(self, key: str, media_path: str | None, fallback: str) -> Path:
        """Return the cached image for ``key``, or a fallback icon while it is unavailable.

        On a miss the image is requested from the background fetcher (once per miss memo).

        Args:
            key: Image cache key.
            media_path: Path on the media host, or ``None`` if unknown (nothing is fetched).
            fallback: Name of a bundled pixel icon, e.g. ``"lock"``.

        Returns:
            A file path PyUI can load.
        """
        version = self.version
        if version != self._seen_version:
            self._missing.clear()
            self._seen_version = version
        if key not in self._missing:
            path = self._media.path_for(key)
            if path is not None:
                return path
            self._missing.add(key)
            if self._fetcher is not None and media_path:
                self._fetcher.request(key, media_path)
        return self._icons / f"{fallback}.png"

    def badge(self, achievement: Achievement, *, unlocked: bool | None = None) -> Path:
        """Return the badge matching the unlock state (colour, or RA's ``_lock`` variant).

        Args:
            achievement: The achievement.
            unlocked: Override the state, e.g. ``True`` for an unlock still waiting in
                RAOfflineProxy's queue (unlocked on the device, not yet on RA).

        Returns:
            The badge, or a trophy/lock icon while it is unavailable.
        """
        locked = not (achievement.unlocked if unlocked is None else unlocked)
        name = achievement.badge_name
        suffix = "_lock" if locked else ""
        return self.resolve(
            badge_key(name, locked=locked),
            f"/Badge/{name}{suffix}.png",
            "lock" if locked else "trophy",
        )

    def game_icon(self, game_id: int, image_icon: str) -> Path:
        """Return a game's icon.

        Args:
            game_id: RA game ID.
            image_icon: Icon path on the media host (may be empty: nothing is fetched).

        Returns:
            The icon, or a gamepad icon while it is unavailable.
        """
        return self.resolve(icon_key(game_id), image_icon or None, "gamepad")

    def avatar(self, profile: UserProfile | None) -> Path:
        """Return the user's avatar.

        Args:
            profile: Cached profile, or ``None`` before the first sync.

        Returns:
            The avatar, or a user icon while it is unavailable.
        """
        if profile is None:
            return self._icons / "user.png"
        return self.resolve(avatar_key(profile.username), profile.user_pic or None, "user")
