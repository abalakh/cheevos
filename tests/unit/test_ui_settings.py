from types import SimpleNamespace
from typing import cast

import pytest

from cheevos.ui.context import AppContext
from cheevos.ui.screens.settings import _proxy_rows


def context(*, waiting: int, cached: int) -> AppContext:
    proxy = SimpleNamespace(
        installed=lambda: True,
        enabled=lambda: True,
        online=lambda: True,
        cached_game_ids=lambda: set(range(cached)),
    )
    return cast(
        AppContext,
        SimpleNamespace(
            proxy=proxy,
            pending_awards=lambda: dict.fromkeys(range(waiting)),
            icon=lambda name: name,
        ),
    )


@pytest.mark.parametrize(
    ("waiting", "cached", "status"),
    [
        (1, 1, "On · online · 1 waiting · 1 game cached"),
        (0, 12, "On · online · 0 waiting · 12 games cached"),
    ],
)
def test_the_proxy_row_counts_each_number(waiting, cached, status):
    (row,) = _proxy_rows(context(waiting=waiting, cached=cached))

    assert row.description == status
