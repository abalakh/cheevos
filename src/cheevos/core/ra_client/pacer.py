"""Space Web API requests for one API key, across every client and thread.

RA limits requests per key (.agents/retroachievements.md, "Politeness"). On 2026-10-06 a sync
at about 2.6 requests per second drew HTTP 429 within seconds, then ``Retry-After: 600``;
one request per second drew none in 20 minutes. The sync, on-demand fetches and the key check
each have their own client, so they share one :class:`Pacer` that keeps their combined pace.

A pacer only schedules: :meth:`Pacer.reserve` returns how long the caller must wait, and the
caller waits in a way it can interrupt.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from cheevos.core.errors import RateLimitedError

API_INTERVAL = 1.0  # seconds between request starts: the pace measured clean on 2026-10-06
LONG_PAUSE = 10.0  # RA asking for a longer pause stops work instead of waiting it out


class Pacer:
    """Hands out request slots at least ``interval`` seconds apart (thread-safe).

    Args:
        interval: Minimum seconds between the starts of two requests.
        clock: Monotonic clock.
        long_pause: Pauses longer than this make :meth:`reserve` raise instead of waiting.
    """

    def __init__(
        self,
        interval: float = API_INTERVAL,
        *,
        clock: Callable[[], float] = time.monotonic,
        long_pause: float = LONG_PAUSE,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._long_pause = long_pause
        self._lock = threading.Lock()
        self._next: float | None = None  # earliest start of the next request
        self._paused_until: float | None = None

    def reserve(self) -> float:
        """Take the next request slot.

        Returns:
            Seconds the caller must wait before starting its request (0 when it may start now).

        Raises:
            RateLimitedError: RA asked for a pause longer than ``long_pause``; carries the
                seconds left.
        """
        with self._lock:
            now = self._clock()
            paused = self._paused_until if self._paused_until is not None else now
            if paused - now > self._long_pause:
                raise RateLimitedError(paused - now)
            start = max(now, paused, self._next if self._next is not None else now)
            self._next = start + self._interval
            return start - now

    def pause(self, seconds: float) -> None:
        """Start no request for ``seconds`` (RA answered HTTP 429).

        Args:
            seconds: Length of the pause, from now.
        """
        with self._lock:
            until = self._clock() + max(seconds, 0.0)
            if self._paused_until is None or until > self._paused_until:
                self._paused_until = until
