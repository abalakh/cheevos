import json
from calendar import timegm
from pathlib import Path

import pytest

from cheevos.core.errors import ApiPayloadError
from cheevos.core.models import AwardKind, AwardType, EventInfo, EventTier
from cheevos.core.ra_client import parse_awards as parse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
MEDIA = "https://media.retroachievements.org"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def utc(*parts):
    return timegm((*parts, 0, 0, 0))


def test_awards_from_empty_fixture():
    counts, awards = parse.parse_awards(load("user_awards"))
    assert (counts.mastered, counts.completed, counts.beaten_hardcore, counts.beaten_softcore) == (
        0,
        0,
        0,
        0,
    )
    assert awards == []


def test_awards_of_every_type_keep_ras_order():
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
                {"AwardType": "Patreon Supporter", "AwardData": 0, "AwardDataExtra": 2},
                {"AwardType": "Game Beaten", "AwardData": 0, "AwardDataExtra": 1},  # no game
                {"AwardType": "Event", "AwardData": 1, "AwardDataExtra": 3, "Title": "AotW"},
                {"AwardType": "Site Event", "AwardData": 9, "display_award_tier": "2"},
                {"AwardType": "Referrals", "AwardData": 5},  # unknown: skipped
                {"AwardType": "Media Contribution", "AwardData": 0, "AwardDataExtra": 1},
            ],
        }
    )
    assert (counts.mastered, counts.completed) == (1, 1)
    assert [(a.type, a.data, a.extra, a.position) for a in awards] == [
        (AwardType.MASTERY, 1, 1, 0),
        (AwardType.MASTERY, 2, 0, 1),
        (AwardType.GAME_BEATEN, 3, 1, 2),
        (AwardType.GAME_BEATEN, 4, 0, 3),
        (AwardType.PATREON, 0, 2, 4),
        (AwardType.EVENT, 1, 3, 6),
        (AwardType.SITE_EVENT, 9, 0, 7),
        (AwardType.MEDIA, 0, 1, 9),
    ]
    assert [a.kind for a in awards[:4]] == [
        AwardKind.MASTERED,
        AwardKind.COMPLETED,
        AwardKind.BEATEN_HARDCORE,
        AwardKind.BEATEN_SOFTCORE,
    ]
    assert awards[0].title == "A"
    assert awards[0].awarded_at == utc(2024, 2, 10, 16, 41, 22)
    assert (awards[0].console_id, awards[0].display_order) == (5, 3)
    assert (awards[1].console_id, awards[1].display_order) == (0, 0)
    assert [a.display_tier for a in awards[-3:]] == [None, 2, None]


def test_game_and_event_ids_never_collide():
    _counts, awards = parse.parse_awards(
        {
            "VisibleUserAwards": [
                {"AwardType": "Mastery/Completion", "AwardData": 196, "AwardDataExtra": 1},
                {"AwardType": "Event", "AwardData": 196, "AwardDataExtra": 1},
            ]
        }
    )
    game, event = awards
    assert game.game_id == 196
    assert event.game_id is None  # an event ID is never a game ID
    assert event.kind is None
    assert game.key != event.key


@pytest.mark.parametrize(
    "payload", [[], {"VisibleUserAwards": {"a": 1}}, {"VisibleUserAwards": [1]}]
)
def test_awards_reject_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_awards(payload)


def events_document():
    return {
        "meta": {"page": {"currentPage": 1, "lastPage": 2}},
        "data": [
            {
                "type": "events",
                "id": "196",
                "attributes": {
                    "title": "Achievement of the Week 2026",
                    "badgeUrl": f"{MEDIA}/Images/122637.png",
                },
                "relationships": {
                    "awards": {
                        "data": [
                            {"type": "event-awards", "id": "113"},
                            {"type": "event-awards", "id": "112"},
                        ]
                    }
                },
            },
            {
                "type": "events",
                "id": "221",
                "attributes": {"title": "Find the Pixel", "badgeUrl": "elsewhere.png"},
                "relationships": {"awards": {"data": []}},
            },
            {"type": "events", "id": "0", "attributes": {}},
        ],
        "included": [
            {
                "type": "event-awards",
                "id": "112",
                "attributes": {
                    "tierIndex": 1,
                    "label": "Bronze",
                    "pointsRequired": 12,
                    "badgeUrl": f"{MEDIA}/Images/122638.png",
                },
            },
            {
                "type": "event-awards",
                "id": "113",
                "attributes": {
                    "tierIndex": "2",
                    "label": "Silver",
                    "pointsRequired": 30,
                    "badgeUrl": f"{MEDIA}/Images/122639.png",
                },
            },
            {"type": "users", "id": "1", "attributes": {}},
        ],
    }


def test_events_with_their_tiers():
    events, last_page = parse.parse_events(events_document())
    assert last_page == 2
    assert events == [
        EventInfo(
            196,
            "Achievement of the Week 2026",
            "/Images/122637.png",
            (
                EventTier(1, "Bronze", 12, "/Images/122638.png"),
                EventTier(2, "Silver", 30, "/Images/122639.png"),
            ),
        ),
        EventInfo(221, "Find the Pixel", ""),  # not a media-host URL: no image
    ]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"data": {}},
        {"data": [], "included": {"a": 1}},
        {"data": [{"id": "1", "relationships": {"awards": {"data": "x"}}}]},
    ],
)
def test_events_reject_bad_payloads(payload):
    with pytest.raises(ApiPayloadError):
        parse.parse_events(payload)


def test_event_points_add_up_per_event():
    def row(event_id, points):
        link = {"data": {"type": "events", "id": str(event_id)}} if event_id else {"data": None}
        return {"attributes": {"achievementPoints": points}, "relationships": {"event": link}}

    document = {
        "meta": {"page": {"lastPage": 3}},
        "data": [row(196, 1), row(196, "2"), row(141, 3), row(None, 5)],
    }
    assert parse.parse_event_points(document) == ({196: 3, 141: 3}, 3)
    assert parse.parse_event_points({"data": []}) == ({}, 1)
    with pytest.raises(ApiPayloadError):
        parse.parse_event_points({"data": {}})


def test_media_path_keeps_only_media_host_urls():
    assert parse.media_path(f"{MEDIA}/Badge/1.png") == "/Badge/1.png"
    assert parse.media_path("https://static.retroachievements.org/x.png") == ""
    assert parse.media_path(None) == ""
