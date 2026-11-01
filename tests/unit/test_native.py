import dataclasses
import logging
import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from cheevos import native
from cheevos.app import AppEnvironment
from cheevos.core.ra_client.redact import install_redaction, uninstall_redaction
from cheevos.platform.paths import Paths
from cheevos.ui import strings
from cheevos.ui.pyui import host as pyui_host

KEY = "A" * 32


@pytest.fixture
def card(tmp_path, monkeypatch):
    monkeypatch.setenv("CHEEVOS_SDCARD_ROOT", str(tmp_path))
    monkeypatch.setenv("PLATFORM", "MiyooMini")
    return tmp_path


@pytest.fixture
def host(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        enter=lambda: calls.append("enter"),
        leave=lambda: calls.append("leave"),
        show_message=Mock(),
        language=lambda: "English",
        set_spruce_setting=lambda *args: calls.append(("setting", *args)),
    )
    monkeypatch.setattr(native, "host", fake)
    monkeypatch.setattr(native, "uninstall_redaction", lambda: calls.append("redaction"))
    monkeypatch.setattr(native, "_await_workers", lambda: calls.append("workers"))
    fake.calls = calls
    return fake


def test_run_logs_and_shows_an_error_then_returns(card, host, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(native, "session", broken)
    native.run()
    log = (card / "Saves" / "spruce" / "cheevos-MiyooMini.log").read_text(encoding="utf-8")
    assert "Unhandled error" in log
    assert "RuntimeError: boom" in log
    host.show_message.assert_called_once()
    assert "Saves/spruce/cheevos-MiyooMini.log" in host.show_message.call_args.args[0]


def test_run_passes_the_game_and_leaves_logging_as_it_was(card, host, monkeypatch):
    seen = {}
    top = logging.getLogger(native.APP_LOGGER)
    before = (list(top.handlers), top.level, top.propagate)

    def session(env, *, started_at, game_id=None):
        seen.update(paths=env.paths, game_id=game_id, handlers=list(top.handlers))
        logging.getLogger("cheevos.test").info("inside the session")

    monkeypatch.setattr(native, "session", session)
    native.run(game_id=519)
    assert seen["game_id"] == 519
    assert seen["paths"].sdcard == card
    assert len(seen["handlers"]) == len(before[0]) + 1
    assert (list(top.handlers), top.level, top.propagate) == before
    log = (card / "Saves" / "spruce" / "cheevos-MiyooMini.log").read_text(encoding="utf-8")
    assert "inside the session" in log
    host.show_message.assert_not_called()


def test_a_failed_session_still_takes_everything_out_in_order(tmp_path, host, monkeypatch):
    def failing_app(**_kwargs):
        host.calls.append("app")
        raise RuntimeError("boom")

    monkeypatch.setattr(native.app, "run", failing_app)
    (tmp_path / "Saves" / "cheevos").mkdir(parents=True)
    (tmp_path / "Saves" / "cheevos" / "apikey.txt").write_text(f"\n {KEY} \n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="boom"):
        native.session(AppEnvironment(paths=Paths(sdcard=tmp_path)), started_at=0)
    assert host.calls == [
        "enter",
        "app",
        ("setting", "RetroAchievements Settings", "webApiKey", KEY),
        "leave",
        "workers",
        "redaction",
    ]


def test_without_a_key_file_spruce_gets_an_empty_key(tmp_path, host, monkeypatch):
    monkeypatch.setattr(native.app, "run", lambda **_kwargs: None)
    native.session(AppEnvironment(paths=Paths(sdcard=tmp_path)), started_at=0)
    assert ("setting", "RetroAchievements Settings", "webApiKey", "") in host.calls


def test_the_session_is_in_spruces_language(tmp_path, host, monkeypatch):
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    (lang_dir / "Catalan.json").write_text('{"SYNC": "Sincronitza"}', encoding="utf-8")
    host.language = lambda: "Catalan"
    seen = []
    monkeypatch.setattr(native.app, "run", lambda **_kwargs: seen.append(strings.SYNC))
    env = AppEnvironment(paths=Paths(sdcard=tmp_path), lang_dir=lang_dir)
    native.session(env, started_at=0)
    native.session(dataclasses.replace(env, language="English"), started_at=0)
    assert seen == ["Sincronitza", "Sync"]


def test_uninstalling_the_redaction_puts_the_record_factory_back(caplog):
    install_redaction(KEY)
    assert logging.getLogRecordFactory() is not logging.LogRecord
    uninstall_redaction()
    try:
        assert logging.getLogRecordFactory() is logging.LogRecord
        caplog.set_level(logging.INFO)
        logging.getLogger("other.library").info("raw %s", KEY)
        assert KEY in caplog.text  # nothing of the app is left in the process's logging
    finally:
        install_redaction(KEY)  # as other tests' clients leave it


def test_workers_are_waited_for(monkeypatch):
    release = threading.Event()
    worker = threading.Thread(target=release.wait, name="cheevos-test", daemon=True)
    worker.start()
    threading.Timer(0.05, release.set).start()
    native._await_workers(timeout=2)
    assert not worker.is_alive()


def test_a_stuck_worker_is_logged_not_waited_for_forever(caplog):
    release = threading.Event()
    worker = threading.Thread(target=release.wait, name="cheevos-stuck", daemon=True)
    worker.start()
    try:
        with caplog.at_level(logging.WARNING, logger="cheevos.native"):
            native._await_workers(timeout=0.05)
        assert "cheevos-stuck" in caplog.text
    finally:
        release.set()
        worker.join()


@pytest.fixture
def spruce_settings(monkeypatch):
    options = {"RetroAchievements Settings": {"webApiKey": {"selected": "old"}}}
    changed = []

    def get_selected_value(section, name):
        return options.get(section, {}).get(name, {}).get("selected")

    config = SimpleNamespace(
        get_selected_value=get_selected_value,
        set_menu_option=lambda *args: changed.append(args),
    )
    package = ModuleType("utils")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "utils", package)
    monkeypatch.setitem(
        sys.modules, "utils.cfw_system_config", SimpleNamespace(CfwSystemConfig=config)
    )
    return SimpleNamespace(options=options, changed=changed)


def test_spruce_setting_changes_only_when_it_exists_and_differs(spruce_settings):
    pyui_host.set_spruce_setting("RetroAchievements Settings", "webApiKey", "old")
    pyui_host.set_spruce_setting("RetroAchievements Settings", "missing", KEY)
    pyui_host.set_spruce_setting("Other", "webApiKey", KEY)
    assert spruce_settings.changed == []
    pyui_host.set_spruce_setting("RetroAchievements Settings", "webApiKey", KEY)
    assert spruce_settings.changed == [("RetroAchievements Settings", "webApiKey", KEY)]
