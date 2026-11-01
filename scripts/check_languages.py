"""Check the translations in ``res/lang`` and write the English template for translators.

For each translation it lists what the app would leave out (and so show in English) and the
strings it doesn't translate yet. ``--template`` writes every string in English, laid out as a
translation file is: copy it to ``src/cheevos/res/lang/<Language>.json`` to start a new one.

Usage: ``python scripts/check_languages.py [--template PATH] [LANGUAGE ...]`` (default: all).
Exits with status 1 when a translation has values the app would leave out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cheevos.platform.desktop import translations
from cheevos.ui import language


def untranslated(data: dict[str, object]) -> list[str]:
    """List the strings a translation doesn't cover yet.

    Args:
        data: The translation file's contents.

    Returns:
        Names, with ``NAME.key`` for a missing entry of a dict of labels.
    """
    missing: list[str] = []
    for name, value in language.english().items():
        given = data.get(name)
        if given in (None, ""):
            missing.append(name)
        elif isinstance(value, dict) and isinstance(given, dict):
            missing.extend(f"{name}.{key}" for key in value if given.get(key) in (None, ""))
    return missing


def check(path: Path) -> bool:
    """Print a translation's problems and coverage.

    Args:
        path: The translation file.

    Returns:
        ``True`` when the app can show every value it has.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"{path.stem}: can't read {path}: {exc}")
        return False
    translations, problems = language.parse(data)
    missing = untranslated(data) if isinstance(data, dict) else []
    print(f"{path.stem}: {len(translations)} of {len(language.english())} strings translated")
    for problem in problems:
        print(f"  left out, shown in English: {problem}")
    if missing:
        print(f"  not translated yet: {', '.join(missing)}")
    return not problems


def main(argv: list[str] | None = None) -> int:
    """Check translations and optionally write the template.

    Args:
        argv: Arguments; ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when every translation is usable as it is, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(prog="python scripts/check_languages.py")
    parser.add_argument("languages", nargs="*", help='e.g. "Catalan" (default: every file)')
    parser.add_argument("--template", type=Path, help="write the English template here")
    args = parser.parse_args(argv)
    if args.template:
        path = translations.write(args.template.parent, args.template.stem, translations.template())
        print(f"English template: {path}")
    names = args.languages or sorted(path.stem for path in language.LANG_DIR.glob("*.json"))
    if not names:
        print(f"No translations in {language.LANG_DIR} yet")
    results = [check(language.LANG_DIR / f"{name}.json") for name in names]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
