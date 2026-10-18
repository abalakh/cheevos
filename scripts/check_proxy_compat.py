"""Check that an RAOfflineProxy build still offers what ROM identification uses.

Usage::

    python scripts/check_proxy_compat.py [PROXY] [--source-commit SHA] [--report FILE]

``PROXY`` is a Spruce bundle (``App/RAOfflineProxy``), an upstream checkout (the repository or
its ``linux/`` directory) or the ``raofflineproxy`` package. The default is the bundle that
``make proxy`` fetches into ``.spruceos-proxy/`` at ``proxy-tested-commit``.

The checks use the proxy's real Python modules, imported from a copy without its native
libraries, so nothing built for a device is loaded here:

1. ``rom_hashing`` imports alone and has the functions the adapter calls
   (``cheevos.platform.proxy_hasher``), with compatible signatures.
2. The adapter and Cheevos' archive rules give the same candidates as the proxy's own
   ``rom_browser.hash_candidates_for_manual_cache``, for plain, ZIP and 7z fixtures, with
   the native library simulated (``proxy_native.SimulatedRcHash``).
3. The read-only cache reader understands what the proxy's ``Storage`` writes.
4. Each bundled ``lib/<arch>/libraproxy_rchash.so`` exports every function the wrapper binds.

It prints the proxy's version and source commit and exits 1 if anything changed. Real hashing
is tested on a device (TESTING.md, "RAOfflineProxy compatibility").
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import ModuleType

from cheevos.core.identification.candidates import hash_candidates
from cheevos.core.identification.hash_lookup import CachedAnswer, ProxyHashCache
from cheevos.core.identification.result import IdentificationError
from cheevos.platform import proxy_hasher
from proxy_native import ElfError, SimulatedRcHash, bound_functions, elf_function_exports

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PROXY = REPO / ".spruceos-proxy" / "App" / "RAOfflineProxy"
_VERSION = re.compile(r"""^\s*(?:APP_VERSION=|APP_VERSION = .*?or )["']?v?([^"'\s]+)""", re.M)
# How the adapter calls each function: positional arguments that must bind to its signature.
CALLS: dict[str, tuple[object, ...]] = {
    "load_rchash": (),
    "hash_rom_candidates_result": (Path("rom"),),
    "list_7z_entries": (Path("rom.7z"),),
    "hash_7z_entry_candidates": (Path("rom.7z"), "entry"),
    "supported_rom_extensions": (),
}
# Fixtures for the parity check: file name -> ZIP entries (dict), simulated 7z (JSON), or bytes.
FIXTURES: dict[str, dict[str, bytes] | bytes] = {
    "plain.gba": b"plain cartridge",
    "single.zip": {"Game (USA).gba": b"zipped cartridge"},
    "no-extension.zip": {"game": b"unknown system"},
    "with-readme.zip": {"game.sfc": b"snes cartridge", "readme.txt": b"notes"},
    "hidden.zip": {"__MACOSX/._game.gba": b"fork", "game.gba": b"real cartridge"},
    "in-folder.zip": {"Game/game.nes": b"nes cartridge"},
    "two-roms.zip": {"a.gba": b"one", "b.gba": b"two"},
    "arcade.zip": {"set.p1": b"program", "set.c1": b"graphics"},
    "not-a-zip.zip": b"this is not an archive",
    "disc.chd": b"compressed disc",
    "single.7z": json.dumps({"game.md": "zipped megadrive"}).encode(),
    "unreadable.7z": json.dumps({"game.md": "!unreadable"}).encode(),
    "two-roms.7z": json.dumps({"a.md": "one", "b.md": "two"}).encode(),
    "arcade.7z": json.dumps({"set.p1": "a", "set.c1": "b"}).encode(),
}


@dataclass
class Report:
    """What was checked, for the terminal and ``--report``.

    Attributes:
        proxy: The checked path.
        version: The proxy's version, if found.
        source_commit: The checkout's commit, if known.
        checks: Check name -> problems (empty when it passed).
        libraries: Bundled library -> missing exports.
    """

    proxy: str
    version: str | None = None
    source_commit: str | None = None
    checks: dict[str, list[str]] = field(default_factory=dict)
    libraries: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Report whether every check passed."""
        return not any(self.checks.values()) and not any(self.libraries.values())


def package_root(proxy: Path) -> Path:
    """Find the directory holding the ``raofflineproxy`` package.

    Args:
        proxy: A bundle, an upstream checkout, its ``linux/`` directory or the package.

    Returns:
        The package's parent directory.

    Raises:
        FileNotFoundError: No ``raofflineproxy`` package there.
    """
    for root in (proxy / "app", proxy / "linux", proxy, proxy.parent):
        if (root / proxy_hasher.PACKAGE / "rom_hashing.py").is_file():
            return root
    raise FileNotFoundError(f"no raofflineproxy package under {proxy}")


def proxy_version(proxy: Path, root: Path) -> str | None:
    """Read the version from a bundle's ``common.sh`` or the package's ``config.py``."""
    for source in (proxy / "common.sh", root / proxy_hasher.PACKAGE / "config.py"):
        try:
            found = _VERSION.search(source.read_text(encoding="utf-8"))
        except OSError:
            continue
        if found:
            return found.group(1)
    return None


def source_commit(proxy: Path) -> str | None:
    """Return the git commit of the checkout holding ``proxy``, if it is one."""
    try:
        result = subprocess.run(  # noqa: S603 — fixed git command on a developer's path
            ["git", "-C", str(proxy), "rev-parse", "HEAD"],  # noqa: S607 — git from PATH
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def check_api(module: ModuleType) -> list[str]:
    """Check the adapter's API checks, signatures and the modules ``rom_hashing`` loads."""
    problems: list[str] = []
    try:
        proxy_hasher.check_api(module)
    except IdentificationError as exc:
        return [str(exc)]
    for name, arguments in CALLS.items():
        try:
            inspect.signature(getattr(module, name)).bind(*arguments)
        except TypeError as exc:
            problems.append(f"{name}{inspect.signature(getattr(module, name))}: {exc}")
    loaded = {name for name in sys.modules if name.startswith(proxy_hasher.PACKAGE)}
    if extra := sorted(loaded - proxy_hasher.EXPECTED_MODULES):
        problems.append(f"importing rom_hashing also loads {', '.join(extra)}")
    return problems


def _write_fixtures(directory: Path) -> list[Path]:
    """Create the parity fixtures."""
    files = []
    for name, content in FIXTURES.items():
        path = directory / name
        if isinstance(content, dict):
            with zipfile.ZipFile(path, "w") as archive:
                for entry, data in content.items():
                    archive.writestr(entry, data)
        else:
            path.write_bytes(content)
        files.append(path)
    return files


def _outcome(call: Callable[[], Iterable[str]]) -> list[str] | str:
    """Return candidates as a list, or ``"error"`` for no candidates or an exception."""
    try:
        candidates = list(call())
    except Exception:  # noqa: BLE001 — either side may fail in its own way: compare only that
        return "error"
    return candidates or "error"


def check_parity(module: ModuleType, scratch: Path) -> list[str]:
    """Compare Cheevos' candidates with ``rom_browser``'s, over a simulated native library."""
    simulated = SimulatedRcHash()
    # rom_hashing's functions look the library up at call time, through this function.
    setattr(module, "load_rchash", lambda: simulated)  # noqa: B010 — a module attribute
    try:
        rom_browser = importlib.import_module("raofflineproxy.rom_browser")
    except Exception as exc:  # noqa: BLE001 — report any import failure as a finding
        return [f"rom_browser does not import: {exc!r}"]
    reference = getattr(rom_browser, "hash_candidates_for_manual_cache", None)
    if reference is None:
        return ["rom_browser.hash_candidates_for_manual_cache is gone: review the archive rules"]
    hasher = proxy_hasher.ProxyHasher(module, proxy_hasher.check_api(module))
    fixtures = scratch / "fixtures"
    fixtures.mkdir()
    problems = []
    for path in _write_fixtures(fixtures):
        theirs = _outcome(lambda path=path: reference(path))
        ours = _outcome(lambda path=path: hash_candidates(path, hasher, scratch / "work"))
        if theirs != ours:
            problems.append(f"{path.name}: rom_browser gives {theirs}, Cheevos gives {ours}")
    if leftovers := list((scratch / "work").glob("rom-hash-*")):
        problems.append(f"extraction left {leftovers}")
    return problems


def check_cache(scratch: Path) -> list[str]:
    """Write entries with the proxy's ``Storage`` and read them back read-only."""
    cache_keys = importlib.import_module("raofflineproxy.cache_keys")
    storage_module = importlib.import_module("raofflineproxy.storage")

    database = scratch / "config" / "proxy.sqlite3"  # Storage creates its config directory
    storage = storage_module.Storage(database)
    matched, sets, missed = "a" * 32, "b" * 32, "c" * 32
    try:
        storage.upsert_cache(cache_keys.game_id(matched), '{"Success":true,"GameID":1479}')
        storage.upsert_cache(cache_keys.achievementsets(sets, "Player"), '{"GameId":228}')
        storage.upsert_cache(cache_keys.game_id(missed), '{"Success":true,"GameID":0}')
    finally:
        storage.close()
    reader = ProxyHashCache(database, now=lambda: storage_module.current_millis() / 1000)
    try:
        answers = {value: reader.lookup(value) for value in (matched, sets, missed)}
    finally:
        reader.close()
    expected = {
        matched: CachedAnswer(game_id=1479),
        sets: CachedAnswer(game_id=228),
        missed: CachedAnswer(miss=True),
    }
    return [
        f"{value}: read {answers[value]}, expected {answer}"
        for value, answer in expected.items()
        if answers[value] != answer
    ]


def check_libraries(proxy: Path, root: Path) -> dict[str, list[str]]:
    """Check each bundled native library's exports against the wrapper's bindings.

    Args:
        proxy: The checked path.
        root: Its package root; ``<proxy>/app`` for a Spruce bundle, which must ship libraries.

    Returns:
        Library path -> missing exports. Source checkouts have no libraries to check.
    """
    wrapper = root / proxy_hasher.PACKAGE / "rom_hashing.py"
    required = bound_functions(wrapper.read_text(encoding="utf-8"))
    results: dict[str, list[str]] = {}
    if root == proxy / "app" and not any(proxy.glob("lib/*/libraproxy_rchash.so")):
        return {"lib/<arch>/libraproxy_rchash.so": ["not bundled"]}
    for library in sorted(proxy.glob("lib/*/libraproxy_rchash.so")):
        name = str(library.relative_to(proxy))
        try:
            results[name] = sorted(required - elf_function_exports(library))
        except (OSError, ElfError) as exc:
            results[name] = [f"unreadable: {exc}"]
    return results


def check(proxy: Path, commit: str | None = None) -> Report:
    """Run every check against one proxy build.

    Args:
        proxy: A bundle, an upstream checkout or the package.
        commit: The source commit, when it isn't the git checkout's own.

    Returns:
        The report.
    """
    root = package_root(proxy)
    report = Report(
        proxy=str(proxy),
        version=proxy_version(proxy, root),
        source_commit=commit or source_commit(proxy),
    )
    with tempfile.TemporaryDirectory(prefix="proxy-compat-") as temp:
        scratch = Path(temp)
        # A copy without lib/: the wrapper can't find (and must never load) device libraries.
        copy = scratch / "app"
        shutil.copytree(
            root / proxy_hasher.PACKAGE,
            copy / proxy_hasher.PACKAGE,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        os.environ["RAOFFLINEPROXY_CONFIG_DIR"] = str(scratch / "config")
        os.environ.pop("RAOFFLINEPROXY_RCHASH_LIB", None)
        try:
            module = proxy_hasher.import_hashing_module(copy)
        except IdentificationError as exc:
            report.checks["api"] = [str(exc)]
            return report
        report.checks["api"] = check_api(module)
        report.checks["archive rules"] = check_parity(module, scratch)
        report.checks["cache reader"] = check_cache(scratch)
    report.libraries = check_libraries(proxy, root)
    return report


def _print(report: Report) -> None:
    """Print the report for a terminal or CI log."""
    print(f"RAOfflineProxy {report.version or '(unknown version)'} at {report.proxy}")
    print(f"Source commit: {report.source_commit or 'unknown'}")
    for name, problems in report.checks.items():
        print(f"  {'ok  ' if not problems else 'FAIL'} {name}")
        for problem in problems:
            print(f"         {problem}")
    if not report.libraries:
        print("  --   native exports: no bundled lib/<arch>/libraproxy_rchash.so here")
    for name, missing in report.libraries.items():
        status = "ok  " if not missing else "FAIL"
        print(f"  {status} {name}{': missing ' + ', '.join(missing) if missing else ''}")


def main(argv: list[str] | None = None) -> int:
    """Check one proxy build.

    Returns:
        0 when compatible, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("proxy", nargs="?", type=Path, default=DEFAULT_PROXY)
    parser.add_argument("--source-commit", help="record this commit instead of git's HEAD")
    parser.add_argument("--report", type=Path, help="also write the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = check(args.proxy.resolve(), args.source_commit)
    except FileNotFoundError as exc:
        print(f"{exc}. Run `make proxy`, or pass a checkout or bundle.", file=sys.stderr)
        return 1
    _print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    print("Compatible." if report.ok else "INCOMPATIBLE: update the adapter or keep the old proxy.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
