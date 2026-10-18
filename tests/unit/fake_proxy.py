"""A stand-in RAOfflineProxy install for identification tests.

``rom_hashing`` follows the real wrapper's API (``RomHashResult``, ``load_rchash`` and the
candidate functions). Hashes are MD5s of file content. The proxy modules the helper must never
load fail on import, so loading one fails the test. Environment switches let subprocess tests
steer it: ``FAKE_RCHASH=missing`` (no native library) and ``FAKE_HASH_BLOCK=1`` (announce
"hashing" on stderr, then block until stdin closes or a signal arrives).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

TRIPWIRES = ("main", "menu_sdl", "rom_browser", "service", "proxy_service", "storage", "network")

ROM_HASHING = """
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_LIBRCHASH_ERROR = None


@dataclass
class RomHashResult:
    candidates: list
    error: str | None = None


def load_rchash():
    global _LIBRCHASH_ERROR
    if os.environ.get("FAKE_RCHASH") == "missing":
        _LIBRCHASH_ERROR = "libraproxy_rchash shared library not found"
        return None
    return object()


def hash_rom_candidates_result(path):
    path = Path(path)
    if os.environ.get("FAKE_HASH_BLOCK"):
        sys.stderr.write("hashing\\n")
        sys.stderr.flush()
        sys.stdin.read()
    if path.suffix.lower() == ".zip":
        return RomHashResult([hashlib.md5(b"arcade:" + path.name.encode()).hexdigest()])
    return RomHashResult([hashlib.md5(path.read_bytes()).hexdigest()])


def list_7z_entries(path):
    return []


def hash_7z_entry_candidates(path, entry_name):
    return []


def supported_rom_extensions():
    return {".gba", ".nes", ".sfc"}
"""


def md5(data: bytes) -> str:
    """Return the fake hasher's candidate for some content."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def install(sdcard: Path, *, rom_hashing: str = ROM_HASHING, extra: dict[str, str] | None = None):
    """Create ``App/RAOfflineProxy`` under ``sdcard`` and return its package directory."""
    package = sdcard / "App" / "RAOfflineProxy" / "app" / "raofflineproxy"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__all__ = ["main"]\n', encoding="utf-8")
    (package / "rom_hashing.py").write_text(rom_hashing, encoding="utf-8")
    for name in TRIPWIRES:
        (package / f"{name}.py").write_text(
            f'raise ImportError("the helper must not import raofflineproxy.{name}")\n',
            encoding="utf-8",
        )
    for name, source in (extra or {}).items():
        (package / f"{name}.py").write_text(source, encoding="utf-8")
    return package


# The proxy's own api_cache DDL (app/raofflineproxy/storage.py).
API_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cacheKey TEXT NOT NULL UNIQUE,
    responseBody TEXT NOT NULL,
    sourceRomPath TEXT,
    cachedAt INTEGER NOT NULL,
    firstCachedAt INTEGER NOT NULL
);
"""


def proxy_database(sdcard: Path, entries: dict[str, tuple[str, int]], *, ddl=API_CACHE_DDL) -> Path:
    """Create the proxy's ``proxy.sqlite3`` with ``cacheKey -> (body, cachedAt ms)`` rows."""
    database = sdcard / "App" / "RAOfflineProxy" / "data" / "proxy.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(ddl)
        if not entries:
            return database
        connection.executemany(
            "INSERT INTO api_cache (cacheKey, responseBody, cachedAt, firstCachedAt) "
            "VALUES (?, ?, ?, ?)",
            [(key, body, cached_at, cached_at) for key, (body, cached_at) in entries.items()],
        )
        connection.commit()
    finally:
        connection.close()
    return database
