import json
from calendar import timegm
from pathlib import Path

import pytest

from cheevos.core.errors import ApiPayloadError
from cheevos.core.models import WARNING_ACHIEVEMENT_ID, AchievementType, AwardKind
from cheevos.core.ra_client import parse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def utc(*parts):
    return timegm((*parts, 0, 0, 0))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-21 17:02:50", utc(2026, 8, 21, 17, 2, 50)),
        ("2026-08-22T11:42:13+00:00", utc(2026, 8, 22, 11, 42, 13)),
        ("2026-08-22T11:42:13Z", utc(2026, 8, 22, 11, 42, 13)),
        ("2026-08-22T13:42:13+02:00", utc(2026, 8, 22, 11, 42, 13)),
        (None, None),
        ("", None),
        ("   ", None),
        ("not a date", None),
        (12345, None),
    ],
)
def test_parse_time(value, expected):
    assert parse.parse_time(value) == expected


def test_user_summary_from_fixture():
    profile = parse.parse_user_summary(load("user_summary"))
    assert profile.username == "Balah"
    assert profile.user_pic == "/UserPic/Balah.png"
    assert (profile.hardcore_points, profile.softcore_points, profile.retro_points) == (7, 24, 7)
    assert profile.rank is None
    assert profile.total_ranked == 166966
    assert profile.last_game_id == 554
    assert profile.member_since == utc(2020, 6, 2, 20, 44, 6)
    assert profile.rich_presence.startswith("Strategizing in Chapter 0")
    assert profile.rich_presence_at == utc(2026, 10, 4, 12, 10, 0)
    assert profile.last_game_title == "Fire Emblem: The Blazing Blade"
    assert profile.last_game_console == "Game Boy Advance"
    assert profile.last_game_icon == "/Images/042758.png"


def test_user_profile_endpoint_parses_without_rank():
    profile = parse.parse_user_summary(load("user_profile"))
    assert profile.username == "Balah"
    assert profile.rank is None
    assert profile.total_ranked is None


def test_user_summary_defaults_and_string_numbers():
    profile = parse.parse_user_summary({"User": "x", "TotalPoints": "15", "Rank": "42"})
    assert profile.user_pic == "/UserPic/x.png"
    assert profile.hardcore_points == 15
    assert profile.rank == 42
    assert profile.motto == ""
    assert profile.member_since is None


@pytest.mark.parametrize("payload", [[], "x", None, {"TotalPoints": 1}])
def test_user_summary_rejects_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_user_summary(payload)


def test_completion_progress_from_fixture():
    games, total = parse.parse_completion_progress(load("completion_progress"))
    assert total == 7
    assert len(games) == 7
    ffta = games[0]
    assert (ffta.game_id, ffta.title) == (519, "Final Fantasy Tactics Advance")
    assert (ffta.console_id, ffta.console_name) == (5, "Game Boy Advance")
    assert (ffta.max_possible, ffta.earned, ffta.earned_hardcore) == (138, 2, 2)
    assert ffta.last_unlock_at == utc(2026, 8, 22, 11, 42, 13)
    assert ffta.highest_award is None
    assert ffta.last_played_at is None
    assert ffta.fingerprint == f"138:2:2:{utc(2026, 8, 22, 11, 42, 13)}:"


def test_completion_progress_award_kinds_and_strings():
    games, total = parse.parse_completion_progress(
        {
            "Results": [
                {"GameID": "10", "HighestAwardKind": "mastered", "NumAwarded": "5"},
                {"GameID": 11, "HighestAwardKind": "something-new"},
            ]
        }
    )
    assert total == 2  # defaults to the page length when Total is missing
    assert games[0].game_id == 10
    assert games[0].earned == 5
    assert games[0].highest_award is AwardKind.MASTERED
    assert games[1].highest_award is None


@pytest.mark.parametrize("payload", [[], {"Results": {"a": 1}}, {"Results": [1]}])
def test_completion_progress_rejects_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_completion_progress(payload)


def test_recently_played_from_fixture():
    games = parse.parse_recently_played(load("recently_played"))
    assert len(games) == 12
    fire_emblem = games[0]
    assert (fire_emblem.game_id, fire_emblem.max_possible, fire_emblem.earned) == (554, 87, 0)
    assert fire_emblem.last_played_at == utc(2026, 10, 4, 12, 10, 0)
    assert fire_emblem.last_unlock_at is None
    zelda = next(game for game in games if game.game_id == 355)
    assert (zelda.earned, zelda.earned_hardcore) == (6, 0)


def test_recently_played_falls_back_to_achievements_total():
    games = parse.parse_recently_played([{"GameID": 1, "AchievementsTotal": "21"}])
    assert games[0].max_possible == 21


@pytest.mark.parametrize("payload", [{}, [1], None])
def test_recently_played_rejects_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_recently_played(payload)


