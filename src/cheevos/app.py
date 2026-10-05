"""Composition root: wire credentials, caches, sync, lazy media and screens, then run home.

Shared by the device entry point (``cheevos.__main__``) and the desktop runner, which differ
only in the :class:`AppEnvironment` they pass (real HTTPS vs. recorded fixtures).
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cheevos.core.errors import AuthError, CheevosError
from cheevos.core.models import Unlock
from cheevos.core.net import clock_plausible, is_online
from cheevos.core.proxy import ProxyReader
from cheevos.core.ra_client.transport import HttpTransport, Transport
from cheevos.core.screenshots import ScreenshotIndex, screenshot_directory
from cheevos.core.settings import load_settings, save_settings
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache
from cheevos.core.sync.engine import BackgroundSync, SyncDeps
from cheevos.core.sync.lazy_media import LazyMediaFetcher, MediaSession
from cheevos.core.sync.session import Credentials, make_client, open_sync_deps
from cheevos.platform.paths import Paths
from cheevos.ui.context import AppContext
from cheevos.ui.media import MediaResolver
from cheevos.ui.pyui import generated, primitives, status_bar, views
from cheevos.ui.screens.home import Home
from cheevos.ui.screens.setup import change_key, ensure_credentials, untested_device_note
from cheevos.ui.screens.status import SyncBar

logger = logging.getLogger(__name__)

_RES = Path(__file__).resolve().parent / "res"
# Devices Cheevos has been tried on (PyUI device names). Others get a one-time note asking for
# reports; add a device here once it has been confirmed to work.
TESTED_DEVICES = frozenset({"MIYOO_MINI", "MIYOO_MINI_V4", "MIYOO_MINI_PLUS", "MIYOO_MINI_FLIP"})
_LARGE_SCREEN_WIDTH = 1000
_SHUTDOWN_TIMEOUT = 3.0


@dataclass(frozen=True, slots=True)
class AppEnvironment:
    """How the app reaches the outside world.

    Attributes:
        paths: Device paths.
        transport_factory: Creates an HTTP transport (one per thread).
        online: Connectivity check.
        clock_ok: Clock plausibility check.
        auto_sync: Overrides the "sync when the app opens" setting when not ``None``.
        device: PyUI's name for the device (``None`` on the desktop).
    """

    paths: Paths
    transport_factory: Callable[[], Transport] = HttpTransport
    online: Callable[[], bool] = is_online
    clock_ok: Callable[[float], bool] = clock_plausible
    auto_sync: bool | None = None
    device: str | None = None


def _icons_dir(*, bar: bool = False) -> Path:
    """Pick the pixel-icon size for this screen.

    Args:
        bar: Bottom-bar icons (24 px up to 752 px wide, 48 px above) rather than list icons
            (48 px, 72 px above).

    Returns:
        The icon directory.
    """
    width, _ = primitives.screen_size()
    large = width >= _LARGE_SCREEN_WIDTH
    if bar:
        return _RES / "icons" / ("48" if large else "24")
    return _RES / "icons" / ("72" if large else "48")


def _validator(env: AppEnvironment) -> Callable[[str, str], bool | None]:
    """Build the API-key check used by setup and settings.

    Args:
        env: App environment.

    Returns:
        ``(username, key) -> True | False | None`` (``None``: RA unreachable).
    """

    def validate(username: str, key: str) -> bool | None:
        """Ask RA whether ``key`` is valid for ``username`` (anything but a rejection: unknown)."""
        client = make_client(env.paths, Credentials(username, key), env.transport_factory())
        try:
            return client.validate_key()
        except AuthError:
            return False
        except CheevosError as exc:  # unreachable, rate limited or an odd answer
            logger.warning("Could not verify the API key: %s", exc)
            return None

    return validate


def _unlock_fetcher(
    env: AppEnvironment, ctx_ref: list[AppContext]
) -> Callable[[int, int], list[Unlock] | None]:
    """Build the on-demand unlock fetch behind the profile's "See more".

    Args:
        env: App environment.
        ctx_ref: One-element list holding the context.

    Returns:
        ``(start, end) -> unlocks``, or ``None`` when offline, the clock is unset or RA fails.
    """

    def fetch(start: int, end: int) -> list[Unlock] | None:
        """Fetch the user's unlocks between ``start`` and ``end`` (blocking)."""
        if not env.online() or not env.clock_ok(time.time()):
            return None
        credentials = ctx_ref[0].credentials
        client = make_client(env.paths, credentials, env.transport_factory())
        try:
            return client.unlocks_between(start, end)
        except CheevosError:
            logger.warning("Could not fetch recent unlocks", exc_info=True)
            return None

    return fetch


