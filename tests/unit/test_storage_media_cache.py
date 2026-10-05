import os
import shutil
from pathlib import Path

import pytest

from cheevos.core.storage.media_cache import (
    MediaCache,
    avatar_key,
    badge_key,
    icon_key,
    in_pages,
    scratch_name,
)


@pytest.fixture
def media(tmp_path):
    cache = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch", clock=lambda: 1234.0)
    yield cache
    cache.close()


def extract(cache: MediaCache, key: str) -> Path:
    path = cache.path_for(key)
    assert path is not None
    return path


def png(size: int, fill: int = 0) -> bytes:
    return b"\x89PNG" + bytes([fill]) * (size - 4)


def test_key_helpers():
    assert badge_key("198102", locked=False) == "badge/198102"
    assert badge_key("198102", locked=True) == "badge/198102_lock"
    assert icon_key(519) == "icon/519"
    assert avatar_key("Balah") == "avatar/balah"
    assert scratch_name("badge/198102_lock") == "badge__198102_lock.png"
    assert scratch_name("avatar/we!rd name") == "avatar__we_rd_name.png"


def test_put_has_missing_size(media):
    assert not media.has("icon/1")
    media.put("icon/1", png(10))
    media.put_many([("icon/2", png(20)), ("icon/3", png(30))])
    assert media.has("icon/2")
    assert media.missing(["icon/9", "icon/1", "icon/9", "icon/8"]) == ["icon/9", "icon/8"]
    assert media.size_bytes() == 60
    stored_at = media._db.execute("SELECT stored_at FROM media WHERE key = 'icon/1'").fetchone()
    assert stored_at[0] == 1234


def test_missing_handles_more_keys_than_one_query_chunk(media):
    media.put_many([(icon_key(i), png(5)) for i in range(0, 1200, 2)])
    missing = media.missing(icon_key(i) for i in range(1200))
    assert missing == [icon_key(i) for i in range(1, 1200, 2)]


def test_path_for_extracts_and_reuses(media, tmp_path):
    assert media.path_for("badge/1") is None
    media.put("badge/1", png(50, 7))
    path = extract(media, "badge/1")
    assert path == tmp_path / "scratch" / "badge__1.png"
    assert path.read_bytes() == png(50, 7)
    mtime = path.stat().st_mtime_ns
    assert media.path_for("badge/1") == path
    assert path.stat().st_mtime_ns == mtime  # reused, not rewritten


def test_replacing_a_blob_refreshes_its_extracted_file(media):
    media.put("badge/1", png(50, 1))
    first = extract(media, "badge/1")
    media.put("badge/1", png(50, 2))
    assert not first.exists()
    assert extract(media, "badge/1").read_bytes() == png(50, 2)


def test_lru_eviction_keeps_scratch_under_limit(tmp_path):
    cache = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch", scratch_limit_bytes=10_240)
    cache.put_many([(f"badge/{name}", png(1000)) for name in "abcd"])
    a, b = extract(cache, "badge/a"), extract(cache, "badge/b")
    c = extract(cache, "badge/c")  # three 4 KB pages > 10 KB: evicts a
    assert not a.exists()
    assert b.exists()
    assert c.exists()
    extract(cache, "badge/b")  # b becomes most recent
    d = extract(cache, "badge/d")  # evicts c, the least recently used
    assert b.exists()
    assert d.exists()
    assert not c.exists()
    cache.close()


def test_sizes_count_whole_tmpfs_pages():
    assert [in_pages(size) for size in (0, 1, 4096, 4097)] == [0, 4096, 4096, 8192]


def test_oversized_image_is_still_returned(tmp_path):
    cache = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch", scratch_limit_bytes=10)
    cache.put("avatar/x", png(100))
    assert extract(cache, "avatar/x").exists()
    cache.close()


def test_lru_is_seeded_from_previous_runs_oldest_first(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    for index, name in enumerate(["old.png", "newer.png"]):
        (scratch / name).write_bytes(png(1000))
        os.utime(scratch / name, (1000 + index, 1000 + index))
    cache = MediaCache.open(tmp_path / "media.db", scratch, scratch_limit_bytes=10_240)
    cache.put("badge/new", png(1000))
    cache.path_for("badge/new")
    assert not (scratch / "old.png").exists()
    assert (scratch / "newer.png").exists()
    cache.close()


def test_scratch_dir_deleted_externally_is_recreated(media, tmp_path):
    media.put("badge/1", png(10))
    first = extract(media, "badge/1")
    shutil.rmtree(tmp_path / "scratch")
    again = extract(media, "badge/1")
    assert again == first
    assert again.exists()


def test_clear_removes_blobs_and_extracted_files(media, tmp_path):
    media.put_many([("badge/1", png(10)), ("badge/2", png(10))])
    extracted = extract(media, "badge/1")
    media.clear()
    assert media.size_bytes() == 0
    assert not media.has("badge/1")
    assert not extracted.exists()
    media.put("badge/3", png(10))  # still usable after clearing
    assert media.has("badge/3")


def test_corrupt_media_db_is_recreated(tmp_path):
    db = tmp_path / "media.db"
    db.write_bytes(os.urandom(2048))
    cache = MediaCache.open(db, tmp_path / "scratch")
    assert cache.size_bytes() == 0
    cache.close()
