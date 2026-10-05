"""RetroAchievements Web API client: typed endpoints, throttling, retries and error mapping."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import cheevos
from cheevos.core.errors import ApiPayloadError, AuthError, NetworkError, RateLimitedError
from cheevos.core.models import (
    Award,
    AwardCounts,
    GameDetail,
    GameProgress,
    Unlock,
    UserProfile,
)
from cheevos.core.ra_client import parse
from cheevos.core.ra_client.redact import install_redaction
from cheevos.core.ra_client.transport import API_HOST, MEDIA_HOST, Response, Transport

logger = logging.getLogger(__name__)

PAGE_SIZE = 500
UNLOCK_PAGE = 500  # RA's row cap for API_GetAchievementsEarnedBetween
UNLOCK_PAGES = 10  # at most 5,000 unlocks per window
_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_TOO_MANY = 429
_AUTH_STATUSES = frozenset({401, 403})


def default_user_agent(platform: str) -> str:
    """Return the User-Agent RA sees, e.g. ``"Cheevos/0.1.0 (SpruceOS; MiyooMini)"``.

    Args:
        platform: Spruce platform name.

    Returns:
        The User-Agent string.
    """
    return f"Cheevos/{cheevos.__version__} (SpruceOS; {platform})"


def _is_unauthenticated(data: object) -> bool:
    """Recognise RA's "Unauthenticated" error payload.

    Args:
        data: Decoded JSON.

    Returns:
        ``True`` for ``{"message": "Unauthenticated.", "errors": [...]}``-style bodies.
    """
    if not isinstance(data, dict):
        return False
    message = str(data.get("message", ""))
    errors = data.get("errors")
    codes = (
        {str(e.get("code")) for e in errors if isinstance(e, dict)}
        if isinstance(errors, list)
        else set()
    )
    return message.startswith("Unauthenticated") or "unauthorized" in codes


def _retry_after(response: Response) -> float | None:
    """Read a ``Retry-After`` header given in seconds.

    Args:
        response: The response.

    Returns:
        Seconds to wait, or ``None`` if absent or not a number (HTTP dates are ignored).
    """
    try:
        return max(float(response.headers.get("retry-after", "")), 0.0)
    except ValueError:
        return None


class RaClient:
    """Typed access to the Web API endpoints Cheevos uses.

    API requests are spaced at least ``min_interval`` seconds apart (RA publishes no rate
    limits; this keeps a full sync polite). Media downloads are not throttled.

    Args:
        username: RA username whose data is requested.
        api_key: The user's Web API key; registered for log redaction.
        transport: HTTP transport (keep-alive HTTPS, or fixtures in tests).
        user_agent: User-Agent header value.
        min_interval: Minimum seconds between API requests.
        clock: Monotonic clock (injectable for tests).
        sleep: Sleep function (injectable for tests).
        max_retries: Retries for HTTP 429 and 5xx responses.
    """

    def __init__(  # noqa: PLR0913 — collaborators injected for deterministic tests
        self,
        username: str,
        api_key: str,
        transport: Transport,
        *,
        user_agent: str,
        min_interval: float = 0.3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ) -> None:
        install_redaction(api_key)
        self._username = username
        self._api_key = api_key
        self._transport = transport
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._max_retries = max_retries
        self._last_request: float | None = None

    @property
    def username(self) -> str:
        """The username requests are made for."""
        return self._username

    # --- endpoints ------------------------------------------------------------------------------

    def validate_key(self) -> bool:
        """Check the API key with a cheap request.

        Returns:
            ``True`` when RA accepts the key.

        Raises:
            AuthError: RA rejected the key.
            NetworkError: RA could not be reached.
            ApiPayloadError: RA answered with something unexpected.
        """
        parse.parse_user_summary(self._api("API_GetUserProfile"))
        return True

    def user_summary(self, recent_achievements: int = 10) -> UserProfile:
        """Fetch the profile with rank (``API_GetUserSummary``).

        Args:
            recent_achievements: Recent achievements RA should include.

        Returns:
            The profile.
        """
        # g=1 makes RA include the last game (title, console, icon) for "now playing".
        data = self._api("API_GetUserSummary", g=1, a=recent_achievements)
        return parse.parse_user_summary(data)

    def completion_progress(self) -> list[GameProgress]:
        """Fetch every game with unlocks, across all pages (``API_GetUserCompletionProgress``).

        Returns:
            The games in RA's order.
        """
        games: list[GameProgress] = []
        while True:
            page, total = parse.parse_completion_progress(
                self._api("API_GetUserCompletionProgress", c=PAGE_SIZE, o=len(games))
            )
            games.extend(page)
            if not page or len(games) >= total:
                return games

    def recently_played(self, count: int = 50) -> list[GameProgress]:
        """Fetch recently played games, including ones without unlocks.

        Args:
            count: How many games (RA allows up to 50).

        Returns:
            The games, most recent first.
        """
        return parse.parse_recently_played(self._api("API_GetUserRecentlyPlayedGames", c=count))

    def game_detail(self, game_id: int) -> GameDetail:
        """Fetch a game's achievements with the user's unlocks.

        Args:
            game_id: RA game ID.

        Returns:
            The game detail.
        """
        data = self._api("API_GetGameInfoAndUserProgress", g=game_id, a=1)
        return parse.parse_game_detail(data)

    def awards(self) -> tuple[AwardCounts, list[Award]]:
        """Fetch the user's award counters and visible game awards.

        Returns:
            Counters and awards.
        """
        return parse.parse_awards(self._api("API_GetUserAwards"))

    def unlocks_between(self, start: int, end: int) -> list[Unlock]:
        """Fetch the user's unlocks in a time window (``API_GetAchievementsEarnedBetween``).

        RA returns at most :data:`UNLOCK_PAGE` rows, oldest first, so a full page is followed
        by another one starting at its last unlock (rows seen twice are dropped).

        Args:
            start: Window start (UTC epoch seconds).
            end: Window end (UTC epoch seconds).

        Returns:
            The unlocks, oldest first.
        """
        unlocks: list[Unlock] = []
        seen: set[tuple[int, int]] = set()
        since = start
        for _page in range(UNLOCK_PAGES):
            data = self._api("API_GetAchievementsEarnedBetween", f=since, t=end)
            page = parse.parse_unlocks(data)
            fresh = [u for u in page if (u.achievement_id, u.unlocked_at) not in seen]
            seen.update((u.achievement_id, u.unlocked_at) for u in fresh)
            unlocks.extend(fresh)
            if len(page) < UNLOCK_PAGE or not fresh:
                break
            since = page[-1].unlocked_at
        return unlocks

    def media(self, path: str) -> bytes:
        """Download a file from RA's media host (badges, game icons, avatars).

        Args:
            path: Media path, e.g. ``"/Badge/198102_lock.png"``.

        Returns:
            The file contents.

        Raises:
            ApiPayloadError: Invalid path, or the file does not exist (HTTP 404/other).
            NetworkError: The media host could not be reached or failed (5xx).
        """
        if not path.startswith("/"):
            raise ApiPayloadError(f"invalid media path {path!r}")
        response = self._transport.get(MEDIA_HOST, path, self._headers)
        if response.status == _HTTP_OK:
            return response.body
        if response.status >= 500:  # noqa: PLR2004 — HTTP server errors
            raise NetworkError(f"media {path}: HTTP {response.status}")
        raise ApiPayloadError(f"media {path}: HTTP {response.status}")

    # --- plumbing -------------------------------------------------------------------------------

    def _api(self, method: str, **params: object) -> Any:  # noqa: ANN401 — decoded JSON
        """Call an API endpoint, retrying rate limits and server errors.

        Args:
            method: Endpoint name without ``.php``.
            **params: Query parameters other than credentials.

        Returns:
            The decoded JSON body.
        """
        query = urlencode({"y": self._api_key, "u": self._username, **params})
        path = f"/API/{method}.php?{query}"
        attempt = 0
        while True:
            self._throttle()
            response = self._transport.get(API_HOST, path, self._headers)
            delay = self._retry_delay(method, response, attempt)
            if delay is None:
                return self._decode(method, response)
            attempt += 1
            logger.warning(
                "%s: HTTP %d, retrying in %.1fs (%d/%d)",
                method,
                response.status,
                delay,
                attempt,
                self._max_retries,
            )
            self._sleep(delay)

    def _throttle(self) -> None:
        """Wait so API requests are at least ``min_interval`` apart."""
        now = self._clock()
        if self._last_request is not None:
            wait = self._min_interval - (now - self._last_request)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last_request = now

    def _retry_delay(self, method: str, response: Response, attempt: int) -> float | None:
        """Decide whether a response should be retried, and after how long.

        Args:
            method: Endpoint name, for error messages.
            response: The response.
            attempt: Retries already made.

        Returns:
            Seconds to wait before retrying, or ``None`` if the response is final.

        Raises:
            RateLimitedError: Still rate limited after ``max_retries`` retries.
            NetworkError: Still failing with 5xx after ``max_retries`` retries.
        """
        backoff = float(2**attempt)
        if response.status == _HTTP_TOO_MANY:
            retry_after = _retry_after(response)
            if attempt >= self._max_retries:
                raise RateLimitedError(retry_after)
            return retry_after if retry_after is not None else backoff
        if response.status >= 500:  # noqa: PLR2004 — HTTP server errors
            if attempt >= self._max_retries:
                raise NetworkError(f"{method}: HTTP {response.status} from RetroAchievements")
            return backoff
        return None

    @staticmethod
    def _decode(method: str, response: Response) -> Any:  # noqa: ANN401 — decoded JSON
        """Map a final response to decoded JSON or a typed error.

        Args:
            method: Endpoint name, for error messages.
            response: The response.

        Returns:
            The decoded JSON body.

        Raises:
            AuthError: The key was rejected.
            ApiPayloadError: Unexpected status or invalid JSON.
        """
        try:
            data = json.loads(response.body) if response.body else None
        except ValueError:
            data = None
            if response.status == _HTTP_OK:
                raise ApiPayloadError(f"{method}: response is not valid JSON") from None
        if response.status in _AUTH_STATUSES or _is_unauthenticated(data):
            raise AuthError("RetroAchievements rejected the Web API key")
        if response.status != _HTTP_OK:
            detail = "not found" if response.status == _HTTP_NOT_FOUND else "unexpected status"
            raise ApiPayloadError(f"{method}: HTTP {response.status} ({detail})")
        return data
