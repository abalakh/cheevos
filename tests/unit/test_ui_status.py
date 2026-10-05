from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from cheevos.core.models import AwardKind, GameProgress
from cheevos.core.sync.progress import Failure, Phase, SyncStatus
from cheevos.ui.pyui.status_bar import BarStatus
from cheevos.ui.screens.rows import completion
from cheevos.ui.screens.status import RESULT_SECONDS, SyncBar, progress_text

NOW = 1_791_158_400.0
ICONS = Path("/icons")


@dataclass
class FakeSync:
    state: SyncStatus = field(default_factory=SyncStatus)
    cancelling: bool = False
    cancels: int = 0

    def status(self) -> SyncStatus:
        return self.state

    def cancel(self) -> None:
        self.cancels += 1


@dataclass
class FakeData:
    meta: dict[str, str] = field(default_factory=dict)
    reads: int = 0

    def get_meta(self, key: str) -> str | None:
        self.reads += 1
        return self.meta.get(key)


@dataclass
class FakeContext:
    sync: FakeSync = field(default_factory=FakeSync)
    data: FakeData = field(default_factory=FakeData)
    now: float = NOW
    starts: int = 0
    key_prompts: int = 0

    def clock(self) -> float:
        return self.now

    def start_sync(self) -> bool:
        self.starts += 1
        return True


def make_bar(ctx: FakeContext) -> SyncBar:
    def enter_key() -> None:
        ctx.key_prompts += 1

    return SyncBar(cast(Any, ctx), ICONS, enter_key)


def running(phase: Phase, *, done: int = 0, total: int = 0, current: str = "") -> SyncStatus:
    return SyncStatus(phase=phase, done=done, total=total, current=current)


def finished(phase: Phase, at: float, failure: Failure | None = None) -> SyncStatus:
    return SyncStatus(phase=phase, failure=failure, finished_at=at)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (running(Phase.PREFLIGHT), "Checking connection"),
        (running(Phase.LIBRARY), "Syncing game list"),
        (running(Phase.DETAILS, done=2, total=12, current="FFTA"), "Syncing 3/12 · FFTA"),
        (running(Phase.DETAILS, done=12, total=12, current="FFTA"), "Syncing 12/12 · FFTA"),
        (running(Phase.DETAILS), "Syncing achievements"),
        (running(Phase.MEDIA, done=4, total=40), "Downloading images 4/40"),
    ],
)
def test_progress_text(status, expected):
    assert progress_text(status) == expected


def test_running_sync_shows_everywhere_with_cancel_hint_only_when_detailed():
    ctx = FakeContext(sync=FakeSync(running(Phase.PROFILE)))
    bar = make_bar(ctx)
    assert bar.status(True) == BarStatus("Syncing profile", ICONS / "reload.png", "Cancel", True)
    assert bar.status(False) == BarStatus("Syncing profile", ICONS / "reload.png", "", True)


def test_cancelling_has_no_hint():
    ctx = FakeContext(sync=FakeSync(running(Phase.DETAILS), cancelling=True))
    status = make_bar(ctx).status(True)
    assert status is not None
    assert (status.text, status.action, status.live) == ("Cancelling…", "", False)


def test_result_shows_everywhere_briefly_then_only_when_detailed():
    ctx = FakeContext(
        sync=FakeSync(finished(Phase.DONE, NOW)), data=FakeData({"last_sync_at": str(int(NOW))})
    )
    bar = make_bar(ctx)
    assert bar.status(False) == BarStatus("Synced just now", ICONS / "check.png")
    ctx.now = NOW + RESULT_SECONDS + 1
    assert bar.status(False) is None
    assert bar.status(True) == BarStatus("Synced just now", ICONS / "check.png", "Sync")


