"""Fetch missing images in the background while the user browses (.agents/sync-and-storage.md).

Badges outside the sync's badge scope (or with scope "None") and anything a sync has not
reached yet are requested here when a screen first needs them. A single daemon worker
downloads them one at a time over its own keep-alive connection and stores them in the image
cache; the UI notices through :attr:`LazyMediaFetcher.version` and re-renders.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
from collections.abc import Callable
from typing import Protocol

from cheevos.core.errors import CheevosError, NetworkError

logger = logging.getLogger(__name__)

_POLL_SECONDS = 0.5  # idle wake-up interval; requests and close() wake the worker at once


class MediaSource(Protocol):
    """Downloads files from RA's media host (implemented by ``RaClient``)."""

    def media(self, path: str) -> bytes:
        """Return the file at ``path`` on the media host."""
        ...


class MediaStore(Protocol):
    """Stores image blobs (implemented by ``MediaCache``)."""

    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key``."""
        ...


# (client, media cache, close). Opened on the worker thread: SQLite connections are per-thread.
MediaSession = tuple[MediaSource, MediaStore, Callable[[], None]]


class LazyMediaFetcher:
    """Background downloader for images the UI asked for but the cache lacks.

    Args:
        open_session: Creates the client and image cache; called once, on the worker thread.
        clock: Monotonic clock used for the offline backoff.
        offline_backoff: Seconds to ignore requests after a network failure.
        max_queue: Maximum queued requests; extra requests are dropped (and can be re-requested).
    """

    def __init__(
        self,
        open_session: Callable[[], MediaSession],
        *,
        clock: Callable[[], float] = time.monotonic,
        offline_backoff: float = 60.0,
        max_queue: int = 500,
    ) -> None:
        self._open_session = open_session
        self._clock = clock
        self._offline_backoff = offline_backoff
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=max_queue)
        self._lock = threading.Lock()
        self._known: set[str] = set()  # queued, in flight, or stored
        self._failed: set[str] = set()  # permanently unavailable this session
        self._in_flight: str | None = None
        self._version = 0
        self._backoff_until: float | None = None
        self._disabled = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def version(self) -> int:
        """Number of images stored so far; changes whenever a new image becomes available."""
        with self._lock:
            return self._version

    def pending(self) -> int:
        """Return the number of queued plus in-flight requests."""
        with self._lock:
            return self._queue.qsize() + (1 if self._in_flight is not None else 0)

    def request(self, key: str, media_path: str) -> None:
        """Ask for an image to be downloaded and cached (non-blocking, thread-safe).

        Ignored when the key is already queued, in flight, stored or known to be missing on
        RA; during the offline backoff; after :meth:`close`; or when the queue is full.

        Args:
            key: Image cache key.
            media_path: Path on the media host, e.g. ``"/Badge/198102.png"``.
        """
        with self._lock:
            if self._disabled or self._stop.is_set() or self._in_backoff():
                return
            if key in self._known or key in self._failed:
                return
            try:
                self._queue.put_nowait((key, media_path))
            except queue.Full:
                return
            self._known.add(key)
            self._ensure_worker()
        self._wake.set()

    def close(self, timeout: float = 2.0) -> None:
        """Stop the worker and release its session.

        Args:
            timeout: Seconds to wait for the worker to finish its current download.
        """
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _in_backoff(self) -> bool:
        """Report whether requests are paused after a network failure (lock held).

        Returns:
            ``True`` while the backoff lasts; clears it once expired.
        """
        if self._backoff_until is None:
            return False
        if self._clock() < self._backoff_until:
            return True
        self._backoff_until = None
        return False

    def _ensure_worker(self) -> None:
        """Start the worker thread on the first request (lock held)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="cheevos-media", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        """Worker body: open the session, then download queued images until closed."""
        session = self._open()
        if session is None:
            return
        client, media, close = session
        try:
            while not self._stop.is_set():
                self._wake.clear()
                item = self._take()
                if item is None:
                    self._wake.wait(_POLL_SECONDS)
                    continue
                self._fetch(client, media, *item)
        finally:
            try:
                close()
            except (CheevosError, OSError, sqlite3.Error):
                logger.exception("Closing the image session failed")

    def _take(self) -> tuple[str, str] | None:
        """Pop the next request and mark it in flight in one step (so ``pending`` never dips).

        Returns:
            ``(key, media path)``, or ``None`` when the queue is empty.
        """
        with self._lock:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return None
            self._in_flight = item[0]
            return item

    def _open(self) -> MediaSession | None:
        """Open the session; disable the fetcher if that is impossible.

        Returns:
            The session, or ``None`` when it could not be opened.
        """
        try:
            return self._open_session()
        except (CheevosError, OSError, sqlite3.Error):
            logger.exception("Background image downloads disabled")
            with self._lock:
                self._disabled = True
                self._drain()
            return None

    def _fetch(self, client: MediaSource, media: MediaStore, key: str, path: str) -> None:
        """Download one image and store it, classifying failures.

        Args:
            client: Media downloader.
            media: Image store.
            key: Cache key.
            path: Media-host path.
        """
        try:
            media.put(key, client.media(path))
        except NetworkError as exc:
            logger.info("Image downloads paused (offline): %s", exc)
            self._enter_backoff(key)
        except CheevosError as exc:
            logger.warning("Image %s unavailable: %s", key, exc)
            with self._lock:
                self._known.discard(key)
                self._failed.add(key)
        except sqlite3.Error:
            logger.exception("Could not store image %s", key)
            with self._lock:
                self._known.discard(key)  # may be retried later
        else:
            with self._lock:
                self._version += 1
        finally:
            with self._lock:
                self._in_flight = None

    def _enter_backoff(self, key: str) -> None:
        """Pause requests after a network failure and drop everything queued.

        Args:
            key: The in-flight key that failed; it may be requested again after the backoff.
        """
        with self._lock:
            self._backoff_until = self._clock() + self._offline_backoff
            self._known.discard(key)
            self._drain()

    def _drain(self) -> None:
        """Empty the queue, forgetting the dropped keys so they can be re-requested (lock held)."""
        while True:
            try:
                dropped, _ = self._queue.get_nowait()
            except queue.Empty:
                return
            self._known.discard(dropped)
