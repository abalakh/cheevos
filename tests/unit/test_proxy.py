import json
import sqlite3

import pytest

from cheevos.core.models import PendingAward
from cheevos.core.proxy import ProxyReader
from cheevos.platform.paths import Paths

# Exact DDL from RAOfflineProxy v2.0.0-alpha1 (app/raofflineproxy/storage.py).
PROXY_DDL = """
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cacheKey TEXT NOT NULL UNIQUE,
    responseBody TEXT NOT NULL,
    sourceRomPath TEXT,
    cachedAt INTEGER NOT NULL,
    firstCachedAt INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    achievementId INTEGER NOT NULL UNIQUE,
    queryString TEXT NOT NULL,
    requestBody TEXT NOT NULL,
    userAgent TEXT NOT NULL,
    queuedAt INTEGER NOT NULL,
    retryCount INTEGER NOT NULL DEFAULT 0,
    lastError TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    payloadHash TEXT NOT NULL DEFAULT '',
    prevHash TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL DEFAULT '',
    signedAt INTEGER NOT NULL DEFAULT 0
);
"""

FFTA_PATCH = {
    "Success": True,
    "PatchData": {
        "ID": 519,
        "Title": "Final Fantasy Tactics Advance",
        "Achievements": [
            {"ID": 177850, "Title": "Welcome to Ivalice!", "Points": 1, "MemAddr": "0xH..."},
            {"ID": 177851, "Title": "Spice Trader", "Points": 2},
            {"ID": "bad", "Title": "Ignored"},
        ],
    },
}


@pytest.fixture
def paths(tmp_path):
    paths = Paths(sdcard=tmp_path)
    paths.proxy_data_dir.mkdir(parents=True)
    return paths


def make_db(paths, *, ddl=PROXY_DDL):
    connection = sqlite3.connect(paths.proxy_data_dir / "proxy.sqlite3")
    connection.executescript(ddl)
    connection.commit()
    return connection


def add_award(connection, achievement_id, queued_ms, status="pending"):
    connection.execute(
        "INSERT INTO pending_awards (achievementId, queryString, requestBody, userAgent, "
        "queuedAt, status) VALUES (?, '', '', 'RetroArch', ?, ?)",
        (achievement_id, queued_ms, status),
    )
    connection.commit()


def add_cache(connection, key, body):
    connection.execute(
        "INSERT INTO api_cache (cacheKey, responseBody, cachedAt, firstCachedAt) "
        "VALUES (?, ?, 0, 0)",
        (key, body if isinstance(body, str) else json.dumps(body)),
    )
    connection.commit()


def spruce_proxy_setting(paths, value):
    paths.spruce_config.parent.mkdir(parents=True, exist_ok=True)
    paths.spruce_config.write_text(
        json.dumps(
            {
                "menuOptions": {
                    "RetroAchievements Settings": {
                        "enableOfflineProxy": {"options": ["True", "False"], "selected": value}
                    }
                }
            }
        )
    )


def test_missing_database_stays_missing(paths):
    reader = ProxyReader(paths)
    assert reader.pending_awards("Balah") == []
    assert not (paths.proxy_data_dir / "proxy.sqlite3").exists()
    assert list(paths.proxy_data_dir.iterdir()) == []


def test_pending_awards_with_titles_oldest_first(paths):
    db = make_db(paths)
    add_cache(db, "patch:519:balah", FFTA_PATCH)
    add_award(db, 177851, 1_756_000_000_000)
    add_award(db, 177850, 1_755_000_000_000)
    add_award(db, 999, 1_757_000_000_000, status="flushed")
    add_award(db, 555, 1_758_000_000_000)  # no cached patch data
    db.close()
    assert ProxyReader(paths).pending_awards("Balah") == [
        PendingAward(
            177850, 519, "Final Fantasy Tactics Advance", "Welcome to Ivalice!", 1, 1_755_000_000
        ),
        PendingAward(
            177851, 519, "Final Fantasy Tactics Advance", "Spice Trader", 2, 1_756_000_000
        ),
        PendingAward(555, None, "", "", None, 1_758_000_000),
    ]


def test_prefers_own_patch_but_uses_other_accounts_to_fill_gaps(paths):
    db = make_db(paths)
    other = json.loads(json.dumps(FFTA_PATCH))
    other["PatchData"]["Achievements"][0]["Title"] = "Old title"
    add_cache(db, "patch:519:someoneelse", other)
    add_cache(db, "patch:519:balah", FFTA_PATCH)
    add_cache(
        db,
        "patch:3830:someoneelse",
        {
            "PatchData": {
                "ID": 3830,
                "Title": "Descent",
                "Achievements": [{"ID": 527418, "Title": "Brief", "Points": 0}],
            }
        },
    )
    add_cache(db, "patch:junk:balah", FFTA_PATCH)
    add_cache(db, "patch:1:balah", "{not json")
    add_cache(db, "gameid:abc", {"GameID": 1})
    add_award(db, 177850, 1000)
    add_award(db, 527418, 2000)
    db.close()
    awards = ProxyReader(paths).pending_awards(" BALAH ")
    assert [(a.achievement_title, a.game_title, a.queued_at) for a in awards] == [
        ("Welcome to Ivalice!", "Final Fantasy Tactics Advance", 1),
        ("Brief", "Descent", 2),
    ]


