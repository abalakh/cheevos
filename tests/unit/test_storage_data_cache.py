import calendar
import json
import time
from pathlib import Path

import pytest

from cheevos.core.models import (
    WARNING_ACHIEVEMENT_ID,
    Achievement,
    AchievementType,
    Award,
    AwardCounts,
    AwardKind,
    GameDetail,
    GameProgress,
    Unlock,
    UnlockWindow,
    UserProfile,
)
from cheevos.core.storage.data_cache import DataCache

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"


def utc(text: str | None) -> int | None:
    if not text:
        return None
    return calendar.timegm(time.strptime(text.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S"))


def game(game_id: int = 519, **overrides) -> GameProgress:
    values = {
        "game_id": game_id,
        "title": "Final Fantasy Tactics Advance",
        "console_id": 5,
        "console_name": "Game Boy Advance",
        "image_icon": "/Images/070805.png",
        "max_possible": 138,
        "earned": 2,
        "earned_hardcore": 2,
        "last_unlock_at": 1_787_398_933,
        "highest_award": None,
        "highest_award_at": None,
        "last_played_at": None,
    }
    values.update(overrides)
    return GameProgress(**values)


def achievement(achievement_id: int, game_id: int = 519, **overrides) -> Achievement:
    values = {
        "achievement_id": achievement_id,
        "game_id": game_id,
        "title": f"Achievement {achievement_id}",
        "description": "Do the thing",
        "points": 5,
        "retro_points": 6,
        "badge_name": str(198000 + achievement_id % 1000),
        "display_order": achievement_id % 100,
        "type": None,
        "num_awarded": 100,
        "num_awarded_hardcore": 50,
        "earned_at": None,
        "earned_hardcore_at": None,
    }
    values.update(overrides)
    return Achievement(**values)


def detail(game_id: int = 519, achievements: tuple[Achievement, ...] = ()) -> GameDetail:
    return GameDetail(
        game_id=game_id,
        title="Final Fantasy Tactics Advance",
        console_name="Game Boy Advance",
        image_icon="/Images/070805.png",
        num_distinct_players=5619,
        num_players_casual=2000,
        num_players_hardcore=3619,
        achievements=achievements,
    )


def detail_from_fixture(game_id: int) -> GameDetail:
    """Convert a recorded GetGameInfoAndUserProgress response (local helper, not the parser)."""
    raw = json.loads((FIXTURES / f"game_{game_id}.json").read_text(encoding="utf-8"))
    rows = sorted(raw["Achievements"].values(), key=lambda r: (r["DisplayOrder"], r["ID"]))
    achievements = tuple(
        Achievement(
            achievement_id=int(r["ID"]),
            game_id=game_id,
            title=r["Title"],
            description=r["Description"],
            points=int(r["Points"]),
            retro_points=int(r["TrueRatio"]),
            badge_name=str(r["BadgeName"]),
            display_order=int(r["DisplayOrder"]),
            type=AchievementType(r["Type"]) if r.get("Type") else None,
            num_awarded=int(r["NumAwarded"]),
            num_awarded_hardcore=int(r["NumAwardedHardcore"]),
            earned_at=utc(r.get("DateEarned")),
            earned_hardcore_at=utc(r.get("DateEarnedHardcore")),
        )
        for r in rows
    )
    return GameDetail(
        game_id=game_id,
        title=raw["Title"],
        console_name=raw["ConsoleName"],
        image_icon=raw["ImageIcon"],
        num_distinct_players=int(raw["NumDistinctPlayers"]),
        num_players_casual=int(raw.get("NumDistinctPlayersCasual") or 0),
        num_players_hardcore=int(raw.get("NumDistinctPlayersHardcore") or 0),
        achievements=achievements,
    )


@pytest.fixture
def cache(tmp_path):
    data_cache = DataCache.open(tmp_path / "data.db", "Balah")
    yield data_cache
    data_cache.close()


def test_meta_set_get_delete(cache):
    assert cache.get_meta("last_sync") is None
    cache.set_meta("last_sync", "123")
    assert cache.get_meta("last_sync") == "123"
    cache.set_meta("last_sync", "456")
    assert cache.get_meta("last_sync") == "456"
    cache.set_meta("last_sync", None)
    assert cache.get_meta("last_sync") is None


def test_username_is_stored_and_same_user_keeps_data(tmp_path):
    path = tmp_path / "data.db"
    first = DataCache.open(path, "Balah")
    first.upsert_games([game()])
    first.close()
    again = DataCache.open(path, "balah")  # usernames are case-insensitive
    assert again.get_meta("username") == "balah"
    assert [g.game_id for g in again.games()] == [519]
    again.close()


def test_switching_username_resets_cache(tmp_path):
    path = tmp_path / "data.db"
    first = DataCache.open(path, "Balah")
    first.upsert_games([game()])
    first.set_meta("last_sync", "1")
    first.close()
    other = DataCache.open(path, "SomeoneElse")
    assert other.games() == []
    assert other.get_meta("last_sync") is None
    assert other.get_meta("username") == "SomeoneElse"
    other.close()


def test_profile_round_trip(cache):
    assert cache.load_profile() is None
    profile = UserProfile(
        username="Balah",
        user_pic="/UserPic/Balah.png",
        motto="",
        member_since=1_591_130_646,
        hardcore_points=7,
        softcore_points=24,
        retro_points=7,
        rank=None,
        total_ranked=166_966,
        rich_presence="Strategizing in Chapter 0 | 💬0/335",
        last_game_id=519,
    )
    cache.save_profile(profile, synced_at=1_800_000_000)
    assert cache.load_profile() == profile
    cache.save_profile(profile, synced_at=1_800_000_100)  # replaces, never duplicates
    assert cache.load_profile() == profile


def test_unreadable_profile_is_ignored(cache):
    cache._db.execute("INSERT INTO profile VALUES ('Balah', 'not json', 1)")
    assert cache.load_profile() is None


def test_games_ordered_by_latest_activity_then_title(cache):
    cache.upsert_games(
        [
            game(1, title="Zelda", last_unlock_at=100),
            game(2, title="aladdin", last_unlock_at=None),
            game(3, title="Metroid", last_unlock_at=None, last_played_at=300),
            game(4, title="Bomberman", last_unlock_at=None),
            game(5, title="Descent", last_unlock_at=200, last_played_at=50),
        ]
    )
    assert [g.game_id for g in cache.games()] == [3, 5, 1, 2, 4]
    assert cache.game(3).last_played_at == 300
    assert cache.game(999) is None


def test_upsert_keeps_last_played_and_detail_state(cache):
    progress = game(highest_award=AwardKind.BEATEN_HARDCORE, highest_award_at=1_700_000_000)
    cache.upsert_games([game(last_played_at=1_800_000_000)])
    cache.save_game_detail(detail(), fingerprint=progress.fingerprint, synced_at=42)
    # The sync engine upserts the merged library: completion fields are authoritative, while a
    # missing last_played_at (game outside the recently-played window) must not erase it.
    cache.upsert_games([progress])
    stored = cache.game(519)
    assert stored.last_played_at == 1_800_000_000
    assert stored.highest_award is AwardKind.BEATEN_HARDCORE
    assert cache.detail_state(519) == (progress.fingerprint, 42)
    assert cache.detail_states() == {519: (progress.fingerprint, 42)}


def test_upsert_clears_revoked_award(cache):
    cache.upsert_games([game(highest_award=AwardKind.MASTERED, highest_award_at=1_700_000_000)])
    cache.upsert_games([game()])
    stored = cache.game(519)
    assert stored.highest_award is None
    assert stored.highest_award_at is None


def test_detail_state_of_unknown_or_unfetched_game(cache):
    assert cache.detail_state(1) == (None, None)
    cache.upsert_games([game(1)])
    assert cache.detail_state(1) == (None, None)
    assert cache.game_detail(1) is None


def test_game_detail_round_trip_from_fixture(cache):
    recorded = detail_from_fixture(519)
    cache.upsert_games([game()])
    cache.save_game_detail(recorded, fingerprint="fp", synced_at=1)
    assert cache.game_detail(519) == recorded
    stored = cache.game_detail(519)
    unlocked = [a for a in stored.achievements if a.unlocked]
    assert [a.achievement_id for a in unlocked] == [177850, 177851]
    assert all(a.hardcore for a in unlocked)
    assert {a.type for a in stored.achievements} == {
        None,
        AchievementType.PROGRESSION,
        AchievementType.MISSABLE,
        AchievementType.WIN_CONDITION,
    }


def test_save_game_detail_replaces_previous_achievements(cache):
    cache.save_game_detail(
        detail(achievements=(achievement(1), achievement(2))), fingerprint="a", synced_at=1
    )
    cache.save_game_detail(detail(achievements=(achievement(3),)), fingerprint="b", synced_at=2)
    stored = cache.game_detail(519)
    assert [a.achievement_id for a in stored.achievements] == [3]
    assert cache.detail_state(519) == ("b", 2)


def test_save_game_detail_creates_missing_game_row(cache):
    achievements = (
        achievement(1, earned_hardcore_at=500),
        achievement(2, earned_at=700),
        achievement(3),
    )
    cache.save_game_detail(detail(achievements=achievements), fingerprint="fp", synced_at=9)
    created = cache.game(519)
    assert (created.max_possible, created.earned, created.earned_hardcore) == (3, 2, 1)
    assert created.last_unlock_at == 700
    assert created.console_id == 0


def test_mixed_modes_and_warning_id_are_stored_as_is(cache):
    achievements = (
        achievement(10, earned_at=1_000, earned_hardcore_at=900, type=AchievementType.MISSABLE),
        achievement(11, earned_at=2_000, type=AchievementType.WIN_CONDITION),
        achievement(WARNING_ACHIEVEMENT_ID, earned_at=3_000),
        achievement(12),
    )
    cache.save_game_detail(detail(achievements=achievements), fingerprint="fp", synced_at=1)
    stored = {a.achievement_id: a for a in cache.game_detail(519).achievements}
    assert stored[10].earned_hardcore_at == 900
    assert stored[10].earned_at == 1_000
    assert stored[10].type is AchievementType.MISSABLE
    assert stored[11].hardcore is False
    assert WARNING_ACHIEVEMENT_ID in stored
    assert not stored[12].unlocked


def test_recent_unlocks_newest_first_with_limit(cache):
    cache.save_game_detail(
        detail(1, achievements=(achievement(1, 1, earned_at=100), achievement(2, 1))),
        fingerprint="a",
        synced_at=1,
    )
    cache.save_game_detail(
        detail(
            2,
            achievements=(
                achievement(3, 2, earned_at=400, earned_hardcore_at=300),
                achievement(4, 2, earned_hardcore_at=200),
            ),
        ),
        fingerprint="b",
        synced_at=1,
    )
    assert [a.achievement_id for a in cache.recent_unlocks(10)] == [3, 4, 1]
    assert [a.achievement_id for a in cache.recent_unlocks(2)] == [3, 4]


def test_awards_round_trip(cache):
    assert cache.awards() == (None, [])
    counts = AwardCounts(mastered=1, completed=0, beaten_hardcore=2, beaten_softcore=0)
    awards = [
        Award(
            1446, "Super Mario Bros.", "NES/Famicom", "/Images/126543.png", AwardKind.MASTERED, 100
        ),
        Award(
            1446,
            "Super Mario Bros.",
            "NES/Famicom",
            "/Images/126543.png",
            AwardKind.BEATEN_HARDCORE,
            50,
        ),
        Award(
            355,
            "Zelda",
            "SNES/Super Famicom",
            "/Images/059119.png",
            AwardKind.BEATEN_HARDCORE,
            None,
            console_id=3,
            display_order=-1,
        ),
    ]
    cache.save_awards(counts, awards)
    stored_counts, stored = cache.awards()
    assert stored_counts == counts
    assert stored == awards
    cache.save_awards(counts, awards[:1])  # replaces the whole set
    assert cache.awards()[1] == awards[:1]


def test_unreadable_award_counts_are_ignored(cache):
    cache.set_meta("award_counts", "{broken")
    assert cache.awards() == (None, [])


def test_unlock_window_round_trip(cache):
    assert cache.unlock_window() is None
    window = UnlockWindow(100, 200, (Unlock(1, 2, 10, True, 150, "Game Boy Advance"),))
    cache.save_unlock_window(window)
    assert cache.unlock_window() == window
    cache.set_meta("unlock_window", "{broken")
    assert cache.unlock_window() is None


def test_first_hardcore_unlock(cache):
    assert cache.first_hardcore_unlock() is None
    recorded = detail_from_fixture(519)
    cache.save_game_detail(recorded, fingerprint="x", synced_at=1)
    earliest = min(a.earned_hardcore_at for a in recorded.achievements if a.earned_hardcore_at)
    assert cache.first_hardcore_unlock() == earliest


def test_unlocked_among(cache):
    recorded = detail_from_fixture(519)
    cache.save_game_detail(recorded, fingerprint="x", synced_at=1)
    unlocked = {a.achievement_id for a in recorded.achievements if a.unlocked}
    locked = {a.achievement_id for a in recorded.achievements if not a.unlocked}
    probe = set(list(locked)[:3]) | unlocked | {999_999_999}
    assert cache.unlocked_among(probe) == unlocked
    assert cache.unlocked_among([]) == set()


def test_achievement_games(cache):
    cache.save_game_detail(detail_from_fixture(519), fingerprint="x", synced_at=1)
    cache.save_game_detail(detail_from_fixture(3830), fingerprint="x", synced_at=1)
    assert cache.achievement_games([177852, 522844, 999_999_999]) == {177852: 519, 522844: 3830}
    many = [*range(1, 1200), 522844]  # more IDs than one query takes
    assert cache.achievement_games(many) == {522844: 3830}
    assert cache.achievement_games([]) == {}
