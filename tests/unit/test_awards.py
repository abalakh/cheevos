import pytest

from cheevos.core.awards import (
    EventBadge,
    award_image,
    event_badge,
    gallery,
    gallery_counts,
    group,
    site_image,
    site_order,
    threshold,
)
from cheevos.core.models import Award, AwardGroup, AwardType, EventInfo, EventTier

T = AwardType


def award(kind, data=1, extra=0, *, position=0, title="", console="", image="", tier=None):
    return Award(
        kind, data, extra, title, console, image, None, position=position, display_tier=tier
    )


@pytest.mark.parametrize(
    ("made", "expected"),
    [
        (award(T.MASTERY, extra=1, console="NES/Famicom"), AwardGroup.GAME),
        (award(T.MASTERY, extra=0, console="SNES"), AwardGroup.GAME),  # completed
        (award(T.MASTERY, extra=1, console="Events"), AwardGroup.EVENT),  # an old event game
        (award(T.EVENT, extra=3), AwardGroup.EVENT),
        (award(T.SITE_EVENT), AwardGroup.SITE),
        (award(T.PLAYTEST, image="/Images/1.png"), AwardGroup.SITE),
        (award(T.PLAYTEST), None),  # RA draws nothing without an image
        (award(T.UNLOCKS_YIELD), AwardGroup.SITE),
        (award(T.POINTS_YIELD), AwardGroup.SITE),
        (award(T.PATREON), AwardGroup.SITE),
        (award(T.LEGEND), AwardGroup.SITE),
        (award(T.MEDIA), AwardGroup.SITE),
        (award(T.GAME_BEATEN, extra=1), None),  # beaten: Games and Profile only
        (award(T.GAME_BEATEN, extra=0), None),
    ],
)
def test_groups_follow_ras_profile(made, expected):
    assert group(made) is expected


def test_gallery_leaves_out_beaten_and_keeps_events_apart_from_games():
    awards = [
        award(T.GAME_BEATEN, 196, 1, position=0),
        award(T.MASTERY, 196, 1, position=1),
        award(T.EVENT, 196, 1, position=2),  # the same ID as the game: a different award
        award(T.EVENT, 196, 2, position=3),  # another tier of that event: kept too
        award(T.MASTERY, 7, 0, position=5),  # completed...
        award(T.MASTERY, 7, 1, position=4),  # ...and mastered: the mastery wins
        award(T.MASTERY, 8, 0, position=6),
    ]
    shown = gallery(reversed(awards))
    assert [(a.type, a.data, a.extra) for a in shown] == [
        (T.MASTERY, 196, 1),
        (T.EVENT, 196, 1),
        (T.EVENT, 196, 2),
        (T.MASTERY, 7, 1),
        (T.MASTERY, 8, 0),
    ]
    assert len({a.key for a in shown}) == len(shown)


def test_site_order_groups_galleries_by_their_first_award():
    awards = [
        award(T.EVENT, 1, position=0),
        award(T.MASTERY, 10, 1, position=1),
        award(T.PATREON, position=2),
        award(T.EVENT, 2, position=3),
        award(T.MASTERY, 11, 1, position=4),
        award(T.MASTERY, 12, 1, position=5, console="Events"),  # an old event game
    ]
    ordered = site_order(list(reversed(awards)))
    assert [a.position for a in ordered] == [0, 3, 5, 1, 4, 2]


def test_gallery_counts_count_visible_galleries():
    awards = [
        award(T.MASTERY, 1, 1),
        award(T.MASTERY, 2, 0),
        award(T.MASTERY, 3, 1, console="Events"),
        award(T.EVENT, 4),
        award(T.GAME_BEATEN, 5, 1),
        award(T.LEGEND),
        award(T.PLAYTEST),  # no image: not shown
    ]
    counts = gallery_counts(awards)
    assert (counts.mastered, counts.completed, counts.events, counts.site) == (1, 1, 2, 1)
    assert counts.total == 5


AOTW = EventInfo(
    196,
    "Achievement of the Week 2026",
    "/Images/122637.png",
    (
        EventTier(1, "Bronze", 12, "/Images/122638.png"),
        EventTier(2, "Silver", 30, "/Images/122639.png"),
        EventTier(4, "Champion", 64, "/Images/122641.png"),
    ),
    64,
)