def test_only_flushed_awards_means_nothing_pending(paths):
    db = make_db(paths)
    add_award(db, 1, 1000, status="flushed")
    add_award(db, 2, 2000, status="deleted")
    db.close()
    assert ProxyReader(paths).pending_awards("Balah") == []


def test_patch_without_title_or_points(paths):
    db = make_db(paths)
    add_cache(db, "patch:7:balah", {"PatchData": {"Achievements": [{"ID": 70, "Points": "x"}]}})
    add_award(db, 70, 0)
    db.close()
    assert ProxyReader(paths).pending_awards("balah") == [
        PendingAward(70, 7, "Game 7", "Achievement 70", None, None)
    ]


def test_achievements_keyed_by_id(paths):
    db = make_db(paths)
    achievements = {"70": {"ID": 70, "Title": "Keyed", "Points": 5}}
    add_cache(db, "patch:7:balah", {"PatchData": {"Title": "G", "Achievements": achievements}})
    add_award(db, 70, 0)
    db.close()
    assert ProxyReader(paths).pending_awards("balah") == [
        PendingAward(70, 7, "G", "Keyed", 5, None)
    ]


@pytest.mark.parametrize(
    ("key", "body"),
    [
        ("patch:7:balah", {"PatchData": [1]}),
        ("patch:7:balah", {"PatchData": "x"}),
        ("patch:7:balah", {"PatchData": {"Achievements": 5}}),
        ("patch:7:balah", [1, 2]),
        ("patch:²:balah", FFTA_PATCH),  # isdigit() but not int()
    ],
)
def test_odd_patch_data_is_skipped(paths, key, body):
    db = make_db(paths)
    add_cache(db, key, body)
    add_award(db, 177850, 0)
    db.close()
    assert ProxyReader(paths).pending_awards("balah") == [
        PendingAward(177850, None, "", "", None, None)
    ]


def test_unexpected_failure_hides_the_queue_and_warns_once(paths, monkeypatch, caplog):
    db = make_db(paths)
    add_award(db, 1, 1000)
    db.close()

    def broken(*args):
        raise ValueError("a newer proxy")

    monkeypatch.setattr(ProxyReader, "_patch_index", staticmethod(broken))
    reader = ProxyReader(paths)
    assert reader.pending_awards("Balah") == []
    assert reader.pending_awards("Balah") == []
    assert caplog.text.count("Unexpected RAOfflineProxy data") == 1


def test_schema_mismatch_hides_data_and_warns_once(paths, caplog):
    make_db(paths, ddl="CREATE TABLE pending_awards (achievementId INTEGER);").close()
    reader = ProxyReader(paths)
    assert reader.pending_awards("Balah") == []
    assert reader.pending_awards("Balah") == []
    assert caplog.text.count("schema changed") == 1


def test_corrupt_database_never_raises(paths, caplog):
    (paths.proxy_data_dir / "proxy.sqlite3").write_bytes(b"this is not sqlite" * 100)
    assert ProxyReader(paths).pending_awards("Balah") == []
    assert "RAOfflineProxy database" in caplog.text


def test_open_failure_never_raises(paths, monkeypatch, caplog):
    make_db(paths).close()

    def refuse(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sqlite3, "connect", refuse)
    assert ProxyReader(paths).pending_awards("Balah") == []
    assert "Cannot open" in caplog.text


def test_reader_does_not_write(paths):
    db = make_db(paths)
    add_award(db, 1, 1000)
    db.close()
    database = paths.proxy_data_dir / "proxy.sqlite3"
    before = database.stat().st_mtime_ns
    ProxyReader(paths).pending_awards("Balah")
    assert database.stat().st_mtime_ns == before
    assert sorted(p.name for p in paths.proxy_data_dir.iterdir()) == ["proxy.sqlite3"]


def test_online_state(paths):
    reader = ProxyReader(paths)
    assert reader.online() is None
    state = paths.proxy_data_dir / "online_state.json"
    state.write_text('{"online": true}')
    assert reader.online() is True
    state.write_text('{"online": false}')
    assert reader.online() is False
    state.write_text("[]")
    assert reader.online() is None
    state.write_text("{broken")
    assert reader.online() is None


def test_cached_game_ids(paths):
    reader = ProxyReader(paths)
    assert reader.cached_game_ids() == set()
    (paths.proxy_data_dir / "cached_game_ids.txt").write_text("519\n 3830 \njunk\n\n-4\n²\n519\n")
    assert reader.cached_game_ids() == {519, 3830}


def test_installed_but_never_run(tmp_path):
    paths = Paths(sdcard=tmp_path)
    paths.proxy_data_dir.parent.mkdir(parents=True)  # the app folder, without data/
    spruce_proxy_setting(paths, "True")
    reader = ProxyReader(paths)
    assert (reader.installed(), reader.enabled()) == (True, True)
    assert (reader.online(), reader.cached_game_ids(), reader.pending_awards("Balah")) == (
        None,
        set(),
        [],
    )
    assert not paths.proxy_data_dir.exists()


def test_installed_and_enabled(tmp_path):
    paths = Paths(sdcard=tmp_path)
    reader = ProxyReader(paths)
    assert not reader.installed()
    assert not reader.enabled()
    paths.proxy_data_dir.parent.mkdir(parents=True)
    assert reader.installed()
    spruce_proxy_setting(paths, "False")
    assert not reader.enabled()
    spruce_proxy_setting(paths, "True")
    assert reader.enabled()
