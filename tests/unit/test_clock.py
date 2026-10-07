import calendar

import pytest

from cheevos.core.clock import ServerClock

DATE = "Wed, 07 Oct 2026 12:00:00 GMT"
EPOCH = calendar.timegm((2026, 10, 7, 12, 0, 0))


@pytest.mark.parametrize("wall", [0, calendar.timegm((2037, 1, 1, 0, 0, 0))])
def test_server_time_corrects_past_and_future_clocks_and_survives_system_jumps(wall):
    times = {"wall": wall, "elapsed": 10.0}
    clock = ServerClock(wall_clock=lambda: times["wall"], monotonic=lambda: times["elapsed"])
    assert clock.now() == wall
    clock.observe_date(DATE)
    assert clock.now() == EPOCH
    times.update(wall=123, elapsed=25.5)
    assert clock.now() == EPOCH + 15.5
    times.update(wall=wall, elapsed=31)
    assert clock.now() == EPOCH + 21
    clock.observe_date("Wed, 07 Oct 2026 12:01:00 GMT")
    assert clock.now() == EPOCH + 60


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "wrong",
        "Thu, 01 Jan 1970 00:00:00 GMT",
        "Wed, 07 Oct 2026 12:00:00",
        "32 Oct 2026 12:00:00 GMT",
    ],
)
def test_bad_dates_do_not_replace_known_time(value):
    clock = ServerClock(wall_clock=lambda: 123, monotonic=lambda: 10)
    clock.observe_date(value)
    assert clock.now() == 123
    clock.observe_date(DATE)
    clock.observe_date(value)
    assert clock.now() == EPOCH
