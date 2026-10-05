"""The version is in pyproject.toml and ``cheevos.__version__``; releases need both equal."""

import re
from pathlib import Path

import cheevos

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_matches_pyproject():
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    assert match is not None
    assert match.group(1) == cheevos.__version__
