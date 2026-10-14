from collections.abc import Iterator
from types import SimpleNamespace
from typing import ClassVar, cast

import pytest

from cheevos.core.awards import GalleryCounts, gallery
from cheevos.core.models import Award, AwardType, EventInfo, EventTier, UserProfile
from cheevos.core.settings import Settings
from cheevos.ui import format as fmt
from cheevos.ui import strings
from cheevos.ui.context import AppContext
from cheevos.ui.pyui.image_frames import Frame
from cheevos.ui.pyui.primitives import Button
from cheevos.ui.pyui.views import Choice, Layout
from cheevos.ui.screens import awards as screen
from cheevos.ui.screens.award_text import describe
from cheevos.ui.screens.awards import _item, _options, _View, arrange, next_view
from cheevos.ui.screens.home import awards_summary
from cheevos.ui.screens.profile import rank_text

T = AwardType
DAY = 86_400


def award(kind, data, extra=0, *, title="", at=0, position=0, console="", image="", tier=None):
    return Award(kind, data, extra, title, console, image, at, 0, 0, position, tier)


EVENTS = {
    196: EventInfo(
        196,
        "Achievement of the Week 2026",
        "/Images/122637.png",
        (EventTier(1, "Bronze", 12, "/Images/b.png"), EventTier(4, "Champion", 64, "/c.png")),
        64,
    ),
    221: EventInfo(221, "Find the Pixel", "/Images/f.png"),
}
AWARDS = [
    award(T.MASTERY, 196, 1, title="Banjo", at=50 * DAY, position=0, console="N64"),
    award(T.EVENT, 196, 1, title="Achievement of the Week 2026", at=90 * DAY, position=1),
    award(T.MASTERY, 2, 0, title="Aladdin", at=10 * DAY, position=2, console="Genesis"),
    award(T.GAME_BEATEN, 2, 1, title="Aladdin", at=11 * DAY, position=3, console="Genesis"),
    award(T.PATREON, 0, 2, at=70 * DAY, position=4),
    award(T.EVENT, 221, 0, title="Find the Pixel", at=30 * DAY, position=5),
    award(T.MASTERY, 3, 1, title="Contra", at=20 * DAY, position=6, console="NES"),
]


def shown(view=None):
    pairs = [(a, describe(a, EVENTS)) for a in gallery(AWARDS)]
    return [(a.type, a.data) for a, _text in arrange(pairs, view or _View())]


def test_every_view_shows_the_same_awards_newest_first():
    newest = [(T.EVENT, 196), (T.PATREON, 0), (T.MASTERY, 196), (T.EVENT, 221)]
    newest += [(T.MASTERY, 3), (T.MASTERY, 2)]
    for layout in ("carousel", "grid", "list"):
        assert shown(_View(layout=layout)) == newest  # beaten awards are left out


@pytest.mark.parametrize(
    ("filter_key", "expected"),
    [
        ("game", [(T.MASTERY, 196), (T.MASTERY, 3), (T.MASTERY, 2)]),
        ("mastered", [(T.MASTERY, 196), (T.MASTERY, 3)]),
        ("completed", [(T.MASTERY, 2)]),
        ("event", [(T.EVENT, 196), (T.EVENT, 221)]),
        ("site", [(T.PATREON, 0)]),
    ],
)
def test_filters_keep_the_three_galleries_apart(filter_key, expected):
    assert shown(_View(filter=filter_key)) == expected


def test_sorts():
    assert shown(_View(sort="site")) == [
        (T.MASTERY, 196),
        (T.MASTERY, 2),
        (T.MASTERY, 3),
        (T.EVENT, 196),
        (T.EVENT, 221),
        (T.PATREON, 0),
    ]
    # Titles as shown: the event's tier, the site badge's own name.
    assert shown(_View(sort="title")) == [
        (T.EVENT, 196),  # "Achievement of the Week 2026 - Bronze"
        (T.MASTERY, 2),
        (T.MASTERY, 196),
        (T.MASTERY, 3),
        (T.EVENT, 221),
        (T.PATREON, 0),
    ]
    # Console sorting is for game awards: they come first, the other badges by title after.
    assert shown(_View(sort="console")) == [
        (T.MASTERY, 2),
        (T.MASTERY, 196),
        (T.MASTERY, 3),
        (T.EVENT, 196),
        (T.EVENT, 221),
        (T.PATREON, 0),
    ]
    assert shown(_View(filter="event", sort="console")) == shown(_View(filter="event"))


def text(made):
    return describe(made, EVENTS)


def test_game_awards_read_like_the_profile():
    mastered, completed = text(AWARDS[0]), text(AWARDS[2])
    assert (mastered.title, mastered.description, mastered.frame) == (
        "Banjo",
        "Mastered",
        Frame.GOLD,
    )
    assert (completed.description, completed.frame) == ("Completed", None)
    assert mastered.date == fmt.local_date(50 * DAY)
    assert mastered.image == ("icon/196", "")
    legacy = text(award(T.MASTERY, 9, 0, title="AotW 2017", console="Events"))
    assert (legacy.description, legacy.frame) == ("Completed", None)  # RA: plain unless mastered


