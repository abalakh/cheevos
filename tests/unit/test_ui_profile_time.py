from email.utils import formatdate
from unittest.mock import Mock

import pytest

from cheevos.core.clock import ServerClock
from cheevos.core.models import UnlockWindow, UserProfile
from cheevos.core.stats import window_start
from cheevos.core.storage.data_cache import DataCache
from cheevos.ui.screens.profile import _see_more

NOW = 1_791_158_400
PROFILE = UserProfile("Balah", "", "", None, 0, 0, 0, None, None, "", None)


@pytest.mark.parametrize("wall", [0, NOW + 10 * 365 * 86400])
def test_more_queries_and_stores_the_server_time_window(monkeypatch, tmp_path, wall):
    monkeypatch.setattr("cheevos.ui.screens.profile.busy", Mock())
    clock = ServerClock(wall_clock=lambda: wall, monotonic=lambda: 0)
    cache = DataCache.open(tmp_path / "data.db", "Balah")
    ctx = Mock(data=cache, clock=clock.now, fetch_unlocks=Mock(return_value=[]))

    def refresh_time():
        clock.observe_date(formatdate(NOW, usegmt=True))
        return True

    ctx.refresh_time = refresh_time
    try:
        recent, _ = _see_more(ctx, PROFILE)
        assert recent is not None
        ctx.fetch_unlocks.assert_called_once_with(window_start(NOW), NOW)
        assert cache.unlock_window() == UnlockWindow(window_start(NOW), NOW, ())
    finally:
        cache.close()


def test_more_reuses_a_fresh_window_after_time_recovers(monkeypatch, tmp_path):
    monkeypatch.setattr("cheevos.ui.screens.profile.busy", Mock())
    clock = ServerClock(wall_clock=lambda: 0, monotonic=lambda: 0)
    cache = DataCache.open(tmp_path / "data.db", "Balah")
    cache.save_unlock_window(UnlockWindow(window_start(NOW), NOW, ()))
    ctx = Mock(data=cache, clock=clock.now)

    def refresh_time():
        clock.observe_date(formatdate(NOW, usegmt=True))
        return True

    ctx.refresh_time = refresh_time
    try:
        assert _see_more(ctx, PROFILE)[0] is not None
        ctx.fetch_unlocks.assert_not_called()
    finally:
        cache.close()
