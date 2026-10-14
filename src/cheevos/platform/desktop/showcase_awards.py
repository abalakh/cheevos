"""Event and site awards for the ``showcase`` drill, with the v2 API's event tiers.

Real RA events (titles, tiers and badge images as RA's v2 API returned them in October 2026),
earned by the made-up showcase account, so the Awards screen and the docs show every kind of
badge: tiered events (one showing another tier's image), an event without tiers, and site
badges (a holographic Patreon one, developer contributions).
"""

from __future__ import annotations

from typing import Any

MEDIA = "https://media.retroachievements.org"
# (event ID, title, badge, tiers: (tier, label, points, badge)); see the module docstring.
_EVENTS: tuple[tuple[int, str, str, tuple[tuple[int, str, int, str], ...]], ...] = (
    (
        196,
        "Achievement of the Week 2026",
        "/Images/122637.png",
        (
            (1, "Bronze", 12, "/Images/122638.png"),
            (2, "Silver", 30, "/Images/122639.png"),
            (3, "Gold", 48, "/Images/122640.png"),
            (4, "Champion", 64, "/Images/122641.png"),
        ),
    ),
    (
        164,
        "Achievement of the Week 2024",
        "/Images/104713.png",
        (
            (1, "Bronze", 12, "/Images/104711.png"),
            (2, "Silver", 30, "/Images/104714.png"),
            (3, "Gold", 48, "/Images/104712.png"),
            (4, "Champion", 64, "/Images/104713.png"),
        ),
    ),
    (
        141,
        "Challenge League: The Top 100",
        "/Images/089209.png",
        (
            (1, "30 points", 1, "/Images/089207.png"),
            (2, "60 points", 2, "/Images/089208.png"),
            (3, "90 points", 3, "/Images/089209.png"),
        ),
    ),
    (221, "Find the Pixel: Pokemon Emerald", "/Images/144515.png", ()),
)
# VisibleUserAwards rows after the showcase's game awards: (AwardType, AwardData,
# AwardDataExtra, Title, ConsoleName, ImageIcon, AwardedAt, display_award_tier).
_ROWS: tuple[tuple[str, int, int, str, str, str, str, int | None], ...] = (
    ("Event", 196, 2, "Achievement of the Week 2026", "Events", "/Images/122637.png",
     "2026-04-27T14:53:41+00:00", None),
    ("Event", 164, 4, "Achievement of the Week 2024", "Events", "/Images/104713.png",
     "2025-01-18T20:58:09+00:00", 3),
    ("Event", 141, 2, "Challenge League: The Top 100", "Events", "/Images/089209.png",
     "2024-02-21T04:31:01+00:00", None),
    ("Event", 221, 0, "Find the Pixel: Pokemon Emerald", "Events", "/Images/144515.png",
     "2026-07-21T04:59:59+00:00", None),
    ("Patreon Supporter", 0, 2, "", "", "", "2026-03-10T09:00:00+00:00", None),
    ("Achievement Unlocks Yield", 2, 0, "", "", "", "2025-11-02T16:40:00+00:00", None),
    ("Achievement Points Yield", 1, 0, "", "", "", "2025-08-19T12:00:00+00:00", None),
)  # fmt: skip


def award_rows(first_order: int) -> list[dict[str, Any]]:
    """Return the drill's event and site awards as ``VisibleUserAwards`` rows.

    Args:
        first_order: ``DisplayOrder`` of the first one (they follow the game awards).

    Returns:
        The rows, in the profile's order.
    """
    return [
        {
            "AwardedAt": awarded_at,
            "AwardType": kind,
            "AwardData": data,
            "AwardDataExtra": extra,
            "Title": title,
            "ConsoleID": 101 if console else None,
            "ConsoleName": console or None,
            "Flags": None,
            "ImageIcon": image or None,
            "display_award_tier": display,
            "DisplayOrder": first_order + index,
        }
        for index, (kind, data, extra, title, console, image, awarded_at, display) in enumerate(
            _ROWS
        )
    ]


def events_body() -> dict[str, Any]:
    """Return RA's v2 ``events`` response for the drill's events, with their tiers included.

    Returns:
        The JSON:API document.
    """
    data, included = [], []
    for event_id, title, badge, tiers in _EVENTS:
        links = []
        for tier, label, points, image in tiers:
            award_id = f"{event_id}{tier}"
            links.append({"type": "event-awards", "id": award_id})
            included.append(
                {
                    "type": "event-awards",
                    "id": award_id,
                    "attributes": {
                        "tierIndex": tier,
                        "label": label,
                        "pointsRequired": points,
                        "badgeUrl": MEDIA + image,
                    },
                }
            )
        data.append(
            {
                "type": "events",
                "id": str(event_id),
                "attributes": {"title": title, "badgeUrl": MEDIA + badge},
                "relationships": {"awards": {"data": links}},
            }
        )
    page = {"currentPage": 1, "lastPage": 1, "perPage": 50, "total": len(data)}
    return {"meta": {"page": page}, "data": data, "included": included}


# What each tiered event is worth (its published achievements' points), as RA's v2 API added
# them up in October 2026.
_EVENT_POINTS = {196: 64, 164: 64, 141: 3}


def event_achievements_body() -> dict[str, Any]:
    """Return RA's v2 ``event-achievements`` response: one achievement per event, worth it all.

    Returns:
        The JSON:API document.
    """
    data = [
        {
            "type": "event-achievements",
            "id": str(event_id),
            "attributes": {"achievementPoints": points},
            "relationships": {"event": {"data": {"type": "events", "id": str(event_id)}}},
        }
        for event_id, points in _EVENT_POINTS.items()
    ]
    page = {"currentPage": 1, "lastPage": 1, "perPage": 100, "total": len(data)}
    return {"meta": {"page": page}, "data": data}


def v2_body(path: str) -> dict[str, Any]:
    """Answer a request to RA's v2 API: events, or what they are worth.

    Args:
        path: The request's path, e.g. ``"/v2/events?filter[id]=..."``.

    Returns:
        The JSON:API document.
    """
    return event_achievements_body() if path.startswith("/v2/event-achievements") else events_body()


def image_paths() -> list[str]:
    """Return every image the drill's awards show, for the dev media mirror.

    Returns:
        Paths on the media host (``/Images/...``) and the static host (``/assets/...``).
    """
    paths = {image for row in _ROWS if (image := row[5])}
    paths |= {badge for _id, _title, badge, _tiers in _EVENTS}
    paths |= {tier[3] for _id, _title, _badge, tiers in _EVENTS for tier in tiers}
    paths |= {
        "/assets/images/badge/patreon.png",
        "/assets/images/badge/contribYield-2.png",
        "/assets/images/badge/contribPoints-1.png",
    }
    return sorted(paths)
