"""Enforce the conventions ruff cannot express (see .agents/code.md).

Checks:
    CV001  module longer than the soft cap (500 lines) without an allow marker
    CV002  module longer than the hard cap (800 lines)
    CV003  function, method or class without a docstring (private and nested ones included;
           ``__init__`` is documented on the class; tests are exempt)
    CV004  PyUI or sdl2 imported outside the bridge (``cheevos.ui.pyui``) and desktop runner
    CV005  ``cheevos.core`` importing ``cheevos.ui``
    CV006  ``cheevos.platform.desktop`` imported from code that ships to devices
    CV007  a user-facing string read at import time, which would stay English (strings are
           translated when a session starts)

Usage: ``python scripts/check_conventions.py [PATH ...]`` (defaults: src scripts tests).
Exits with status 1 when any violation is found.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

SOFT_CAP = 500
HARD_CAP = 800
ALLOW_MARKER = re.compile(r"#\s*conventions:\s*allow-long-module\s*[—-]+\s*\S")
MARKER_SEARCH_LINES = 5

# PyUI's top-level modules and packages (App/PyUI/main-ui), which become importable once
# main-ui is on sys.path.
PYUI_TOP_LEVEL = frozenset(
    {
        "apps",
        "audio",
        "controller",
        "devices",
        "display",
        "games",
        "mainui",
        "menus",
        "option_select_ui",
        "themes",
        "utils",
        "views",
    }
)
SDL_TOP_LEVEL = frozenset({"sdl2"})
PYUI_ALLOWED_PACKAGES = ("cheevos.ui.pyui", "cheevos.platform.desktop")
DESKTOP_PACKAGE = "cheevos.platform.desktop"
STRINGS_MODULE = "cheevos.ui.strings"
# The strings module itself, and the module that replaces its values with a translation.
STRINGS_OWNERS = frozenset({STRINGS_MODULE, "cheevos.ui.language"})
DEFAULT_PATHS = ("src", "scripts", "tests")


@dataclass(frozen=True, slots=True)
class Violation:
    """One convention violation.

    Attributes:
        path: File containing the violation.
        line: 1-based line number.
        code: Check code, e.g. ``"CV003"``.
        message: Human-readable description.
    """

    path: Path
    line: int
    code: str
    message: str

    def __str__(self) -> str:
        """Format as ``path:line: CODE message``."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def module_name(path: Path) -> str | None:
    """Return the dotted module name for a file under ``src/``, or ``None`` elsewhere.

    Args:
        path: Python file path.

    Returns:
        E.g. ``"cheevos.core.models"`` for ``src/cheevos/core/models.py``.
    """
    parts = path.with_suffix("").parts
    if "src" not in parts:
        return None
    dotted = parts[parts.index("src") + 1 :]
    if dotted and dotted[-1] == "__init__":
        dotted = dotted[:-1]
    return ".".join(dotted) or None


def is_test_file(path: Path) -> bool:
    """Report whether ``path`` belongs to the test suite.

    Args:
        path: Python file path.

    Returns:
        ``True`` for files under a ``tests`` directory.
    """
    return "tests" in path.parts


def check_size(path: Path, lines: list[str]) -> Iterator[Violation]:
    """Check the module length caps.

    Args:
        path: File being checked.
        lines: The file's lines.

    Yields:
        CV001/CV002 violations.
    """
    count = len(lines)
    if count > HARD_CAP:
        yield Violation(path, 1, "CV002", f"{count} lines exceeds the hard cap of {HARD_CAP}")
    elif count > SOFT_CAP:
        head = lines[:MARKER_SEARCH_LINES]
        if not any(ALLOW_MARKER.search(line) for line in head):
            yield Violation(
                path,
                1,
                "CV001",
                f"{count} lines exceeds the soft cap of {SOFT_CAP}; split the module or add "
                "'# conventions: allow-long-module — <reason>' in its first lines",
            )


