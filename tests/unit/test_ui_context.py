from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from cheevos.core.settings import DEFAULTS, Settings, load_settings, save_settings
from cheevos.core.sync.session import Credentials
from cheevos.platform.paths import Paths
from cheevos.ui import context
from cheevos.ui.context import AppContext


def make_context(tmp_path, settings=DEFAULTS):
    unused = cast(Any, None)
    return AppContext(
        paths=Paths(tmp_path),
        credentials=Credentials("Balah", "key"),
        settings=settings,
        data=unused,
        media_cache=unused,
        media=unused,
        sync=unused,
        details=unused,
        proxy=unused,
        screenshots=unused,
        icons=Path(),
        validate_key=lambda _username, _key: True,
        fetch_unlocks=lambda _start, _end: [],
        fetch_first_unlock=lambda _since: None,
    )


def test_changes_apply_in_memory_and_flush_once(tmp_path, monkeypatch):
    ctx = make_context(tmp_path)
    save_settings(ctx.paths.settings_file, ctx.settings)
    saved = Mock(wraps=save_settings)
    monkeypatch.setattr(context, "save_settings", saved)

    ctx.update_settings(replace(ctx.settings, game_list_details=True))
    ctx.update_settings(replace(ctx.settings, achievement_grid=True, auto_sync=False))
    assert ctx.settings == Settings(game_list_details=True, achievement_grid=True, auto_sync=False)
    assert load_settings(ctx.paths.settings_file) == Settings()
    saved.assert_not_called()

    ctx.flush_settings()
    saved.assert_called_once_with(ctx.paths.settings_file, ctx.settings)
    assert load_settings(ctx.paths.settings_file) == ctx.settings
    ctx.flush_settings()
    assert saved.call_count == 1


@pytest.mark.parametrize("initial", [Settings(), Settings(achievement_grid=True)])
def test_unchanged_or_reverted_settings_need_no_write(tmp_path, monkeypatch, initial):
    ctx = make_context(tmp_path, initial)
    saved = Mock()
    monkeypatch.setattr(context, "save_settings", saved)
    ctx.flush_settings()
    ctx.update_settings(replace(ctx.settings, achievement_grid=not initial.achievement_grid))
    ctx.update_settings(initial)
    ctx.flush_settings()
    saved.assert_not_called()
    assert not ctx.paths.settings_file.exists()


def test_failed_save_is_logged_and_can_be_retried(tmp_path, monkeypatch, caplog):
    ctx = make_context(tmp_path)
    save_settings(ctx.paths.settings_file, ctx.settings)
    ctx.update_settings(replace(ctx.settings, achievement_grid=True))
    saved = Mock(side_effect=OSError("card is read-only"))
    monkeypatch.setattr(context, "save_settings", saved)
    ctx.flush_settings()
    assert load_settings(ctx.paths.settings_file) == Settings()
    assert "Could not save settings" in caplog.text

    saved.side_effect = save_settings
    ctx.flush_settings()
    assert load_settings(ctx.paths.settings_file) == ctx.settings
    ctx.flush_settings()
    assert saved.call_count == 2
