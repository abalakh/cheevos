import pytest

from cheevos.core.models import (
    Award,
    AwardCounts,
    AwardKind,
    GameProgress,
    Unlock,
    UnlockWindow,
    UserProfile,
)
from cheevos.core.stats import (
    DAY,
    WEEK,
    console_progress,
    is_retail,
    is_subset,
    player_stats,
    recent_points,
    window_start,
)

NOW = 1_791_158_400  # a UTC midnight


def game(game_id, *, earned=0, hardcore=0, total=40, award=None, console=5, title="Game", last=0):
    return GameProgress(
        game_id,
        title,
        console,
        f"Console {console}",
        "",
        total,
        earned,
        hardcore,
        last,
        award,
        None,
    )


def profile(hardcore=1000, casual=100, retro=1500):
    return UserProfile("Balah", "", "", None, hardcore, casual, retro, 5, 100, "", None)


def award(game_id, kind, *, title="Game", console=5):
    return Award(game_id, title, "Console", "", kind, None, console_id=console)


@pytest.mark.parametrize(
    ("title", "subset"),
    [("Zelda", False), ("Zelda [Subset - Bonus]", True), ("~Test Kit~ Zelda", True)],
)
def test_subsets_and_test_kits(title, subset):
    assert is_subset(title) is subset


def test_retail_excludes_tags_and_homebrew_consoles():
    assert is_retail(award(1, AwardKind.BEATEN_HARDCORE))
    assert not is_retail(award(1, AwardKind.BEATEN_HARDCORE, title="~Hack~ Mario"))
    assert not is_retail(award(1, AwardKind.BEATEN_HARDCORE, console=71))


def test_player_stats_follow_ras_rules():
    games = [
        game(1, earned=20, hardcore=10, award=AwardKind.BEATEN_HARDCORE),
        game(2, earned=40, hardcore=40, award=AwardKind.MASTERED),
        game(3, earned=4, hardcore=0),
        game(4, earned=3, hardcore=3, total=5),  # under 6 achievements: not counted
        game(5, earned=10, hardcore=10, title="Zelda [Subset - Bonus]"),  # subset: not a game
        game(6),  # played, nothing unlocked: not started
    ]
    awards = [
        award(1, AwardKind.BEATEN_HARDCORE),
        award(2, AwardKind.BEATEN_HARDCORE, title="~Homebrew~ Game"),
        award(5, AwardKind.BEATEN_HARDCORE, title="Zelda [Subset - Bonus]"),
    ]
    counts = AwardCounts(mastered=1, completed=0, beaten_hardcore=4, beaten_softcore=0)
    stats = player_stats(profile(), games, counts, awards, NOW - 10 * WEEK, NOW)
    assert (stats.unlocks_hardcore, stats.unlocks_casual) == (60, 14)
    assert stats.retro_ratio == 1.5
    assert stats.games_beaten == 3  # 4 counted by RA, minus the visible subset
    assert stats.games_beaten_retail == 1
    assert stats.started_beaten == 0.5  # sets of any size count as started
    assert stats.average_completion == pytest.approx((0.5 + 1.0 + 0.1) / 3)
    assert stats.points_per_week == 100


def test_player_stats_without_data():
    stats = player_stats(profile(hardcore=0), [], None, [], None, NOW)
    assert stats.retro_ratio is None
    assert stats.started_beaten is None
    assert stats.average_completion is None
    assert stats.points_per_week is None


def test_console_progress_counts_played_beaten_mastered_latest_first():
    games = [
        game(1, earned=5, console=7, last=100),
        game(2, earned=5, console=7, award=AwardKind.MASTERED),
        game(3, earned=5, console=7, award=AwardKind.BEATEN_SOFTCORE),
        game(4, earned=5, console=5, award=AwardKind.COMPLETED, last=900),
        game(5, earned=5, console=101),  # Events: not a console
        game(6, console=7),  # not started
    ]
    rows = console_progress(games)
    assert [(r.console_name, r.played, r.beaten, r.mastered) for r in rows] == [
        ("Console 5", 1, 1, 1),  # played most recently
        ("Console 7", 3, 2, 1),
    ]
    assert rows[0].last_activity == 900


def unlock(days_ago, points, hardcore=True, console="Game Boy Advance"):
    return Unlock(1, 1, points, hardcore, NOW + 3600 - days_ago * DAY, console)


def test_recent_points_buckets_days_like_ra():
    window = UnlockWindow(
        window_start(NOW),
        NOW + 7200,
        (
            unlock(0, 10),
            unlock(6, 5),
            unlock(7, 20),  # outside the last 7 days
            unlock(29, 1),
            unlock(30, 50),  # outside the window
            unlock(1, 99, hardcore=False),  # casual: not counted for a hardcore player
            unlock(2, 77, console="Events"),
        ),
    )
    points = recent_points(window, casual_player=False)
    assert (points.last_7_days, points.last_30_days) == (15, 36)
    assert len(points.per_day) == 30
    assert points.per_day[-1] == 10
    assert points.per_day[0] == 1
    assert recent_points(window, casual_player=True).last_7_days == 15 + 99
