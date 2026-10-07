"""Export the repository's user guide with GitHub wiki page links.

Keep relative ``.md`` links in ``docs/`` so they work when browsing the repository.
The export removes that extension from links to guide pages and copies the images.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
OUTPUT = REPO / "build" / "wiki"


def build(output: Path = OUTPUT) -> Path:
    """Rebuild the wiki export without changing the source guide.

    Args:
        output: Export directory; it is replaced if it exists.

    Returns:
        The export directory, ready to copy into a wiki checkout.
    """
    pages = sorted(DOCS.glob("*.md"))
    page_names = "|".join(re.escape(page.name) for page in pages)
    page_links = re.compile(r"(?<=\]\()(?:" + page_names + r")(?=[)#?])")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(DOCS, output)
    for page in pages:
        content = page.read_text(encoding="utf-8")
        content = page_links.sub(lambda match: match.group().removesuffix(".md"), content)
        (output / page.name).write_text(content, encoding="utf-8")
    return output


def main() -> int:
    """Export the guide and print where it went."""
    output = build()
    print(f"Built {output.relative_to(REPO)}; copy its contents into your wiki checkout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
