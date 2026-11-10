"""The sync engine's test harness: recorded RA fixtures, a mirrored media host, fresh caches."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from cheevos.core.ra_client.client import RaClient
from cheevos.core.ra_client.transport import FixtureTransport
from cheevos.core.storage.data_cache import DataCache
from cheevos.core.storage.media_cache import MediaCache
from cheevos.core.sync.engine import SyncDeps, SyncEngine
from cheevos.core.sync.progress import ProgressTracker

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ra"
NOW = 1_791_158_400  # 2026-10-05 00:00 UTC
FFTA = 519


def recorded_game_ids():
    return sorted(int(p.stem.split("_")[1]) for p in FIXTURES.glob("game_*.json"))


def build_media_dir(root: Path) -> Path:
    """Mirror the media host for every image the fixtures reference."""
    summary = json.loads((FIXTURES / "user_summary.json").read_text())
    paths = {summary["UserPic"]}
    for game_id in recorded_game_ids():
        game = json.loads((FIXTURES / f"game_{game_id}.json").read_text())
        paths.add(game["ImageIcon"])
        for achievement in game["Achievements"].values():
            paths.add(f"/Badge/{achievement['BadgeName']}.png")
            paths.add(f"/Badge/{achievement['BadgeName']}_lock.png")
    for path in paths:
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG:" + path.encode())
    return root


class Harness:
    def __init__(
        self, tmp_path: Path, media_dir: Path, transport=None, on_device=frozenset({FFTA})
    ):
        self.transport = transport or FixtureTransport(FIXTURES, media_dir=media_dir)
        self.client = RaClient("Balah", "k" * 32, self.transport, user_agent="test", min_interval=0)
        self.data = DataCache.open(tmp_path / "data.db", "Balah")
        self.media = MediaCache.open(tmp_path / "media.db", tmp_path / "scratch")
        self.tracker = ProgressTracker()
        self.cancel = threading.Event()
        self.online = True
        self.on_device = set(on_device)

    def engine(self, now=NOW):
        deps = SyncDeps(self.client, self.data, self.media, on_device=lambda: self.on_device)
        return SyncEngine(
            deps,
            self.tracker,
            self.cancel,
            clock=lambda: now,
            online=lambda: self.online,
        )

    def calls(self):
        return [method for method, _ in self.transport.calls]
