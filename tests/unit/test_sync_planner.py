from cheevos.core.models import AwardKind, GameProgress
from cheevos.core.sync.planner import (
    DAY,
    DetailPlan,
    PlanPolicy,
    badge_game_ids,
    merge_library,
    plan_detail_fetches,
)

NOW = 1_800_000_000


def game(game_id, *, earned=0, total=10, last_unlock=None, last_played=None, award=None, title=""):
    return GameProgress(
        game_id=game_id,
        title=title or f"Game {game_id}",
        console_id=1,
        console_name="Console",
        image_icon=f"/Images/{game_id}.png",
        max_possible=total,
        earned=earned,
        earned_hardcore=0,
        last_unlock_at=last_unlock,
        highest_award=award,
        highest_award_at=None,
        last_played_at=last_played,
    )


def test_fingerprint_changes_with_unlocks_awards_and_set_size():
    base = game(1, earned=2, last_unlock=100)
    assert base.fingerprint != game(1, earned=3, last_unlock=100).fingerprint
    assert base.fingerprint != game(1, earned=2, last_unlock=200).fingerprint
    assert base.fingerprint != game(1, earned=2, last_unlock=100, total=11).fingerprint
    assert (
        base.fingerprint
        != game(1, earned=2, last_unlock=100, award=AwardKind.BEATEN_SOFTCORE).fingerprint
    )
    assert base.fingerprint == game(1, earned=2, last_unlock=100, last_played=999).fingerprint


def test_merge_adds_played_without_unlocks_and_last_played():
    progress = [game(1, earned=2, last_unlock=100), game(2, earned=1, last_unlock=50)]
    recent = [game(2, last_played=500), game(3, last_played=300)]
    merged = merge_library(progress, recent)
    assert [g.game_id for g in merged] == [2, 3, 1]
    assert merged[0].earned == 1  # completion data kept
    assert merged[0].last_played_at == 500


def test_merge_orders_ties_by_title():
    merged = merge_library([game(1, title="b"), game(2, title="A")], [])
    assert [g.title for g in merged] == ["A", "b"]


def test_nothing_to_fetch_when_unchanged_and_fresh():
    games = [game(1, earned=2, last_unlock=100), game(2, earned=1, last_unlock=50)]
    states = {g.game_id: (g.fingerprint, NOW - DAY) for g in games}
    assert len(plan_detail_fetches(games, states, now=NOW)) == 0


def test_plans_never_fetched_then_changed_then_stale():
    games = [
        game(1, earned=3, last_unlock=300),  # changed
        game(2, earned=1, last_unlock=200),  # never fetched
        game(3, earned=1, last_unlock=100),  # stale
        game(4, earned=1, last_unlock=90),  # fresh
    ]
    states = {
        1: ("old-fingerprint", NOW - DAY),
        3: (games[2].fingerprint, NOW - 40 * DAY),
        4: (games[3].fingerprint, NOW - DAY),
    }
    plan = plan_detail_fetches(games, states, now=NOW)
    assert plan == DetailPlan(never_fetched=(2,), changed=(1,), stale=(3,))
    assert plan.ordered == (2, 1, 3)


def test_stale_budget_takes_oldest_first():
    games = [game(i, earned=1, last_unlock=i) for i in range(1, 6)]
    states = {g.game_id: (g.fingerprint, NOW - (40 + g.game_id) * DAY) for g in games}
    plan = plan_detail_fetches(games, states, now=NOW, policy=PlanPolicy(stale_budget=2))
    assert plan.stale == (5, 4)


def test_full_resync_plans_everything_with_achievements():
    games = [game(1), game(2, total=0), game(3)]
    states = {1: (games[0].fingerprint, NOW)}
    assert plan_detail_fetches(games, states, now=NOW, full=True).ordered == (1, 3)


def test_games_without_achievements_are_skipped():
    assert len(plan_detail_fetches([game(1, total=0)], {}, now=NOW)) == 0


def test_badge_scope_selection():
    games = [
        game(1, last_unlock=NOW - DAY),  # recent
        game(2, last_played=NOW - 60 * DAY),  # old, on device
        game(3, last_unlock=NOW - 60 * DAY),  # old
    ]
    since = NOW - 30 * DAY
    assert badge_game_ids(games, on_device={2}, include_all=False, recent_since=since) == [1, 2]
    assert badge_game_ids(games, on_device=set(), include_all=True, recent_since=None) == [1, 2, 3]
    assert badge_game_ids(games, on_device=set(), include_all=False, recent_since=None) == []


def test_refetch_before_continues_an_interrupted_full_resync():
    games = [game(1, earned=1, last_unlock=10), game(2, earned=1, last_unlock=5)]
    states = {1: (games[0].fingerprint, NOW - 10), 2: (games[1].fingerprint, NOW + 5)}
    plan = plan_detail_fetches(games, states, now=NOW + 10, refetch_before=NOW)
    assert plan.ordered == (1,)  # 2 was already re-fetched after the full re-sync began
