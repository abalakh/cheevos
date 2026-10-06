import threading

import pytest

from cheevos.core.errors import RateLimitedError
from cheevos.core.ra_client.pacer import Pacer


class FrozenClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_slots_are_spaced_by_the_interval():
    clock = FrozenClock()
    pacer = Pacer(1.0, clock=clock)
    assert pacer.reserve() == 0
    assert pacer.reserve() == 1.0
    clock.now += 0.4
    assert pacer.reserve() == pytest.approx(1.6)  # the third slot starts 2 s after the first


def test_no_wait_once_the_interval_has_passed():
    clock = FrozenClock()
    pacer = Pacer(1.0, clock=clock)
    pacer.reserve()
    clock.now += 5
    assert pacer.reserve() == 0


def test_a_short_pause_delays_the_next_slot():
    clock = FrozenClock()
    pacer = Pacer(0.0, clock=clock)
    pacer.pause(3)
    assert pacer.reserve() == 3


def test_a_long_pause_raises_until_it_is_short_enough_to_wait():
    clock = FrozenClock()
    pacer = Pacer(1.0, clock=clock, long_pause=10)
    pacer.pause(600)
    with pytest.raises(RateLimitedError) as raised:
        pacer.reserve()
    assert raised.value.retry_after == 600
    clock.now += 595
    assert pacer.reserve() == 5


def test_a_shorter_pause_never_shortens_a_longer_one():
    clock = FrozenClock()
    pacer = Pacer(0.0, clock=clock)
    pacer.pause(600)
    pacer.pause(2)
    with pytest.raises(RateLimitedError):
        pacer.reserve()


def test_concurrent_callers_get_distinct_slots():
    pacer = Pacer(1.0, clock=FrozenClock())
    waits: list[float] = []
    lock = threading.Lock()

    def take():
        wait = pacer.reserve()
        with lock:
            waits.append(wait)

    threads = [threading.Thread(target=take) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(waits) == [float(i) for i in range(8)]
