import ctypes
import json
import shutil
import struct
import subprocess
import sys

import pytest

from check_proxy_compat import DEFAULT_PROXY, REPO, package_root, proxy_version
from proxy_native import (
    ElfError,
    SimulatedRcHash,
    bound_functions,
    elf_function_exports,
)

FUNC, OBJECT = 2, 1
GLOBAL, LOCAL, WEAK = 1, 0, 2


def build_elf(symbols, *, wide=True, order="<"):
    """A minimal shared object: a null section, .dynsym and its .dynstr."""
    names, entries = b"\0", [(0, 0, 0)]
    for name, info, shndx in symbols:
        entries.append((len(names), info, shndx))
        names += name.encode() + b"\0"
    if wide:
        table = b"".join(struct.pack(order + "IBBHQQ", n, i, 0, s, 0, 0) for n, i, s in entries)
        entsize, header_size, shentsize, shdr = 24, 64, 64, order + "IIQQQQIIQQ"
    else:
        table = b"".join(struct.pack(order + "IIIBBH", n, 0, 0, i, 0, s) for n, i, s in entries)
        entsize, header_size, shentsize, shdr = 16, 52, 40, order + "IIIIIIIIII"
    dynsym, dynstr = 0x100, 0x100 + len(table)
    shoff = (dynstr + len(names) + 7) // 8 * 8
    sections = [
        struct.pack(shdr, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        struct.pack(shdr, 0, 11, 0, 0, dynsym, len(table), 2, 1, 8, entsize),
        struct.pack(shdr, 0, 3, 0, 0, dynstr, len(names), 0, 0, 1, 0),
    ]
    ident = b"\x7fELF" + bytes([2 if wide else 1, 1 if order == "<" else 2, 1]) + bytes(9)
    if wide:
        header = struct.pack(
            order + "HHIQQQIHHHHHH", 3, 183, 1, 0, 0, shoff, 0, header_size, 0, 0, shentsize, 3, 0
        )
    else:
        header = struct.pack(
            order + "HHIIIIIHHHHHH", 3, 40, 1, 0, 0, shoff, 0, header_size, 0, 0, shentsize, 3, 0
        )
    data = bytearray(shoff + shentsize * 3)
    data[: len(ident + header)] = ident + header
    data[dynsym : dynsym + len(table)] = table
    data[dynstr : dynstr + len(names)] = names
    data[shoff:] = b"".join(sections)
    return bytes(data)


SYMBOLS = [
    ("raproxy_hash_file", GLOBAL << 4 | FUNC, 9),
    ("raproxy_weak", WEAK << 4 | FUNC, 9),
    ("raproxy_local", LOCAL << 4 | FUNC, 9),
    ("raproxy_table", GLOBAL << 4 | OBJECT, 9),
    ("malloc", GLOBAL << 4 | FUNC, 0),  # imported, not defined
]


@pytest.mark.parametrize(("wide", "order"), [(True, "<"), (False, "<"), (True, ">"), (False, ">")])
def test_elf_function_exports(tmp_path, wide, order):
    library = tmp_path / "libraproxy_rchash.so"
    library.write_bytes(build_elf(SYMBOLS, wide=wide, order=order))

    assert elf_function_exports(library) == {"raproxy_hash_file", "raproxy_weak"}


def test_non_elf_files_are_refused(tmp_path):
    library = tmp_path / "libraproxy_rchash.dylib"
    library.write_bytes(b"\xcf\xfa\xed\xfe" + bytes(60))
    with pytest.raises(ElfError):
        elf_function_exports(library)


def test_bound_functions_reads_the_wrappers_ctypes_calls():
    source = (
        "library.raproxy_hash_file.argtypes = [...]\n"
        "count = library.raproxy_hash_7z_entry(path, name, buffer, 8)\n"
        "other.raproxy_not_ours()\n"
    )
    assert bound_functions(source) == {"raproxy_hash_file", "raproxy_hash_7z_entry"}


def test_simulated_hashes_use_rc_hashs_buffer_layout(tmp_path):
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"cart")
    buffer = ctypes.create_string_buffer(8 * 33)

    count = SimulatedRcHash().raproxy_hash_file(str(rom).encode(), buffer, 8)

    assert count == 2
    chunks = [buffer.raw[i * 33 : (i + 1) * 33] for i in range(count)]
    assert all(len(chunk.split(b"\0")[0]) == 32 and chunk[32] == 0 for chunk in chunks)


