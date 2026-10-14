import ast
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from cheevos.ui.pyui.bootstrap import MINI_VARIABLES, _warm_wifi_status

REPO = Path(__file__).resolve().parents[2]
PYUI_DIR = Path(os.environ.get("CHEEVOS_PYUI_DIR", REPO / ".spruceos/App/PyUI/main-ui"))


def mini_branches(source: str) -> dict[str, tuple[str, str]]:
    """Map each ``"NAME" == device`` branch of initialize_device to (class, variables)."""
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "initialize_device"
    )
    branches = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        name = node.test.left
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            continue
        for call in ast.walk(node.body[-1]):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.args:
                last = call.args[-1]
                if call.func.id.startswith("Miyoo") and isinstance(last, ast.Name):
                    branches[name.value] = (call.func.id, last.id)
    return branches


@pytest.mark.skipif(not (PYUI_DIR / "mainui.py").is_file(), reason="no PyUI checkout")
def test_mini_devices_match_pyuis_own_table():
    branches = mini_branches((PYUI_DIR / "mainui.py").read_text())
    for name, variables in MINI_VARIABLES.items():
        assert branches[name] == ("MiyooMiniCommon", variables), name


def test_branches_are_read_from_the_launcher_source():
    source = """
def initialize_device(device, main_ui_mode):
    if "MIYOO_MINI" == device:
        from devices.miyoo.mini.miyoo_mini_common import MiyooMiniCommon
        Device.init(MiyooMiniCommon(device, main_ui_mode, MIYOO_MINI_V1_V2_V3_VARIABLES))
    elif "OTHER" == device:
        Device.init(Other(device))
"""
    assert mini_branches(source) == {
        "MIYOO_MINI": ("MiyooMiniCommon", "MIYOO_MINI_V1_V2_V3_VARIABLES")
    }


def test_wifi_status_is_read_ahead_on_a_thread():
    read = threading.Event()
    main = threading.current_thread()
    threads = []

    def get_wifi_status():
        threads.append(threading.current_thread())
        read.set()

    _warm_wifi_status(SimpleNamespace(get_wifi_status=get_wifi_status))
    assert read.wait(5)
    assert threads[0] is not main
    _warm_wifi_status(SimpleNamespace())  # devices without Wi-Fi: nothing to read


def test_a_failed_wifi_read_does_not_escape():
    failed = threading.Event()

    def get_wifi_status():
        failed.set()
        raise RuntimeError("wifiCmd missing")

    _warm_wifi_status(SimpleNamespace(get_wifi_status=get_wifi_status))
    assert failed.wait(5)
