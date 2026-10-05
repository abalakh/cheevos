from cheevos.core.models import Award, AwardKind, UserProfile
from cheevos.ui.screens.awards import _View, arrange, highest_per_game
from cheevos.ui.screens.profile import rank_text


def award(game_id, kind, *, title="", at=0, order=0, console="NES"):
    return Award(game_id, title or f"Game {game_id}", console, "", kind, at, display_order=order)


def test_each_game_keeps_its_highest_award():
    awards = [
        award(1, AwardKind.BEATEN_HARDCORE),
        award(1, AwardKind.MASTERED),
        award(2, AwardKind.BEATEN_SOFTCORE),
        award(2, AwardKind.COMPLETED),
        award(3, AwardKind.BEATEN_HARDCORE),
    ]
    best = highest_per_game(awards)
    assert [(a.game_id, a.kind) for a in best] == [
        (1, AwardKind.MASTERED),
        (2, AwardKind.COMPLETED),
        (3, AwardKind.BEATEN_HARDCORE),
    ]


def test_arrange_filters_and_sorts():
    awards = [
        award(1, AwardKind.MASTERED, title="b", at=10, order=2, console="SNES"),
        award(2, AwardKind.BEATEN_HARDCORE, title="a", at=30, order=1, console="NES"),
        award(3, AwardKind.COMPLETED, title="c", at=20, order=0, console="NES"),
    ]
    ids = [a.game_id for a in arrange(awards, _View())]
    assert ids == [2, 3, 1]  # newest first
    assert [a.game_id for a in arrange(awards, _View(sort="site"))] == [3, 2, 1]
    assert [a.game_id for a in arrange(awards, _View(sort="title"))] == [2, 1, 3]
    assert [a.game_id for a in arrange(awards, _View(sort="console"))] == [2, 3, 1]
    assert [a.game_id for a in arrange(awards, _View(filter="mastery"))] == [3, 1]
    assert [a.game_id for a in arrange(awards, _View(filter="beaten"))] == [2]


def profile(rank, total):
    return UserProfile("Balah", "", "", None, 0, 0, 0, rank, total, "", None)


def test_rank_text_like_ra():
    assert rank_text(profile(None, 100)) == "Unranked"
    assert rank_text(profile(42, 80_000)) == "#42 of 80,000"
    assert rank_text(profile(1_234, 80_000)).startswith("#1,234 of 80,000 · top ")