def test_event_awards_read_like_ras_tooltips():
    tiered = text(AWARDS[1])
    assert tiered.title == "Achievement of the Week 2026 - Bronze"
    assert tiered.description == "Awarded for earning at least 12 points"
    assert tiered.frame is Frame.GOLD
    assert tiered.image == ("award/Images/b", "/Images/b.png")
    assert tiered.date == fmt.local_date(90 * DAY)
    champion = text(award(T.EVENT, 196, 4, title="Achievement of the Week 2026"))
    assert (champion.title, champion.description) == (
        "Achievement of the Week 2026",
        "Awarded for completing this event",
    )
    assert text(AWARDS[5]).description == "Awarded for completing this event"
    one = EventInfo(5, "Roulette", "", (EventTier(1, "Spin", 1, ""),), 9)
    assert describe(award(T.EVENT, 5, 1), {5: one}).description == strings.EVENT_POINT
    unknown = text(award(T.EVENT, 999, 2, title="Some Event", image="/Images/e.png"))
    assert (unknown.title, unknown.description) == ("Some Event", "Event award")
    assert unknown.image == ("award/Images/e", "/Images/e.png")


@pytest.mark.parametrize(
    ("made", "title", "description", "frame"),
    [
        (
            award(T.PATREON, 0, 2),
            "Patreon Supporter",
            "$2 Patreon supporter",
            Frame.HOLO,
        ),
        (award(T.PATREON, 0, 1), "Patreon Supporter", strings.PATREON_TEXT, Frame.GOLD),
        (
            award(T.UNLOCKS_YIELD, 3),
            "Achievements Earned by Others",
            "Over 1,000 unlocks",
            Frame.GOLD,
        ),
        (
            award(T.POINTS_YIELD, 0),
            "Achievement Points Earned by Others",
            "Over 1,000 points",
            Frame.GOLD,
        ),
        (award(T.UNLOCKS_YIELD, 99), strings.UNLOCKS_YIELD, strings.DEVELOPER_TEXT, Frame.GOLD),
        (
            award(T.MEDIA, 0, 2),
            "Media Contribution",
            "100 approved screenshots",
            Frame.GOLD,
        ),
        (award(T.LEGEND, 0), "Certified Legend", strings.LEGEND_TEXT, Frame.GOLD),
        (
            award(T.PLAYTEST, 4, title="Beta tester", image="/Images/p.png"),
            "Playtester Award",
            "Beta tester",
            Frame.GOLD,
        ),
    ],
)
def test_site_awards_read_like_the_profile(made, title, description, frame):
    described = text(made)
    assert (described.title, described.description, described.frame) == (title, description, frame)


def test_items_resolve_their_image_lazily_with_a_fallback():
    asked = []
    media = SimpleNamespace(resolve=lambda *args: asked.append(args) or "x.png")
    ctx = cast(AppContext, SimpleNamespace(media=media))
    game, event = _item(ctx, AWARDS[0], text(AWARDS[0])), _item(ctx, AWARDS[1], text(AWARDS[1]))
    assert asked == []  # only when drawn
    assert callable(game.icon)
    assert callable(event.icon)
    game.icon()
    event.icon()
    assert asked == [("icon/196", None, "gamepad"), ("award/Images/b", "/Images/b.png", "crown")]
    assert event.details is not None
    assert (event.tail, event.details.tags) == (fmt.local_date(90 * DAY),) * 2
    assert game.key != event.key  # the same ID, different awards


def test_select_cycles_the_views():
    assert [next_view(v) for v in ("carousel", "grid", "list", "bogus")] == [
        "grid",
        "list",
        "carousel",
        "carousel",
    ]


def picks(monkeypatch, *answers):
    asked = []
    replies = iter(answers)

    def pick(_title, options, current):
        asked.append((dict(options), current))
        return next(replies)

    monkeypatch.setattr(screen, "pick", pick)
    return asked


def test_filter_popup_counts_each_gallery_and_hides_empty_ones(monkeypatch):
    asked = picks(monkeypatch, "filter", "event")
    awards = [a for a in gallery(AWARDS) if a.type is not T.PATREON]
    assert _options(_View(sort="console"), awards) == _View(filter="event", sort="newest")
    options, current = asked[1]
    assert current == "all"
    assert options == {
        "all": "All · 5",
        "game": "Game Awards · 3",
        "mastered": "Mastered · 2",
        "completed": "Completed · 1",
        "event": "Event Awards · 2",  # no "Site Awards · 0"
    }


def test_console_sorting_is_offered_for_game_awards_only(monkeypatch):
    asked = picks(monkeypatch, "sort", None, "sort", None)
    assert _options(_View(filter="event"), gallery(AWARDS)) == _View(filter="event")
    assert "console" not in asked[1][0]
    assert _options(_View(filter="game", sort="console"), gallery(AWARDS)).sort == "console"
    assert "console" in asked[3][0]


def test_view_popup_and_backing_out(monkeypatch):
    picks(monkeypatch, "layout", "list", None)
    assert _options(_View(), []) == _View(layout="list")
    assert _options(_View(), []) == _View()


