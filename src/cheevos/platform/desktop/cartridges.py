"""Preview Spruce's cartridge view with real labels, without launching an emulator.

The view itself belongs to SpruceOS. This desktop-only harness supplies attributed cartridge
prints for GB/GBC/GBA; it exercises PyUI's real controller, rendering and launch hook. It is
excluded from the Cheevos device package (.agents/code.md, "Package layout").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller.controller import Controller
from controller.controller_inputs import ControllerInput
from views.grid_or_list_entry import GridOrListEntry
from views.view_creator import ViewCreator
from views.view_type import ViewType

REPO = Path(__file__).resolve().parents[4]
ARTWORK = REPO / "assets" / "cartridges"
SHELVES = ("GBA", "GB", "GBC")
SHELF_NAMES = {"GBA": "Game Boy Advance", "GB": "Game Boy", "GBC": "Game Boy Color"}


@dataclass(frozen=True, slots=True)
class PreviewGame:
    """Describe a desktop cartridge without a ROM path or launcher command."""

    title: str
    cartridge_system: str
    image: str | None = None
    cartridge_face: str | None = None


def fixture_games() -> dict[str, list[PreviewGame]]:
    """Read the seven attributed cartridge prints prepared for the desktop demo."""
    games = {system: [] for system in SHELVES}
    manifest = json.loads((ARTWORK / "manifest.json").read_text(encoding="utf-8"))
    for game in manifest["games"]:
        face = ARTWORK / "rendered" / f"{game['id']}.png"
        label = ARTWORK / "rendered" / f"{game['id']}-label.png"
        games[game["system"]].append(
            PreviewGame(game["title"], game["system"], str(label), str(face))
        )
    return games


def _create_view(system: str, games: list[PreviewGame], selected: int) -> Any:  # noqa: ANN401 — PyUI view
    """Create the source checkout's view through PyUI's standard view factory."""
    entries = [
        GridOrListEntry(
            game.title, value=game, image_path=game.image, image_path_selected=game.image
        )
        for game in games
    ]
    return ViewCreator.create_view(
        ViewType.CARTRIDGE,
        entries,
        SHELF_NAMES[system],
        selected_index=selected,
    )


def _hold_inserted(view: Any) -> None:  # noqa: ANN401 — PyUI view
    """Keep the insertion's final frame visible until B returns to the shelf."""
    while True:
        view.render_inserted()
        if Controller.get_input(timeout=1 / 12) and Controller.last_input() == ControllerInput.B:
            return


def run() -> None:
    """Browse with D-pad, Select for console, A to insert and B to return/exit."""
    games = fixture_games()
    shelf = 0
    selections = dict.fromkeys(SHELVES, 0)
    view = _create_view(SHELVES[shelf], games[SHELVES[shelf]], 0)
    try:
        while True:
            result = view.get_selection([ControllerInput.A, ControllerInput.SELECT])
            pressed = result.get_input()
            if pressed == ControllerInput.B:
                return
            if pressed == ControllerInput.SELECT:
                system = SHELVES[shelf]
                selections[system] = result.get_index()
                view.view_finished()
                shelf = (shelf + 1) % len(SHELVES)
                system = SHELVES[shelf]
                view = _create_view(system, games[system], selections[system])
            elif pressed == ControllerInput.A and view.prepare_launch():
                _hold_inserted(view)
    finally:
        view.view_finished()
