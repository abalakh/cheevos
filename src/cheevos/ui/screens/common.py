"""Building blocks shared by screens: message pages, option pickers, full-screen images."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from cheevos.ui import strings
from cheevos.ui.pyui import primitives as ui
from cheevos.ui.pyui.primitives import Align, Button, Text
from cheevos.ui.pyui.views import Layout, MenuItem, choose

PADDING = 16


def message(title: str, paragraphs: Sequence[str]) -> None:
    """Show wrapped, centred paragraphs until A or B is pressed.

    Args:
        title: Top-bar text.
        paragraphs: Text blocks, separated by a blank gap.
    """
    while True:
        area = ui.begin(title, hints=[(Button.A, strings.HINT_OK)])
        y = area.y + PADDING * 2
        for paragraph in paragraphs:
            for line in ui.wrap(paragraph, Text.BODY, area.width - PADDING * 4):
                ui.text(line, area.width // 2, y, align=Align.TOP_CENTER)
                y += ui.line_height(Text.BODY)
            y += PADDING
        ui.end()
        if ui.wait_for({Button.A, Button.B}):
            return


def busy(title: str, text: str) -> None:
    """Draw a single "working…" frame (no input wait) before a blocking operation.

    Args:
        title: Top-bar text.
        text: What is happening.
    """
    area = ui.begin(title)
    ui.text(text, area.width // 2, area.y + area.height // 2, align=Align.MIDDLE_CENTER)
    ui.end()


def pick(title: str, options: Mapping[str, str], current: str) -> str | None:
    """Let the user pick one option from a popup menu.

    Args:
        title: Popup title.
        options: Option key to label, in display order.
        current: Key of the current option (pre-selected).

    Returns:
        The chosen key, or ``None`` if the user backed out.
    """
    keys = list(options)
    items = [MenuItem(label, key=key) for key, label in options.items()]
    selected = keys.index(current) if current in keys else 0
    choice = choose(title, items, selected=selected, layout=Layout.POPUP)
    return None if choice is None else choice.item.key


def fullscreen(path: Path, scratch: Path) -> None:
    """Show an image over the whole screen, without bars, until A or B is pressed.

    Pixel art stays sharp: it is enlarged by a whole factor first (see ``sharp_scaled``).

    Args:
        path: Image path.
        scratch: Directory for the enlarged copy.
    """
    while True:
        area = ui.begin_bare()
        shown = ui.sharp_scaled(path, area.width, area.height, scratch)
        center_x, center_y = area.width // 2, area.height // 2
        ui.image(shown, center_x, center_y, area.width, area.height, Align.MIDDLE_CENTER)
        ui.end()
        if ui.wait_for({Button.A, Button.B}):
            return
