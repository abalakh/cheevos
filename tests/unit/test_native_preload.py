"""Verify that background imports stay separate from session and SDL initialization."""

import os
import subprocess
import sys


def test_preload_has_no_device_network_user_storage_or_logging_side_effects(tmp_path):
    program = """
import logging, signal, socket, sys, threading
from pathlib import Path
from cheevos.ui.pyui.native_app import _preload
root = Path(sys.argv[1])
before = (logging.getLogRecordFactory(), list(logging.getLogger().handlers),
          signal.getsignal(signal.SIGTERM), sys.stdout, sys.stderr)
class NoNetwork(socket.socket):
    def __init__(self, *args, **kwargs):
        raise AssertionError('network during preload')
socket.socket = NoNetwork
worker = threading.Thread(target=_preload)
worker.start()
worker.join(15)
assert not worker.is_alive()
assert 'cheevos.app' in sys.modules and 'cheevos.ui.pyui.session' in sys.modules
assert not {'sdl2', 'display', 'devices', 'themes', 'controller', 'mainui'} & sys.modules.keys()
assert before == (logging.getLogRecordFactory(), list(logging.getLogger().handlers),
                  signal.getsignal(signal.SIGTERM), sys.stdout, sys.stderr)
assert not list(root.iterdir())
assert not [t for t in threading.enumerate() if t.name.startswith('cheevos-')]
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path)],
        env={**os.environ, "CHEEVOS_SDCARD_ROOT": str(tmp_path)},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
