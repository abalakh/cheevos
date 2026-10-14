"""Exercise the optional SpruceOS source prototype with the real PyUI desktop device."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_desktop_runner import png_size

REPO = Path(__file__).resolve().parents[2]
SOURCE_PYUI = Path(
    os.environ.get(
        "CHEEVOS_CARTRIDGE_PYUI_DIR", REPO.parent / "spruceOS" / "App" / "PyUI" / "main-ui"
    )
)
pytestmark = [
    pytest.mark.screens,
    pytest.mark.skipif(
        not (SOURCE_PYUI / "views" / "cartridge_view.py").is_file(),
        reason="cartridge prototype needs the SpruceOS source checkout",
    ),
]

SCRIPT = (
    "shot:shelf,right,wait:5,shot:next,a,wait:3,shot:inserting,wait:12,shot:inserted,"
    "b,shot:returned,a,b,shot:cancelled,select,shot:gb,right,wait:4,shot:gb_next,"
    "select,shot:gbc"
)


@pytest.mark.parametrize("res", ["640x480", "752x560", "1280x720", "480x800"])
def test_browse_insert_cancel_and_short_shelves(tmp_path, res):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cheevos.platform.desktop",
            "--cartridges",
            "--headless",
            "--res",
            res,
            "--script",
            SCRIPT,
            "--out",
            str(tmp_path / "shots"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={
            **os.environ,
            "CHEEVOS_PYUI_DIR": str(SOURCE_PYUI),
            "CHEEVOS_THEMES_DIR": str(SOURCE_PYUI.parents[2] / "Themes"),
            "CHEEVOS_SDCARD_ROOT": str(tmp_path / "card"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert result.returncode == 0, result.stderr
    shots = tmp_path / "shots" / res
    expected_size = tuple(int(value) for value in res.split("x"))
    names = [
        "shelf",
        "next",
        "inserting",
        "inserted",
        "returned",
        "cancelled",
        "gb",
        "gb_next",
        "gbc",
    ]
    for name in names:
        assert png_size(shots / f"{name}.png") == expected_size
    assert (shots / "shelf.png").read_bytes() != (shots / "next.png").read_bytes()
    assert (shots / "inserting.png").read_bytes() != (shots / "inserted.png").read_bytes()
    assert (shots / "gb.png").read_bytes() != (shots / "gb_next.png").read_bytes()


@pytest.fixture
def geometry_module():
    spec = importlib.util.spec_from_file_location(
        "cartridge_geometry", SOURCE_PYUI / "views" / "cartridge_geometry.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 1000])
def test_wraparound_draws_each_short_collection_entry_once(geometry_module, count):
    for position in (-1, -0.5, 0, 0.5, count - 0.2, count + 0.5):
        slots = geometry_module.visible_slots(position, count)
        indices = [index for index, _distance in slots]
        assert len(indices) == len(set(indices))
        assert len(indices) <= min(count, 6)
        assert all(0 <= index < count for index in indices)


@pytest.mark.parametrize("size", [(640, 480), (752, 560), (1280, 720), (480, 800)])
def test_launch_ends_behind_slot_and_starts_above_bars(geometry_module, size):
    width, height = size
    geometry = geometry_module.Geometry(width, height, 60)
    dock_x, dock_y, dock_width, dock_height = geometry.dock_rect
    assert dock_x <= 0
    assert dock_x + dock_width >= width
    assert dock_y + dock_height == height
    for system in ("GB", "GBC", "GBA", "unknown"):
        shell = geometry_module.shell_for(system)
        x, y, cart_width, cart_height = geometry.launch_rect(shell, 0)
        assert x >= 0
        assert x + cart_width <= width
        assert y >= geometry.top
        assert y + cart_height <= geometry.slot_y
        assert (x, y, cart_width, cart_height) == geometry.browse_rect(shell)
        assert geometry.launch_rect(shell, 1)[1] >= geometry.slot_y


@pytest.mark.parametrize("size", [(640, 480), (752, 560), (1280, 720), (480, 800)])
def test_large_browsing_cartridges_fit_then_pause_at_contact(geometry_module, size):
    geometry = geometry_module.Geometry(*size, top=60)
    timing = geometry_module
    for system in ("GB", "GBC", "GBA", "unknown"):
        shell = geometry_module.shell_for(system)
        browsing = geometry.browse_rect(shell)
        approaching = geometry.launch_rect(shell, timing.SHRINK_SECONDS / timing.INSERT_SECONDS)
        contact = geometry.launch_rect(
            shell, (timing.CONTACT_START + timing.CONTACT_SECONDS / 4) / timing.INSERT_SECONDS
        )
        held = geometry.launch_rect(
            shell, (timing.CONTACT_START + timing.CONTACT_SECONDS * 3 / 4) / timing.INSERT_SECONDS
        )
        pushed = geometry.launch_rect(
            shell, (timing.PUSH_START + timing.PUSH_SECONDS / 2) / timing.INSERT_SECONDS
        )
        assert browsing[2] > approaching[2]
        assert contact == held
        assert contact[1] + contact[3] == geometry.slot_y
        assert contact[2] < geometry.dock_rect[2] * 252 / 720
        assert pushed[1] > contact[1]
        assert pushed[2:] == contact[2:]
