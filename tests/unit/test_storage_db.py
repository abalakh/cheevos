import logging
import os
import sqlite3

import pytest

from cheevos.core.storage.db import delete_cache_files, open_cache, reset_cache

DDL = "CREATE TABLE things (value INTEGER NOT NULL);"


def count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM things").fetchone()[0]


def test_creates_schema_and_stamps_version(tmp_path, caplog):
    path = tmp_path / "nested" / "cache.db"
    with caplog.at_level(logging.INFO):
        connection = open_cache(path, schema_version=3, ddl=DDL)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert count(connection) == 0
    assert "Creating cache" in caplog.text
    connection.close()


def test_applies_cache_pragmas(tmp_path):
    connection = open_cache(tmp_path / "cache.db", schema_version=1, ddl=DDL)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    connection.close()


def test_reopening_same_version_keeps_data(tmp_path):
    path = tmp_path / "cache.db"
    connection = open_cache(path, schema_version=1, ddl=DDL)
    with connection:
        connection.execute("INSERT INTO things VALUES (1)")
    connection.close()
    connection = open_cache(path, schema_version=1, ddl=DDL)
    assert count(connection) == 1
    connection.close()


def test_version_mismatch_recreates(tmp_path, caplog):
    path = tmp_path / "cache.db"
    connection = open_cache(path, schema_version=1, ddl=DDL)
    with connection:
        connection.execute("INSERT INTO things VALUES (1)")
    connection.close()
    with caplog.at_level(logging.INFO):
        connection = open_cache(path, schema_version=2, ddl=DDL)
    assert count(connection) == 0
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert "schema version 1, expected 2" in caplog.text
    connection.close()


def test_populated_file_without_version_is_recreated(tmp_path):
    path = tmp_path / "cache.db"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE old_stuff (x)")
    legacy.commit()
    legacy.close()
    connection = open_cache(path, schema_version=1, ddl=DDL)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert tables == {"things"}
    connection.close()


def test_corrupt_file_is_recreated_and_siblings_removed(tmp_path, caplog):
    path = tmp_path / "cache.db"
    path.write_bytes(os.urandom(4096))
    stale = [path.with_name("cache.db" + suffix) for suffix in ("-journal", "-wal", "-shm")]
    for sibling in stale:
        sibling.write_bytes(b"junk")
    with caplog.at_level(logging.INFO):
        connection = open_cache(path, schema_version=1, ddl=DDL)
    assert count(connection) == 0
    assert "unreadable" in caplog.text
    assert not any(sibling.exists() for sibling in stale)
    connection.close()


def test_rejects_version_below_one(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        open_cache(tmp_path / "cache.db", schema_version=0, ddl=DDL)


def test_reset_cache_empties_existing_cache(tmp_path):
    path = tmp_path / "cache.db"
    connection = open_cache(path, schema_version=1, ddl=DDL)
    with connection:
        connection.execute("INSERT INTO things VALUES (1)")
    connection.close()
    connection = reset_cache(path, schema_version=1, ddl=DDL)
    assert count(connection) == 0
    connection.close()


def test_delete_cache_files_tolerates_missing_files(tmp_path):
    delete_cache_files(tmp_path / "nothing-here.db")
