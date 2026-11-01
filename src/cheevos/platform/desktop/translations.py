"""Language files for development: the English template, and the pseudo-language.

The template is every string in English, laid out as a translation file is (``make languages``
writes it for translators to copy). The pseudo-language is English with accented letters,
longer words and brackets, so screens rendered in it (``make screens UI_LANGUAGE=Pseudo``) show
text a translation can't reach (no brackets), text cut short (no closing bracket) and text that
runs into its neighbours in a longer language. Numbers use Catalan's separators.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from cheevos.ui import language, strings

PSEUDO = "Pseudo"

# Vowels doubled (English text gets about 40% longer, as German or Catalan does) and accented;
# the SPRUCE theme's font has every one of these letters.
_PSEUDO_LETTERS = str.maketrans(
    {
        "a": "áá",
        "e": "éé",
        "i": "íí",
        "o": "óó",
        "u": "úú",
        "A": "Á",
        "E": "É",
        "I": "Í",
        "O": "Ó",
        "U": "Ú",
        "c": "ç",
        "n": "ñ",
        "s": "š",
        "y": "ý",
    }
)
_PSEUDO_NUMBERS = {"THOUSANDS_SEPARATOR": ".", "DECIMAL_SEPARATOR": ","}


def to_json(value: language.Value) -> object:
    """Write a string's value as a translation file holds it.

    Args:
        value: A value from :mod:`cheevos.ui.strings`.

    Returns:
        Text, a list, or an object (plural forms, or labels by key).
    """
    if isinstance(value, strings.Plural):
        forms = {"one": value.one, "few": value.few, "many": value.many, "other": value.other}
        return {form: text for form, text in forms.items() if text is not None}
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def template() -> dict[str, object]:
    """Return every string in English, as a translation file lays them out.

    Returns:
        Values by name, in the order ``strings`` defines them.
    """
    return {name: to_json(value) for name, value in language.english().items()}


def pseudo_text(text: str) -> str:
    """Turn English into the pseudo-language, keeping its ``{fields}`` as they are.

    Args:
        text: An English template.

    Returns:
        E.g. ``"[Sýñç]"`` for ``"Sync"``; text without letters stays as it is.
    """
    parts: list[str] = []
    words = False  # "{percent}%" has none of its own: it stays as it is
    for literal, name, spec, _conversion in string.Formatter().parse(text):
        words = words or any(char.isalpha() for char in literal)
        parts.append(literal.replace("{", "{{").replace("}", "}}").translate(_PSEUDO_LETTERS))
        if name is not None:
            parts.append(f"{{{name}:{spec}}}" if spec else f"{{{name}}}")
    pseudo = "".join(parts)
    return f"[{pseudo}]" if words else pseudo


def _pseudo_value(value: object) -> object:
    """Turn a translation file's value into the pseudo-language.

    Args:
        value: Text, a list, or an object of texts.

    Returns:
        The same shape, in the pseudo-language.
    """
    if isinstance(value, str):
        return pseudo_text(value)
    if isinstance(value, list):
        return [pseudo_text(item) for item in value]
    if isinstance(value, dict):
        return {key: pseudo_text(text) for key, text in value.items()}
    return value


def pseudo() -> dict[str, object]:
    """Return the pseudo-language's translation file.

    Returns:
        Every string, in the pseudo-language.
    """
    translated = {name: _pseudo_value(value) for name, value in template().items()}
    return translated | _PSEUDO_NUMBERS


def write(directory: Path, name: str, content: dict[str, object]) -> Path:
    """Write a translation file as translators keep them: UTF-8, indented, not escaped.

    Args:
        directory: Where to write it.
        name: The language.
        content: Values by name.

    Returns:
        The file's path.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(content, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return path
