import argparse
import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cheevos import app
from cheevos.core.credentials import Credentials
from cheevos.core.sync.detail_fetch import FetchState, FetchStatus
from cheevos.core.sync.progress import Failure
from cheevos.platform.arguments import add_game_argument
from cheevos.platform.paths import Paths
from cheevos.ui.context import AppContext
from cheevos.ui.screens import game_detail
from cheevos.ui.screens.game_status import GameSyncBar


@pytest.mark.parametrize("value", ["0", "-1", "bad", "1.5"])
def test_invalid_game_ids_are_rejected(value):
    parser = argparse.ArgumentParser()
    add_game_argument(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--game-id", value])


def test_game_launch_argument_is_optional_and_positive():
    parser = argparse.ArgumentParser()
    add_game_argument(parser)
    assert parser.parse_args([]).game_id is None
    assert parser.parse_args(["--game-id", "519"]).game_id == 519
    assert parser.parse_args(["--game-id", "2147483648"]).game_id == 2147483648


def test_direct_launch_never_starts_an_account_sync(monkeypatch, tmp_path):
    calls = []

    class Details:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, game_id, **kwargs):
            calls.append((game_id, kwargs))

        def close(self):
            pass

    def forbid_sync(*_args, **_kwargs):
        pytest.fail("a direct launch started account-wide sync")

    def show_game(ctx, game_id, *, refresh):
        assert (game_id, refresh, ctx.launch_game_id) == (519, True, 519)
        ctx.start_sync()
        ctx.start_sync(full=True)

    monkeypatch.setattr(app.primitives, "screen_size", lambda: (640, 480))
    monkeypatch.setattr(app, "ensure_credentials", lambda *_args: Credentials("Test", "x" * 32))
    monkeypatch.setattr(app, "DetailFetcher", Details)
    monkeypatch.setattr(app.BackgroundSync, "start", forbid_sync)
    monkeypatch.setattr(app.Home, "run", forbid_sync)
    monkeypatch.setattr(game_detail, "show_game", show_game)
    monkeypatch.setattr(app.status_bar, "installed", lambda *_args: contextlib.nullcontext())
    monkeypatch.setattr(app.title_bar, "installed", contextlib.nullcontext)
    monkeypatch.setattr(app.visible_images, "track_images", lambda *_args: None)
    paths = Paths(tmp_path, tmp_path / "scratch")
    app.run(started_at=0, env=app.AppEnvironment(paths=paths), game_id=519)
    assert calls == [(519, {"refresh": True}), (519, {"refresh": True})]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (FetchStatus(FetchState.WAITING), "cancel"),
        (FetchStatus(FetchState.DONE), "refresh"),
        (FetchStatus(FetchState.CANCELLED), "refresh"),
        (FetchStatus(FetchState.FAILED, Failure.AUTH), "key"),
    ],
)
def test_start_in_a_game_session_only_targets_that_game(state, expected):
    calls = []
    ctx = SimpleNamespace(
        details=SimpleNamespace(
            status=lambda _id: state, cancel=lambda game: calls.append(("cancel", game))
        ),
        start_sync=lambda: calls.append(("refresh", 519)),
    )
    bar = GameSyncBar(
        cast(AppContext, ctx), Path("/icons"), lambda: calls.append(("key", 519)), 519
    )
    bar.press_start()
    assert calls == [(expected, 519)]
