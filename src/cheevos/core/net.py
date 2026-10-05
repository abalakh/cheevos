"""Pre-flight checks before syncing: is RA reachable, and is the clock sane enough for TLS?"""

from __future__ import annotations

import logging
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Opens a request and returns a response-like object (``urllib.request.urlopen`` signature).
Opener = Callable[..., Any]


def is_online(
    *,
    host: str = "retroachievements.org",
    timeout: float = 3.0,
    opener: Opener | None = None,
    context: ssl.SSLContext | None = None,
) -> bool:
    """Check that ``https://<host>/`` answers a HEAD request.

    Any answer counts, including HTTP errors: the point is reachability. Only failures to
    connect (DNS, timeout, TLS) count as offline.

    Args:
        host: Host to probe.
        timeout: Seconds to wait.
        opener: Replacement for ``urllib.request.urlopen`` (tests).
        context: TLS context (devices pass one built from ``SSL_CERT_FILE``).

    Returns:
        ``True`` if the host answered.
    """
    request = urllib.request.Request(f"https://{host}/", method="HEAD")
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout, context=context):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception as exc:  # noqa: BLE001 — any failure means "offline", by design
        logger.info("RA unreachable: %s", exc)
        return False


def clock_plausible(now: float | None = None, *, min_year: int = 2026) -> bool:
    """Check the system clock: devices have no RTC and boot in 1970 until NTP syncs.

    TLS certificate validation fails with a wrong clock, so sync waits for this.

    Args:
        now: Epoch seconds to check (defaults to the current time).
        min_year: Earliest believable year.

    Returns:
        ``True`` if the UTC year is at least ``min_year``.
    """
    seconds = time.time() if now is None else now
    return time.gmtime(seconds).tm_year >= min_year