def test_game_detail_from_fixture():
    detail = parse.parse_game_detail(load("game_519"))
    assert (detail.game_id, detail.title) == (519, "Final Fantasy Tactics Advance")
    assert detail.console_name == "Game Boy Advance"
    assert detail.num_distinct_players == 5619
    assert len(detail.achievements) == 138
    orders = [(a.display_order, a.achievement_id) for a in detail.achievements]
    assert orders == sorted(orders)
    by_id = {a.achievement_id: a for a in detail.achievements}
    welcome, spice = by_id[177850], by_id[177851]
    assert welcome.title == "Welcome to Ivalice!"
    assert welcome.badge_name == "198102"
    assert welcome.type is AchievementType.PROGRESSION
    assert welcome.earned_hardcore_at == utc(2026, 8, 21, 17, 2, 50)
    assert welcome.hardcore
    assert welcome.unlocked
    assert spice.earned_hardcore_at == utc(2026, 8, 22, 11, 42, 13)
    assert spice.unlocked_at == spice.earned_hardcore_at
    assert sum(a.unlocked for a in detail.achievements) == 2
    kinds = [a.type for a in detail.achievements]
    assert kinds.count(AchievementType.MISSABLE) == 23
    assert kinds.count(AchievementType.WIN_CONDITION) == 1
    assert kinds.count(None) == 90


def test_game_detail_tolerates_lists_strings_and_drops_warning_achievement():
    detail = parse.parse_game_detail(
        {
            "ID": "7",
            "Achievements": [
                {"ID": "3", "DisplayOrder": "2", "Points": "5", "Type": "weird"},
                {"ID": WARNING_ACHIEVEMENT_ID, "DisplayOrder": 0},
                {
                    "ID": 1,
                    "DisplayOrder": 2,
                    "Type": "missable",
                    "DateEarned": "2024-01-01 00:00:00",
                },
            ],
        }
    )
    assert [a.achievement_id for a in detail.achievements] == [1, 3]
    assert detail.achievements[1].points == 5
    assert detail.achievements[1].type is None
    first = detail.achievements[0]
    assert first.type is AchievementType.MISSABLE
    assert first.unlocked
    assert not first.hardcore


def test_game_detail_without_achievements():
    detail = parse.parse_game_detail({"ID": 9, "Achievements": []})
    assert detail.achievements == ()


@pytest.mark.parametrize(
    "payload",
    [[], {"Title": "no id"}, {"ID": 1, "Achievements": "x"}, {"ID": 1, "Achievements": [1]}],
)
def test_game_detail_rejects_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_game_detail(payload)


def test_awards_from_empty_fixture():
    counts, awards = parse.parse_awards(load("user_awards"))
    assert (counts.mastered, counts.completed, counts.beaten_hardcore, counts.beaten_softcore) == (
        0,
        0,
        0,
        0,
    )
    assert awards == []


def test_awards_kinds_and_filtering():
    counts, awards = parse.parse_awards(
        {
            "MasteryAwardsCount": 1,
            "CompletionAwardsCount": "1",
            "BeatenHardcoreAwardsCount": 1,
            "BeatenSoftcoreAwardsCount": 1,
            "VisibleUserAwards": [
                {
                    "AwardType": "Mastery/Completion",
                    "AwardData": 1,
                    "AwardDataExtra": 1,
                    "Title": "A",
                    "AwardedAt": "2024-02-10T16:41:22+00:00",
                    "ConsoleID": 5,
                    "DisplayOrder": "3",
                },
                {"AwardType": "Mastery/Completion", "AwardData": "2", "AwardDataExtra": 0},
                {"AwardType": "Game Beaten", "AwardData": 3, "AwardDataExtra": 1},
                {"AwardType": "Game Beaten", "AwardData": 4, "AwardDataExtra": "0"},
                {"AwardType": "Patreon Supporter", "AwardData": 0},
                {"AwardType": "Game Beaten", "AwardData": 0, "AwardDataExtra": 1},
            ],
        }
    )
    assert (counts.mastered, counts.completed) == (1, 1)
    assert [(a.game_id, a.kind) for a in awards] == [
        (1, AwardKind.MASTERED),
        (2, AwardKind.COMPLETED),
        (3, AwardKind.BEATEN_HARDCORE),
        (4, AwardKind.BEATEN_SOFTCORE),
    ]
    assert awards[0].title == "A"
    assert awards[0].awarded_at == utc(2024, 2, 10, 16, 41, 22)
    assert (awards[0].console_id, awards[0].display_order) == (5, 3)
    assert (awards[1].console_id, awards[1].display_order) == (0, 0)


@pytest.mark.parametrize(
    "payload", [[], {"VisibleUserAwards": {"a": 1}}, {"VisibleUserAwards": [1]}]
)
def test_awards_reject_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_awards(payload)


def test_unlocks_between():
    unlocks = parse.parse_unlocks(
        [
            {
                "Date": "2026-10-01 22:41:48",
                "HardcoreMode": 1,
                "AchievementID": 175333,
                "Points": "10",
                "GameID": 3164,
                "ConsoleName": "PlayStation Portable",
            },
            {"Date": "2026-10-02 08:00:00", "HardcoreMode": False, "AchievementID": 7},
            {"Date": "", "AchievementID": 8},  # no date: skipped
            {"Date": "2026-10-02 08:00:00", "AchievementID": 0},  # no ID: skipped
        ]
    )
    assert [(u.achievement_id, u.hardcore, u.points) for u in unlocks] == [
        (175333, True, 10),
        (7, False, 0),
    ]
    assert unlocks[0].unlocked_at == utc(2026, 10, 1, 22, 41, 48)
    assert unlocks[0].console_name == "PlayStation Portable"


def test_unlocks_between_rejects_non_lists():
    with pytest.raises(ApiPayloadError):
        parse.parse_unlocks({"Achievements": []})
