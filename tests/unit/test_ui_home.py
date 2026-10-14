from types import SimpleNamespace
from typing import cast

from cheevos.core.sync.progress import Phase
from cheevos.ui.context import AppContext
from cheevos.ui.screens.home import Home


def home(*, sync_when_shown):
    starts = []
    ctx = SimpleNamespace(
        start_sync=lambda: starts.append(True) or True,
        sync=SimpleNamespace(status=lambda: SimpleNamespace(phase=Phase.IDLE)),
    )
    shown = Home(cast(AppContext, ctx), sync_when_shown=sync_when_shown)
    shown._last_phase = Phase.IDLE  # the rows don't change
    return shown, starts


def test_the_auto_sync_starts_once_home_is_on_screen():
    shown, starts = home(sync_when_shown=True)
    assert starts == []  # not while Home is being built
    assert shown.tick() is None  # the first tick follows the first frame
    assert shown.tick() is None
    assert starts == [True]


def test_no_sync_when_the_setting_is_off():
    shown, starts = home(sync_when_shown=False)
    shown.tick()
    assert starts == []
