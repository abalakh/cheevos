"""Desktop data modes: recorded fixtures (default, offline, deterministic) or the live API.

Fixture mode prepares a throwaway SD card (username in a RetroArch config, a dummy key, unlock
screenshots), syncs the recorded responses into its caches before the UI starts, and serves
lazily requested images from ``dev/media-host`` when ``scripts/fetch_dev_media.py`` has
filled it.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path

from cheevos.app import AppEnvironment
from cheevos.core.ra_client.pacer import Pacer
from cheevos.core.ra_client.transport import FixtureTransport
from cheevos.core.settings import BadgeScope
from cheevos.core.sync.engine import SyncEngine, SyncOptions
from cheevos.core.sync.progress import ProgressTracker
from cheevos.core.sync.session import Credentials, open_sync_deps
from cheevos.platform.desktop.simulate import prepare_card, simulation
from cheevos.platform.paths import Paths
from cheevos.ui.pyui.generated import encode_png

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "tests" / "fixtures" / "ra"
MEDIA_HOST_MIRROR = REPO / "dev" / "media-host"
BORROWED_AWARDS = REPO / "dev" / "fixtures" / "awards"  # the ``awards`` drill's recording
REAL_SCREENSHOTS = REPO / "dev" / "sdcard" / "Saves" / "screenshots"
# Final Fantasy Tactics Advance's two unlocks, which the walk-throughs open.
STAND_IN_SCREENSHOTS = (177850, 177851)
FIXTURE_USER = "Balah"
DUMMY_KEY = "0" * 32


def _paths(sd_root: Path) -> Paths:
    """Desktop paths: scratch next to the SD card instead of ``/tmp/cheevos``.

    Args:
        sd_root: Fake SD-card root.

    Returns:
        The paths.
    """
    return Paths(sdcard=sd_root, scratch=sd_root / "_scratch")


def _fixture_transport() -> FixtureTransport:
    """Serve recorded API responses, and images from the media-host mirror if present."""
    media = MEDIA_HOST_MIRROR if MEDIA_HOST_MIRROR.is_dir() else None
    return FixtureTransport(FIXTURES, media_dir=media)


def _write_stand_in_screenshots(directory: Path) -> None:
    """Give the walk-throughs' achievements a made-up unlock screenshot.

    Without one, A on the achievement card does nothing, so a script that opens the screenshot
    drifts from the screens. ``dev/sdcard`` is git-ignored, so CI has no real screenshots.

    Args:
        directory: The fake card's screenshot directory.
    """
    width, height = 240, 160  # a GBA frame, like the real ones
    rgba = bytes(
        channel
        for y in range(height)
        for x in range(width)
        for channel in (40 + x * 120 // width, 70 + y * 120 // height, 150, 255)
    )
    png = encode_png(width, height, rgba)
    directory.mkdir(parents=True, exist_ok=True)
    for achievement_id in STAND_IN_SCREENSHOTS:
        (directory / f"Stand-in-cheevo-{achievement_id}.png").write_bytes(png)


def _prepare_fixture_card(paths: Paths) -> None:
    """Give the fake card a username, a key and screenshots (real ones if available).

    Args:
        paths: Fake card paths.
    """
    paths.retroarch_config.parent.mkdir(parents=True, exist_ok=True)
    screenshots = REAL_SCREENSHOTS
    if not screenshots.is_dir():
        screenshots = paths.default_screenshot_dir
        _write_stand_in_screenshots(screenshots)
    paths.retroarch_config.write_text(
        f'cheevos_username = "{FIXTURE_USER}"\nscreenshot_directory = "{screenshots}"\n',
        encoding="utf-8",
    )
    if not paths.api_key_file.exists():
        paths.api_key_file.parent.mkdir(parents=True, exist_ok=True)
        paths.api_key_file.write_text(DUMMY_KEY + "\n", encoding="utf-8")


def fixture_environment(sd_root: Path) -> AppEnvironment:
    """Prepare a card filled from the recorded fixtures and return its environment.

    ``CHEEVOS_SIMULATE`` (see :mod:`cheevos.platform.desktop.simulate`) selects a failure or
    edge-case drill.

    Args:
        sd_root: Fake SD-card root (created if missing).

    Returns:
        An environment that never touches the network.
    """
    scenario = os.environ.get("CHEEVOS_SIMULATE") or None
    awards = Path(os.environ.get("CHEEVOS_AWARDS_FIXTURES") or BORROWED_AWARDS)
    drill = simulation(scenario, FIXTURES, _fixture_transport, awards)
    if scenario:  # each drill starts from its own clean card
        sd_root = sd_root.with_name(f"{sd_root.name}-{scenario}")
        shutil.rmtree(sd_root, ignore_errors=True)
    paths = _paths(sd_root)
    _prepare_fixture_card(paths)
    prepare_card(scenario, paths, FIXTURES)
    transport = drill.transport if drill.seeds_card and drill.transport else _fixture_transport
    credentials = Credentials(FIXTURE_USER, DUMMY_KEY)
    deps = open_sync_deps(paths, credentials, transport(), pacer=Pacer(0.0))
    try:
        engine = SyncEngine(
            deps,
            ProgressTracker(),
            threading.Event(),
            online=lambda: True,
        )
        # Fixture mode shows everything (every game's details and badges, as if downloaded),
        # unless the drill is about what a first sync leaves out.
        options = SyncOptions(full=drill.download_all, badge_scope=BadgeScope.ALL)
        status = engine.run(options)
        logger.info("Fixture pre-sync: %s", status.phase.value)
    finally:
        deps.close()
    return AppEnvironment(
        paths=paths,
        transport_factory=drill.transport or _fixture_transport,
        online=lambda: drill.online,
        clock=drill.clock,
        auto_sync=drill.auto_sync,
        api_interval=0.0,  # recorded responses: nothing to be polite to
    )


def live_environment(sd_root: Path) -> AppEnvironment:
    """Return an environment that talks to the real RetroAchievements API.

    The card needs a username (Spruce or RetroArch config) and ``Saves/cheevos/apikey.txt``;
    otherwise the app's setup screens ask for them.

    Args:
        sd_root: Dev SD-card root.

    Returns:
        The environment.
    """
    return AppEnvironment(paths=_paths(sd_root))
