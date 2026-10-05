from cheevos.core.models import Achievement, AchievementType, AwardKind, GameProgress
from cheevos.ui.screens import game_detail, games


def achievement(aid, *, points=5, unlocked=False, awarded=10, type_=None):
    return Achievement(
        achievement_id=aid,
        game_id=1,
        title=f"A{aid}",
        description="",
        points=points,
        retro_points=points,
        badge_name=str(aid),
        display_order=aid,
        type=type_,
        num_awarded=awarded,
        num_awarded_hardcore=0,
        earned_at=100 if unlocked else None,
        earned_hardcore_at=None,
    )


def game(gid, title, console, earned, total, award=None):
    return GameProgress(gid, title, 1, console, "", total, earned, 0, None, award, None)


def test_achievement_sorts():
    items = [
        achievement(1, points=1, awarded=50),
        achievement(2, points=10, unlocked=True, awarded=5),
        achievement(3, points=5, awarded=20),
    ]

    def ids(xs):
        return [a.achievement_id for a in xs]

    assert ids(game_detail._sorted(items, "order", 100)) == [1, 2, 3]
    assert ids(game_detail._sorted(items, "unlocked", 100)) == [2, 1, 3]
    assert ids(game_detail._sorted(items, "locked", 100)) == [1, 3, 2]
    assert ids(game_detail._sorted(items, "points", 100)) == [2, 3, 1]
    assert ids(game_detail._sorted(items, "rarity", 100)) == [2, 3, 1]


def test_achievement_filters():
    missable = achievement(1, type_=AchievementType.MISSABLE)
    win = achievement(2, type_=AchievementType.WIN_CONDITION, unlocked=True)
    plain = achievement(3)

    def pick(key):
        return [a.achievement_id for a in (missable, win, plain) if game_detail.FILTERS[key](a)]

    assert pick("all") == [1, 2, 3]
    assert pick("locked") == [1, 3]
    assert pick("unlocked") == [2]
    assert pick("missable") == [1]
    assert pick("key") == [2]


def test_game_sorts():
    library = [
        game(1, "zelda", "SNES", 6, 109),
        game(2, "Aladdin", "Genesis", 0, 21),
        game(3, "Metroid", "NES", 25, 25, AwardKind.MASTERED),
    ]

    def titles(xs):
        return [g.title for g in xs]

    assert titles(games._sorted(library, "recent")) == ["zelda", "Aladdin", "Metroid"]
    assert titles(games._sorted(library, "title")) == ["Aladdin", "Metroid", "zelda"]
    assert titles(games._sorted(library, "console")) == ["Aladdin", "Metroid", "zelda"]
    assert titles(games._sorted(library, "completion")) == ["Metroid", "zelda", "Aladdin"]
