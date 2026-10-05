from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from cheevos.core.models import Achievement, AchievementType, PendingAward
from cheevos.core.settings import DescriptionHiding, Settings
from cheevos.core.sync.session import Credentials
from cheevos.ui.context import AppContext
from cheevos.ui.screens.achievement import hides_description

LOCKED = Achievement(1, 1, "Boss", "Defeat the final boss", 10, 20, "1", 1, None, 5, 2, None, None)
QUEUED = PendingAward(1, 1, "Game", "Boss", 10, 100)


@pytest.mark.parametrize(
    ("mode", "kind", "hidden"),
    [
        (DescriptionHiding.OFF, AchievementType.WIN_CONDITION, False),
        (DescriptionHiding.ALL, None, True),
        (DescriptionHiding.ALL, AchievementType.MISSABLE, True),
        (DescriptionHiding.STORY, AchievementType.WIN_CONDITION, True),
        (DescriptionHiding.STORY, AchievementType.PROGRESSION, True),
        (DescriptionHiding.STORY, AchievementType.MISSABLE, False),
        (DescriptionHiding.STORY, None, False),  # untagged sets hide nothing
    ],
)
def test_which_locked_descriptions_are_hidden(mode, kind, hidden):
    assert hides_description(mode, replace(LOCKED, type=kind)) is hidden


def test_unlocked_ones_are_never_hidden():
    unlocked = replace(LOCKED, earned_at=100)
    assert not hides_description(DescriptionHiding.ALL, unlocked)
    assert not hides_description(DescriptionHiding.ALL, LOCKED, pending=QUEUED)


class FakeProxy:
    def __init__(self, awards):
        self.awards = awards

    def installed(self):
        return True

    def enabled(self):
        return True

    def pending_awards(self, _username):
        return self.awards


class FakeData:
    def unlocked_among(self, ids):
        return {achievement_id for achievement_id in ids if achievement_id == 3}


def test_pending_by_game_skips_synced_and_unknown_games():
    queue = [
        PendingAward(1, 519, "", "", None, 1),
        PendingAward(2, 519, "", "", None, 2),
        PendingAward(3, 519, "", "", None, 3),  # RA already has it
        PendingAward(4, None, "", "", None, 4),  # the proxy can't name the game
        PendingAward(5, 3830, "", "", None, 5),
    ]
    none = cast(Any, None)
    ctx = AppContext(
        paths=none,
        credentials=Credentials("Balah", "k"),
        settings=Settings(),
        data=cast(Any, FakeData()),
        media_cache=none,
        media=none,
        sync=none,
        proxy=cast(Any, FakeProxy(queue)),
        screenshots=none,
        icons=Path(),
        validate_key=lambda _u, _k: True,
        fetch_unlocks=lambda _s, _e: [],
    )
    assert ctx.pending_by_game() == {519: 2, 3830: 1}
