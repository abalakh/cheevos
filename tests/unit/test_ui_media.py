import pytest

from cheevos.core.models import Achievement, UserProfile
from cheevos.core.storage.media_cache import MediaCache, avatar_key, badge_key, icon_key
from cheevos.ui.media import MediaResolver
from cheevos.ui.pyui.visible_images import ImageDemand


class FakeFetcher:
    def __init__(self):
        self.version = 0
        self.requests = []  # for the screen
        self.later = []  # for the next page
        self.drops = 0

    def request(self, key, media_path, *, later=False):
        (self.later if later else self.requests).append((key, media_path))

    def drop_waiting(self):
        self.drops += 1


class Demand:
    """What the views are drawing, switchable by the test."""

    def __init__(self):
        self.now = ImageDemand.SHOWN

    def __call__(self):
        return self.now


def achievement(*, unlocked):
    return Achievement(
        achievement_id=177851,
        game_id=519,
        title="Spice Trader",
        description="Complete Mission 001",
        points=2,
        retro_points=2,
        badge_name="198103",
        display_order=2,
        type=None,
        num_awarded=10,
        num_awarded_hardcore=5,
        earned_at=1_755_000_000 if unlocked else None,
        earned_hardcore_at=None,
    )


def profile(user_pic="/UserPic/Balah.png"):
    return UserProfile(
        username="Balah",
        user_pic=user_pic,
        motto="",
        member_since=None,
        hardcore_points=7,
        softcore_points=24,
        retro_points=7,
        rank=None,
        total_ranked=None,
        rich_presence="",
        last_game_id=None,
    )


@pytest.fixture
def media(tmp_path):
    cache = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")
    yield cache
    cache.close()


@pytest.fixture
def icons(tmp_path):
    return tmp_path / "icons"


def test_cached_image_resolves_to_extracted_file(media, icons):
    media.put(badge_key("198103", locked=False), b"PNGDATA")
    resolver = MediaResolver(media, icons)
    path = resolver.badge(achievement(unlocked=True))
    assert path.read_bytes() == b"PNGDATA"


def test_missing_image_falls_back_and_is_requested_once(media, icons):
    fetcher = FakeFetcher()
    resolver = MediaResolver(media, icons, fetcher)
    for _ in range(3):
        assert resolver.badge(achievement(unlocked=False)) == icons / "lock-muted.png"
    assert fetcher.requests == [(badge_key("198103", locked=True), "/Badge/198103_lock.png")]


def test_unlocked_badge_falls_back_to_trophy(media, icons):
    assert MediaResolver(media, icons).badge(achievement(unlocked=True)) == icons / "trophy.png"


def test_miss_memo_avoids_queries_until_version_changes(media, icons, monkeypatch):
    fetcher = FakeFetcher()
    resolver = MediaResolver(media, icons, fetcher)
    lookups = []
    original = media.path_for

    def counting(key):
        lookups.append(key)
        return original(key)

    monkeypatch.setattr(media, "path_for", counting)
    key = icon_key(519)
    for _ in range(5):
        assert resolver.game_icon(519, "/Images/070805.png") == icons / "gamepad.png"
    assert lookups == [key]

    media.put(key, b"ICON")  # the fetcher stored it...
    fetcher.version = 1  # ...and says so
    path = resolver.game_icon(519, "/Images/070805.png")
    assert path.read_bytes() == b"ICON"
    assert lookups == [key, key]
    assert resolver.version == 1


def test_empty_icon_path_is_not_fetched(media, icons):
    fetcher = FakeFetcher()
    resolver = MediaResolver(media, icons, fetcher)
    assert resolver.game_icon(2, "") == icons / "gamepad.png"
    assert fetcher.requests == []


def test_avatar(media, icons):
    fetcher = FakeFetcher()
    resolver = MediaResolver(media, icons, fetcher)
    assert resolver.avatar(None) == icons / "user.png"
    assert resolver.avatar(profile()) == icons / "user.png"
    assert fetcher.requests == [(avatar_key("Balah"), "/UserPic/Balah.png")]
    media.put(avatar_key("Balah"), b"AVATAR")
    fetcher.version = 1
    assert resolver.avatar(profile()).read_bytes() == b"AVATAR"


def test_without_fetcher_version_is_zero(media, icons):
    assert MediaResolver(media, icons).version == 0


ICON = (icon_key(519), "/Images/070805.png")


def test_rows_pyui_only_measures_are_neither_fetched_nor_memoized(media, icons):
    fetcher, demand = FakeFetcher(), Demand()
    resolver = MediaResolver(media, icons, fetcher, demand)
    demand.now = ImageDemand.MEASURED  # PyUI building the list: every row asks
    assert resolver.game_icon(519, ICON[1]) == icons / "gamepad.png"
    assert (fetcher.requests, fetcher.later) == ([], [])
    demand.now = ImageDemand.SHOWN  # the row is drawn
    resolver.game_icon(519, ICON[1])
    assert fetcher.requests == [ICON]


def test_cached_images_of_rows_pyui_only_measures_are_not_extracted(media, icons, tmp_path):
    media.put(icon_key(519), b"ICON")
    demand = Demand()
    resolver = MediaResolver(media, icons, FakeFetcher(), demand)
    demand.now = ImageDemand.MEASURED
    assert resolver.game_icon(519, ICON[1]) == icons / "gamepad.png"
    assert not any((tmp_path / "scratch").glob("*"))
    demand.now = ImageDemand.SHOWN
    assert resolver.game_icon(519, ICON[1]).read_bytes() == b"ICON"


def test_next_page_waits_until_it_is_on_screen(media, icons):
    fetcher, demand = FakeFetcher(), Demand()
    resolver = MediaResolver(media, icons, fetcher, demand)
    demand.now = ImageDemand.NEXT
    resolver.game_icon(519, ICON[1])
    resolver.game_icon(519, ICON[1])
    assert (fetcher.requests, fetcher.later) == ([], [ICON])
    demand.now = ImageDemand.SHOWN  # scrolled into view: asked again, for the screen
    resolver.game_icon(519, ICON[1])
    assert fetcher.requests == [ICON]


def test_a_new_window_drops_waiting_downloads_and_asks_again(media, icons):
    fetcher = FakeFetcher()
    resolver = MediaResolver(media, icons, fetcher)
    resolver.game_icon(519, ICON[1])
    resolver.new_window()
    resolver.game_icon(519, ICON[1])
    assert fetcher.drops == 1
    assert fetcher.requests == [ICON, ICON]