def test_idle_status_reads_last_sync_time_once_per_change():
    ctx = FakeContext(data=FakeData({"last_sync_at": str(int(NOW - 300))}))
    bar = make_bar(ctx)
    for _ in range(3):
        status = bar.status(True)
    assert status == BarStatus("Synced 5 min ago", ICONS / "check.png", "Sync")
    assert ctx.data.reads == 1
    assert make_bar(FakeContext()).status(True) == BarStatus(
        "Not synced yet", ICONS / "reload.png", "Sync"
    )


@pytest.mark.parametrize(
    ("failure", "text", "icon", "action"),
    [
        (Failure.OFFLINE, "Offline · showing saved data", "cloud", "Retry"),
        (Failure.CLOCK, "Clock not set · connect to Wi-Fi", "clock", "Retry"),
        (Failure.AUTH, "API key rejected", "lock", "Enter key"),
        (Failure.RATE_LIMITED, "RetroAchievements unavailable", "cloud", "Retry"),
    ],
)
def test_failure_offers_a_way_out_on_detailed_screens(failure, text, icon, action):
    ctx = FakeContext(sync=FakeSync(finished(Phase.FAILED, NOW - 60, failure)))
    bar = make_bar(ctx)
    assert bar.status(True) == BarStatus(text, ICONS / f"{icon}.png", action)
    assert bar.status(False) is None


def test_cancelled_shows_briefly_then_falls_back_to_last_sync():
    ctx = FakeContext(
        sync=FakeSync(finished(Phase.CANCELLED, NOW)),
        data=FakeData({"last_sync_at": str(int(NOW - 7200))}),
    )
    bar = make_bar(ctx)
    assert bar.status(True) == BarStatus("Sync cancelled", ICONS / "reload.png", "Sync")
    ctx.now = NOW + RESULT_SECONDS
    assert bar.status(True) == BarStatus("Synced 2 h ago", ICONS / "check.png", "Sync")


def test_start_syncs_when_idle_and_cancels_when_running():
    ctx = FakeContext()
    bar = make_bar(ctx)
    bar.press_start()
    assert (ctx.starts, ctx.sync.cancels) == (1, 0)
    ctx.sync.state = running(Phase.LIBRARY)
    bar.press_start()
    assert (ctx.starts, ctx.sync.cancels) == (1, 1)


@pytest.mark.parametrize(
    ("failure", "starts", "key_prompts"), [(Failure.AUTH, 0, 1), (Failure.NETWORK, 1, 0)]
)
def test_start_asks_for_a_new_key_only_after_a_rejection(failure, starts, key_prompts):
    # Retrying with a key RA just rejected can't work.
    ctx = FakeContext(sync=FakeSync(finished(Phase.FAILED, NOW - 60, failure)))
    make_bar(ctx).press_start()
    assert (ctx.starts, ctx.key_prompts) == (starts, key_prompts)


def game(earned: int, hardcore: int, total: int = 40, award: AwardKind | None = None):
    return GameProgress(1, "Game", 5, "GBA", "/i.png", total, earned, hardcore, None, award, None)


def test_completion_bar_splits_hardcore_and_casual():
    bar = completion(game(earned=26, hardcore=12))
    assert (bar.done, bar.extra, bar.label, bar.award) == (0.3, 0.35, "65%", None)


def test_completion_rounds_inwards_and_carries_the_award():
    assert completion(game(earned=39, hardcore=39)).label == "97%"
    assert completion(game(earned=199, hardcore=0, total=200)).label == "99%"
    assert completion(game(earned=1, hardcore=0, total=106)).label == "1%"
    mastered = completion(game(earned=40, hardcore=40, award=AwardKind.MASTERED))
    assert (mastered.done, mastered.label, mastered.award) == (1.0, "100%", AwardKind.MASTERED)
    assert completion(game(0, 0, total=0)).label == "0%"


def test_completion_counts_unlocks_waiting_to_sync_as_casual():
    bar = completion(game(earned=20, hardcore=10), pending=2)
    assert (bar.done, bar.extra, bar.label) == (0.25, 0.3, "55%")
    assert completion(game(earned=39, hardcore=0), pending=5).extra == 1.0  # capped at the set