def check_docstrings(path: Path, tree: ast.Module) -> Iterator[Violation]:
    """Require docstrings on every function, method and class except ``__init__``.

    Args:
        path: File being checked.
        tree: Parsed module.

    Yields:
        CV003 violations.
    """
    definitions = (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    for node in sorted(definitions, key=lambda definition: definition.lineno):
        if node.name == "__init__" or ast.get_docstring(node) is not None:
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        yield Violation(path, node.lineno, "CV003", f"{kind} {node.name!r} has no docstring")


def imported_modules(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """List absolute imports in a module.

    Args:
        tree: Parsed module.

    Yields:
        ``(line, dotted module name)`` for each ``import`` / ``from ... import``.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module


def _within(module: str, package: str) -> bool:
    """Report whether dotted ``module`` is ``package`` or inside it.

    Args:
        module: Dotted module name.
        package: Dotted package name.

    Returns:
        ``True`` if ``module`` equals ``package`` or is a submodule of it.
    """
    return module == package or module.startswith(package + ".")


def check_layers(path: Path, tree: ast.Module) -> Iterator[Violation]:
    """Check the import rules between packages.

    Args:
        path: File being checked (only files under ``src/cheevos`` are subject to the rules).
        tree: Parsed module.

    Yields:
        CV004/CV005/CV006 violations.
    """
    owner = module_name(path)
    if owner is None or not _within(owner, "cheevos"):
        return
    may_use_pyui = any(_within(owner, package) for package in PYUI_ALLOWED_PACKAGES)
    for line, imported in imported_modules(tree):
        top = imported.split(".", 1)[0]
        if top in PYUI_TOP_LEVEL | SDL_TOP_LEVEL and not may_use_pyui:
            yield Violation(
                path, line, "CV004", f"{imported!r} may only be imported in the PyUI bridge"
            )
        if _within(owner, "cheevos.core") and _within(imported, "cheevos.ui"):
            yield Violation(path, line, "CV005", "cheevos.core must not depend on cheevos.ui")
        if _within(imported, DESKTOP_PACKAGE) and not _within(owner, DESKTOP_PACKAGE):
            yield Violation(
                path, line, "CV006", "the desktop runner is dev-only and must not be imported here"
            )


def _import_time_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """List a node and the nodes inside it that Python evaluates when the module is imported.

    Function and lambda bodies run later; their decorators and default values don't.

    Args:
        node: A module, or a node inside one.

    Yields:
        Every node evaluated at import time.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        evaluated: list[ast.expr] = [*node.args.defaults, *filter(None, node.args.kw_defaults)]
        if not isinstance(node, ast.Lambda):
            evaluated.extend(node.decorator_list)
        for expression in evaluated:
            yield from _import_time_nodes(expression)
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _import_time_nodes(child)


def check_import_time_strings(path: Path, tree: ast.Module) -> Iterator[Violation]:
    """Require user-facing strings to be read when they are shown, not at import.

    A session applies its translation after the app's modules are imported, so a string kept
    in a module constant, a default value or a class attribute would stay English.

    Args:
        path: File being checked (only files under ``src/cheevos`` are subject to the rule).
        tree: Parsed module.

    Yields:
        CV007 violations.
    """
    owner = module_name(path)
    if owner is None or not _within(owner, "cheevos") or owner in STRINGS_OWNERS:
        return
    for node in _import_time_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == STRINGS_MODULE:
            yield Violation(
                path,
                node.lineno,
                "CV007",
                "import the strings module and read strings.NAME when the text is shown",
            )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "strings"
            and node.attr.isupper()
        ):
            yield Violation(
                path,
                node.lineno,
                "CV007",
                f"strings.{node.attr} is read at import time and would stay English; "
                "read it inside a function",
            )


def check_file(path: Path) -> list[Violation]:
    """Run every check on one Python file.

    Args:
        path: Python file path.

    Returns:
        Violations found, in check order.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations = list(check_size(path, source.splitlines()))
    if not is_test_file(path):
        violations.extend(check_docstrings(path, tree))
    violations.extend(check_layers(path, tree))
    violations.extend(check_import_time_strings(path, tree))
    return violations


def python_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Expand files and directories into Python files, skipping caches.

    Args:
        paths: Files or directories.

    Yields:
        ``.py`` files in sorted order per directory.
    """
    for path in paths:
        if path.is_dir():
            yield from sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.suffix == ".py":
            yield path


def main(argv: list[str] | None = None) -> int:
    """Check the given paths and print violations.

    Args:
        argv: Paths to check; ``None`` reads ``sys.argv`` (defaults when empty).

    Returns:
        ``0`` when clean, ``1`` when violations were found.
    """
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(arg) for arg in args] or [Path(p) for p in DEFAULT_PATHS if Path(p).exists()]
    violations = [v for file in python_files(paths) for v in check_file(file)]
    for violation in violations:
        print(violation)
    if violations:
        print(f"{len(violations)} convention violation(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