class FakeView:
    """Stands in for PreparedView: records how it was built and presses scripted buttons."""

    built: ClassVar[list["FakeView"]] = []
    presses: ClassVar[Iterator] = iter(())

    def __init__(self, title, items, *, selected, layout):
        self.title, self.items, self.layout = title, items, layout
        self.initial = self.selected = selected
        FakeView.built.append(self)

    def show(self, **_kwargs):
        button, index = next(FakeView.presses, (None, 0))
        if button is None:
            return None
        self.selected = index
        return Choice(self.items[index], index, button)


def browse(monkeypatch, presses, *, view="carousel", options=None, awards=AWARDS):
    FakeView.built, FakeView.presses = [], iter(presses)
    monkeypatch.setattr(screen, "PreparedView", FakeView)
    monkeypatch.setattr(screen, "_options", options or (lambda current, _awards: current))
    games = []
    monkeypatch.setattr(screen, "show_game", lambda _ctx, game_id: games.append(game_id))
    ctx = SimpleNamespace(
        settings=Settings(awards_view=view),
        data=SimpleNamespace(awards=lambda **_kw: (None, awards), events=lambda: EVENTS),
        media=SimpleNamespace(resolve=lambda *_args: "x.png"),
    )
    ctx.update_settings = lambda settings: setattr(ctx, "settings", settings)
    screen.show_awards(cast(AppContext, ctx))
    return ctx, games


def test_only_game_awards_open_without_mixing_up_ids(monkeypatch):
    # Newest first: the AotW event (ID 196), Patreon, then Banjo (game 196).
    _ctx, games = browse(monkeypatch, [(Button.A, 0), (Button.A, 1), (Button.A, 2)])
    assert games == [196]
    assert len(FakeView.built) == 1  # back from a game: the same view and page
    legacy = award(T.MASTERY, 9, 1, title="AotW 2017", console="Events")
    _ctx, games = browse(monkeypatch, [(Button.A, 0)], awards=[legacy])
    assert games == []  # an old event's mastery is an event badge, though its ID is a game's


@pytest.mark.parametrize(
    ("saved", "layout"),
    [("carousel", Layout.CAROUSEL), ("grid", Layout.BADGES), ("list", Layout.LIST)],
)
def test_awards_open_in_the_saved_view(monkeypatch, saved, layout):
    browse(monkeypatch, [], view=saved)
    assert [view.layout for view in FakeView.built] == [layout]


def test_select_cycles_views_keeping_the_selection_and_remembers_it(monkeypatch):
    ctx, _games = browse(monkeypatch, [(Button.SELECT, 3), (Button.SELECT, 3)])
    assert [view.layout for view in FakeView.built] == [Layout.CAROUSEL, Layout.BADGES, Layout.LIST]
    assert [view.initial for view in FakeView.built] == [0, 3, 3]
    assert ctx.settings.awards_view == "list"
    assert ctx.settings.achievement_grid is False  # independent of the achievement view


def test_new_filter_starts_at_the_top_and_unchanged_options_keep_the_page(monkeypatch):
    changes = iter([None, "event", "layout"])

    def options(current, _awards):
        change = next(changes)
        if change == "event":
            return _View(layout=current.layout, filter="event")
        if change == "layout":
            return _View(layout="grid", filter=current.filter)
        return current

    presses = [(Button.Y, 4), (Button.MENU, 4), (Button.Y, 1)]
    ctx, _games = browse(monkeypatch, presses, view="list", options=options)
    assert len(FakeView.built) == 3  # the unchanged options kept the first view
    assert [view.initial for view in FakeView.built] == [0, 0, 1]  # a new view keeps it
    assert [len(view.items) for view in FakeView.built] == [6, 2, 2]
    assert ctx.settings.awards_view == "grid"


def test_no_awards_and_an_empty_filter(monkeypatch):
    shown_messages = []
    monkeypatch.setattr(screen, "message", lambda _title, lines: shown_messages.append(lines))
    ctx = SimpleNamespace(
        settings=Settings(),
        data=SimpleNamespace(awards=lambda **_kw: (None, [AWARDS[3]]), events=dict),
    )
    screen.show_awards(cast(AppContext, ctx))  # only a beaten award: nothing to show
    assert shown_messages == [[strings.NO_AWARDS]]


def test_home_summary_leaves_out_empty_galleries():
    assert awards_summary(GalleryCounts()) == "No awards yet"
    assert awards_summary(GalleryCounts(902, 0, 35, 0)) == "902 mastered · 35 events"
    assert awards_summary(GalleryCounts(0, 2, 1, 3)) == "2 completed · 1 event · 3 site"
    assert awards_summary(GalleryCounts(1_234, 0, 0, 0)) == "1,234 mastered"


def profile(rank, total):
    return UserProfile("Balah", "", "", None, 0, 0, 0, rank, total, "", None)


def test_rank_text_like_ra():
    assert rank_text(profile(None, 100)) == "Unranked"
    assert rank_text(profile(42, 80_000)) == "#42 of 80,000"
    assert rank_text(profile(1_234, 80_000)).startswith("#1,234 of 80,000 · top ")
