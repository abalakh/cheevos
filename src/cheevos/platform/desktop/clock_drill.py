"""Simulate RA supplying app time on a device whose system clock reads 1970."""

from __future__ import annotations

from cheevos.core.clock import ServerClock
from cheevos.core.ra_client.transport import API_HOST, Response, Transport


class ClockRecoveryTransport:
    """Serve fixtures and update the drill's private clock when the API answers.

    Args:
        base: Recorded transport.
        clock: App clock starting at the Unix epoch.
    """

    def __init__(self, base: Transport, clock: ServerClock) -> None:
        self._base = base
        self._clock = clock

    def get(self, host: str, path: str, headers: dict[str, str]) -> Response:
        """Answer a recorded request and supply a valid server date for API calls."""
        response = self._base.get(host, path, headers)
        if host == API_HOST:
            self._clock.observe_date("Wed, 07 Oct 2026 12:00:00 GMT")
        return response