def _media_session(env: AppEnvironment, ctx_ref: list[AppContext]) -> Callable[[], MediaSession]:
    """Build the lazy fetcher's session factory (runs on the fetcher's thread).

    Args:
        env: App environment.
        ctx_ref: One-element list holding the context (set once it exists).

    Returns:
        A factory returning ``(client, media cache, close)``.
    """

    def open_session() -> MediaSession:
        """Open a client and an image-cache connection for the fetcher thread."""
        credentials = ctx_ref[0].credentials
        client = make_client(env.paths, credentials, env.transport_factory())
        media = MediaCache.open(env.paths.media_db, env.paths.media_scratch)
        return client, media, media.close

    return open_session


def _sync_deps(env: AppEnvironment, ctx_ref: list[AppContext]) -> Callable[[], SyncDeps]:
    """Build the background sync's collaborator factory (runs on the sync thread).

    Reads the credentials when each sync starts, so a key changed in Settings applies to the
    next sync.

    Args:
        env: App environment.
        ctx_ref: One-element list holding the context.

    Returns:
        The factory.
    """
    return lambda: open_sync_deps(env.paths, ctx_ref[0].credentials, env.transport_factory())


def run(*, started_at: float, env: AppEnvironment) -> None:
    """Run the app until the user leaves the home screen.

    Args:
        started_at: ``time.monotonic()`` at process start (for the start-up log line).
        env: App environment.
    """
    paths = env.paths
    icons = _icons_dir()
    validate = _validator(env)
    # Nothing to sync before setup ends, but its screens need the bar for their hints.
    with status_bar.installed(lambda _detailed: None, lambda: None):
        credentials = ensure_credentials(paths, validate)
        if credentials is None:
            return
        settings = load_settings(paths.settings_file)
        device = env.device
        if device and device not in TESTED_DEVICES and settings.untested_note != device:
            untested_device_note(device, paths.log_file.relative_to(paths.sdcard))
            settings = dataclasses.replace(settings, untested_note=device)
            save_settings(paths.settings_file, settings)
    ctx_ref: list[AppContext] = []
    try:
        data = DataCache.open(paths.data_db, credentials.username)
        media_cache = MediaCache.open(paths.media_db, paths.media_scratch)
    except CheevosError:
        logger.exception("Could not open the caches")
        return
    fetcher = LazyMediaFetcher(_media_session(env, ctx_ref))
    sync = BackgroundSync(_sync_deps(env, ctx_ref), online=env.online, clock_ok=env.clock_ok)
    ctx = AppContext(
        paths=paths,
        credentials=credentials,
        settings=settings,
        data=data,
        media_cache=media_cache,
        media=MediaResolver(media_cache, icons, fetcher, views.image_demand),
        sync=sync,
        proxy=ProxyReader(paths),
        screenshots=ScreenshotIndex(screenshot_directory(paths)),
        icons=icons,
        validate_key=validate,
        fetch_unlocks=_unlock_fetcher(env, ctx_ref),
    )
    ctx_ref.append(ctx)
    if settings.auto_sync if env.auto_sync is None else env.auto_sync:
        ctx.start_sync()
    logger.info("UI ready after %.2fs", time.monotonic() - started_at)
    generated.use_scratch(paths.scaled_scratch)
    views.track_images(lambda: ctx.media.version, ctx.media.new_window)
    bar = SyncBar(ctx, _icons_dir(bar=True), lambda: change_key(ctx))
    try:
        with status_bar.installed(bar.status, bar.press_start):
            Home(ctx).run()
    finally:
        sync.cancel()
        sync.join(_SHUTDOWN_TIMEOUT)
        fetcher.close()
        data.close()
        media_cache.close()
        # Extracted and enlarged images live in RAM (tmpfs) on devices; give it back.
        shutil.rmtree(paths.media_scratch, ignore_errors=True)
        shutil.rmtree(paths.scaled_scratch, ignore_errors=True)