@pytest.mark.parametrize(
    ("layout", "root"),
    [
        ("App/RAOfflineProxy/app/raofflineproxy", "App/RAOfflineProxy/app"),
        ("repo/linux/raofflineproxy", "repo/linux"),
        ("package/raofflineproxy", "package"),
    ],
)
def test_finds_the_package_in_bundles_and_checkouts(tmp_path, layout, root):
    (tmp_path / layout).mkdir(parents=True)
    (tmp_path / layout / "rom_hashing.py").touch()
    given = {"App/RAOfflineProxy/app": "App/RAOfflineProxy", "repo/linux": "repo"}.get(root, root)

    assert package_root(tmp_path / given) == tmp_path / root
    assert package_root(tmp_path / layout) == tmp_path / root


def test_reads_the_version_from_a_bundle_or_the_package(tmp_path):
    bundle = tmp_path / "App" / "RAOfflineProxy"
    (bundle / "app" / "raofflineproxy").mkdir(parents=True)
    (bundle / "common.sh").write_text("APP_DIR=x\nAPP_VERSION=v2.2.0-alpha1-nightly.54\n")
    assert proxy_version(bundle, bundle / "app") == "2.2.0-alpha1-nightly.54"

    config = tmp_path / "linux" / "raofflineproxy" / "config.py"
    config.parent.mkdir(parents=True)
    config.write_text('APP_VERSION = os.environ.get("X") or "2.3.0"\n')
    assert proxy_version(tmp_path / "linux", tmp_path / "linux") == "2.3.0"


# --- against the fetched bundle (make proxy; CI fetches it before the tests) -------------------

needs_bundle = pytest.mark.skipif(
    not (DEFAULT_PROXY / "app" / "raofflineproxy" / "rom_hashing.py").is_file(),
    reason="no RAOfflineProxy bundle: run `make proxy`",
)


def run_check(proxy, tmp_path):
    report = tmp_path / "report.json"
    process = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "check_proxy_compat.py"),
            str(proxy),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return process, json.loads(report.read_text()) if report.exists() else None


@pytest.fixture
def bundle_copy(tmp_path):
    copy = tmp_path / "RAOfflineProxy"
    shutil.copytree(DEFAULT_PROXY, copy, ignore=shutil.ignore_patterns("__pycache__", "data"))
    return copy


def edit(bundle, module, old, new):
    path = bundle / "app" / "raofflineproxy" / f"{module}.py"
    source = path.read_text()
    assert old in source, f"{module}.py changed: update this test"
    path.write_text(source.replace(old, new, 1))


@pytest.mark.proxy
@needs_bundle
def test_the_pinned_bundle_is_compatible(tmp_path):
    process, report = run_check(DEFAULT_PROXY, tmp_path)

    assert process.returncode == 0, process.stdout + process.stderr
    assert report["version"]
    assert len(report["source_commit"]) == 40
    assert set(report["checks"]) == {"api", "archive rules", "cache reader"}
    assert report["libraries"]  # both architectures' exports were read


@pytest.mark.proxy
@needs_bundle
@pytest.mark.parametrize(
    ("module", "old", "new", "check"),
    [
        # A renamed wrapper function.
        ("rom_hashing", "def list_7z_entries(", "def list_seven_zip_entries(", "api"),
        # The wrapper starts importing more of the proxy.
        ("rom_hashing", "import ctypes\n", "import ctypes\nfrom . import storage\n", "api"),
        # The proxy's own archive rule changes: several ROMs no longer refuse.
        (
            "rom_browser",
            'raise ValueError("archive contains multiple supported ROMs")',
            "rom_entries = rom_entries[:1]",
            "archive",
        ),
        # The cache key format changes.
        ("cache_keys", 'return f"gameid:{', 'return f"game-id:{', "cache"),
    ],
)
def test_changes_are_caught(tmp_path, bundle_copy, module, old, new, check):
    edit(bundle_copy, module, old, new)

    process, report = run_check(bundle_copy, tmp_path)

    assert process.returncode == 1
    failing = [name for name, problems in report["checks"].items() if problems]
    assert any(name.startswith(check) for name in failing), process.stdout


@pytest.mark.proxy
@needs_bundle
def test_a_new_native_binding_must_be_exported(tmp_path, bundle_copy):
    edit(
        bundle_copy,
        "rom_hashing",
        "library.raproxy_hash_file.restype = ctypes.c_int",
        "library.raproxy_hash_file.restype = ctypes.c_int\n"
        "            library.raproxy_hash_patch.restype = ctypes.c_int",
    )

    process, report = run_check(bundle_copy, tmp_path)

    assert process.returncode == 1
    assert all(missing == ["raproxy_hash_patch"] for missing in report["libraries"].values())