def aotw(extra, tier=None):
    return award(
        T.EVENT,
        196,
        extra,
        title="Achievement of the Week 2026",
        image="/Images/122637.png",
        tier=tier,
    )


def test_event_tier_reads_like_ras_tooltip():
    assert event_badge(aotw(2), AOTW) == EventBadge(
        "Achievement of the Week 2026 - Silver", 30, "/Images/122639.png", known=True
    )


def test_event_image_follows_the_shown_tier_but_text_the_earned_one():
    badge = event_badge(aotw(1, tier=4), AOTW)
    assert badge.image == "/Images/122641.png"  # the Champion badge the player shows
    assert (badge.title, badge.points) == ("Achievement of the Week 2026 - Bronze", 12)


def test_a_tier_worth_the_whole_event_was_for_completing_it():
    badge = event_badge(aotw(4), AOTW)
    assert badge == EventBadge(
        "Achievement of the Week 2026", None, "/Images/122641.png", known=True
    )


def test_tier_points_are_kept_when_the_events_total_is_unknown():
    badge = event_badge(aotw(4), EventInfo(196, AOTW.title, AOTW.image, AOTW.tiers))
    assert (badge.title, badge.points) == ("Achievement of the Week 2026 - Champion", 64)


def test_event_without_tiers_and_unknown_events():
    plain = award(T.EVENT, 221, 0, title="Find the Pixel", image="/Images/144515.png")
    info = EventInfo(221, "Find the Pixel", "/Images/144515.png")
    assert event_badge(plain, info) == EventBadge(
        "Find the Pixel", None, "/Images/144515.png", known=True
    )
    # Not fetched yet (or offline): RA's own title and image, and nothing invented.
    assert event_badge(aotw(2), None) == EventBadge(
        "Achievement of the Week 2026", None, "/Images/122637.png", known=False
    )
    # A tier the API doesn't list (a legacy tier number) isn't a hardcore flag either.
    assert event_badge(aotw(3), AOTW).points is None


@pytest.mark.parametrize(
    ("label", "title", "expected"),
    [
        ("Challenge League 2024 - Gold", "Challenge League 2024", "Challenge League 2024 - Gold"),
        ("Gold", "Challenge League 2024: Ticket", "Challenge League 2024: Ticket - Gold"),
        ("RetroAchievemas 2024", "RetroAchievemas 2024", "RetroAchievemas 2024"),
        ("Back to School", "AotW 2025 - Back to School", "AotW 2025 - Back to School"),
        ("AotW 2025: Silver", "AotW 2025", "AotW 2025 - Silver"),
    ],
)
def test_tier_labels_drop_the_event_title_like_ra(label, title, expected):
    info = EventInfo(5, title, "", (EventTier(1, label, 1, ""),), 10)
    made = award(T.EVENT, 5, 1, title=title)
    assert event_badge(made, info).title == expected


@pytest.mark.parametrize(
    ("made", "expected"),
    [
        (award(T.UNLOCKS_YIELD, 2), 500),
        (award(T.POINTS_YIELD, 0), 1_000),
        (award(T.MEDIA, 0, 3), 300),  # media contributions: the tier is AwardDataExtra
        (award(T.UNLOCKS_YIELD, 99), None),
        (award(T.PATREON), None),
    ],
)
def test_contribution_thresholds(made, expected):
    assert threshold(made) == expected


def test_site_art_and_award_images():
    assert site_image(award(T.UNLOCKS_YIELD, 2)) == "/assets/images/badge/contribYield-2.png"
    assert site_image(award(T.POINTS_YIELD, 1)) == "/assets/images/badge/contribPoints-1.png"
    assert site_image(award(T.MEDIA, 0, 1, tier=3)) == "/assets/images/badge/mediaContrib-3.png"
    assert site_image(award(T.PATREON)) == "/assets/images/badge/patreon.png"
    assert site_image(award(T.LEGEND)) == "/assets/images/badge/legend.png"
    assert site_image(award(T.PLAYTEST, image="/Images/9.png")) == "/Images/9.png"
    game = award(T.MASTERY, 196, 1, image="/Images/070805.png")
    assert award_image(game) == ("icon/196", "/Images/070805.png")  # the game's own icon
    assert award_image(aotw(2), AOTW) == ("award/Images/122639", "/Images/122639.png")
    assert award_image(award(T.LEGEND)) == (
        "award/assets/images/badge/legend",
        "/assets/images/badge/legend.png",
    )
