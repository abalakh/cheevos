import importlib
import sys

import fake_proxy
import pytest

from cheevos.core.identification.result import IdentificationError
from cheevos.platform import proxy_hasher
from cheevos.platform.proxy_hasher import load_proxy_hasher


@pytest.fixture(autouse=True)
def _forget_the_proxy(monkeypatch):
    """Each test imports its own fake proxy: restore sys.path and drop its modules after."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [name for name in sys.modules if name.startswith("raofflineproxy")]:
        del sys.modules[name]


@pytest.fixture
def proxy_dir(tmp_path):
    return tmp_path / "App" / "RAOfflineProxy"


def dependency_error(proxy_dir):
    with pytest.raises(IdentificationError) as error:
        load_proxy_hasher(proxy_dir)
    assert error.value.reason == "dependency"
    return str(error.value)


def test_loads_only_the_hashing_wrapper(tmp_path, proxy_dir):
    fake_proxy.install(tmp_path)
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"cart")

    hasher = load_proxy_hasher(proxy_dir)

    assert hasher.supported_extensions() == {".gba", ".nes", ".sfc"}
    assert hasher.hash_file(rom).candidates == (fake_proxy.md5(b"cart"),)
    loaded = {name for name in sys.modules if name.startswith("raofflineproxy")}
    assert loaded == {"raofflineproxy", "raofflineproxy.rom_hashing"}
    assert not (proxy_dir / "app" / "raofflineproxy" / "__pycache__").exists()
    assert sys.dont_write_bytecode is False


def test_missing_proxy_is_a_dependency_error(proxy_dir):
    assert "no RAOfflineProxy hashing module" in dependency_error(proxy_dir)


def test_an_import_failure_is_a_dependency_error(tmp_path, proxy_dir):
    # Spruce's OTA mixed proxy versions: rom_browser imported a helper network.py no longer had.
    fake_proxy.install(
        tmp_path,
        rom_hashing="from .helpers import apply_scan_batch_cooldown\n",
        extra={"helpers": "def something_else():\n    pass\n"},
    )
    assert "apply_scan_batch_cooldown" in dependency_error(proxy_dir)


def test_a_syntax_error_is_a_dependency_error(tmp_path, proxy_dir):
    fake_proxy.install(tmp_path, rom_hashing="def broken(:\n")
    assert "SyntaxError" in dependency_error(proxy_dir)


@pytest.mark.parametrize("name", proxy_hasher.REQUIRED_FUNCTIONS)
def test_a_missing_function_is_a_dependency_error(tmp_path, proxy_dir, name):
    fake_proxy.install(tmp_path, rom_hashing=fake_proxy.ROM_HASHING + f"\ndel {name}\n")
    assert name in dependency_error(proxy_dir)


def test_odd_extensions_are_a_dependency_error(tmp_path, proxy_dir):
    source = fake_proxy.ROM_HASHING + "\ndef supported_rom_extensions():\n    return 3\n"
    fake_proxy.install(tmp_path, rom_hashing=source)
    dependency_error(proxy_dir)


def test_a_missing_native_library_is_a_dependency_error(tmp_path, proxy_dir, monkeypatch):
    fake_proxy.install(tmp_path)
    monkeypatch.setenv("FAKE_RCHASH", "missing")
    assert "libraproxy_rchash shared library not found" in dependency_error(proxy_dir)


def test_a_module_from_elsewhere_is_refused(tmp_path, proxy_dir):
    other = tmp_path / "other"
    fake_proxy.install(other)
    sys.path.insert(0, str(other / "App" / "RAOfflineProxy" / "app"))
    importlib.import_module("raofflineproxy.rom_hashing")  # already loaded from another copy
    fake_proxy.install(tmp_path)

    assert "came from" in dependency_error(proxy_dir)


def test_unexpected_proxy_imports_are_logged(tmp_path, proxy_dir, caplog):
    fake_proxy.install(
        tmp_path,
        rom_hashing=fake_proxy.ROM_HASHING + "\nfrom . import helpers\n",
        extra={"helpers": ""},
    )
    load_proxy_hasher(proxy_dir)
    assert "also loaded raofflineproxy.helpers" in caplog.text


def test_hashing_exceptions_are_hash_errors(tmp_path, proxy_dir):
    source = fake_proxy.ROM_HASHING + (
        "\ndef hash_rom_candidates_result(path):\n    raise OSError('I/O error')\n"
        "\ndef list_7z_entries(path):\n    raise MemoryError()\n"
        "\ndef hash_7z_entry_candidates(path, entry_name):\n    return 'not a list'\n"
    )
    fake_proxy.install(tmp_path, rom_hashing=source)
    hasher = load_proxy_hasher(proxy_dir)

    for call in (
        lambda: hasher.hash_file(tmp_path / "game.gba"),
        lambda: hasher.list_7z_entries(tmp_path / "game.7z"),
        lambda: hasher.hash_7z_entry(tmp_path / "game.7z", "game.md"),
    ):
        with pytest.raises(IdentificationError) as error:
            call()
        assert error.value.reason == "hash"


def test_a_changed_result_shape_is_a_hash_error(tmp_path, proxy_dir):
    source = fake_proxy.ROM_HASHING + "\ndef hash_rom_candidates_result(path):\n    return ['a']\n"
    fake_proxy.install(tmp_path, rom_hashing=source)

    with pytest.raises(IdentificationError):
        load_proxy_hasher(proxy_dir).hash_file(tmp_path / "game.gba")
