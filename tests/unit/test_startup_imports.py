import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# Not needed for Home's first frame, and slow to import on a Mini: they load on first use
# (.agents/device.md, "Start-up"). A new screen or worker belongs here too.
LATER = [
    "email.utils",
    "http.client",
    "ssl",
    "cheevos.core.net",
    "cheevos.core.ra_client.client",
    "cheevos.core.ra_client.transport",
    "cheevos.core.ra_client.v2",
    "cheevos.core.stats",
    "cheevos.core.sync.engine",
    "cheevos.core.sync.events",
    "cheevos.core.sync.session",
    "cheevos.ui.pyui.badge_grid",
    "cheevos.ui.pyui.carousel",
    "cheevos.ui.screens.achievement",
    "cheevos.ui.screens.awards",
    "cheevos.ui.screens.game_detail",
    "cheevos.ui.screens.game_status",
    "cheevos.ui.screens.games",
    "cheevos.ui.screens.lists",
    "cheevos.ui.screens.profile",
    "cheevos.ui.screens.settings",
]


def test_the_app_starts_without_what_home_does_not_need():
    probe = "import sys, cheevos.app; print('\\n'.join(sorted(sys.modules)))"
    loaded = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(SRC)},
    ).stdout.split()
    assert "cheevos.ui.screens.home" in loaded
    assert [module for module in LATER if module in loaded] == []
