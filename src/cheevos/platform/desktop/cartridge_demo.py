"""Record the real PyUI cartridge view as a small, attributed concept demo.

Render the same scroll and insertion states the interactive view uses at fixed time samples.
The output includes an animated GIF, PNG frames, an FFmpeg timeline and sharing notes.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from cheevos.platform.desktop import __main__ as desktop

REPO = Path(__file__).resolve().parents[4]
FRAME_MS = 20
SCROLL_FRAMES = 12


class Recorder:
    """Capture a deterministic walk through each system's real cartridge view.

    Args:
        output: Folder for the GIF and its editable frame sequence.
    """

    def __init__(self, output: Path) -> None:
        self.output = output
        self.frames = output / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        self.durations: list[int] = []

    def shot(self, duration: int = FRAME_MS) -> None:
        """Capture the frame just presented by PyUI, with its intended duration."""
        from cheevos.platform.desktop.capture import capture_frame

        capture_frame(self.frames / f"{len(self.durations):03d}.png")
        self.durations.append(duration)

    def card(self, lines: list[str], duration: int) -> None:
        """Draw a demo title or credit card using the actual theme fonts."""
        from display.display import Display
        from display.font_purpose import FontPurpose
        from display.render_mode import RenderMode
        from themes.theme import Theme

        purpose = FontPurpose.DESCRIPTIVE_LIST_DESCRIPTION
        Display.clear("SpruceOS", bottom_bar_text="Desktop UI concept")
        height = Display.get_line_height(purpose)
        y = (480 - height * len(lines)) // 2
        for line in lines:
            Display.render_text(
                line, 320, y, Theme.text_color(purpose), purpose, RenderMode.TOP_CENTER_ALIGNED
            )
            y += height
        Display.present()
        self.shot(duration)

    def scroll(self, view: Any, amount: int) -> None:  # noqa: ANN401 — PyUI view
        """Sample the view's own elapsed-time carousel motion."""
        view.adjust_selected(amount)
        for index in range(1, SCROLL_FRAMES + 1):
            view._moved_at = time.monotonic() - index / SCROLL_FRAMES * 0.22
            view._render()
            self.shot()
        view._render()
        self.shot(550)

    def insert(self, view: Any) -> None:  # noqa: ANN401 — PyUI view
        """Sample the view's actual insertion draw states and hold its final frame."""
        from views.cartridge_geometry import INSERT_SECONDS

        frames = round(INSERT_SECONDS * 1000 / FRAME_MS)
        for index in range(frames):
            view._render(index / frames)
            self.shot()
        view.render_inserted()
        self.shot(600)

    def run(self) -> None:
        """Record seven games across the three shelves and include the asset credits."""
        from controller.controller import Controller
        from themes.theme import Theme

        from cheevos.platform.desktop import cartridges

        # Keep the demo's clock out of the title cards; only the in-memory theme changes.
        Theme._data["showClock"] = False
        self.card(["Cartridge carousel", "Game Boy / Game Boy Color / Game Boy Advance"], 1400)
        games = cartridges.fixture_games()
        for system in ("GBA", "GB", "GBC"):
            view = cartridges._create_view(system, games[system], 0)
            try:
                view._render()
                self.shot(900)
                self.scroll(view, 1)
                if system == "GBA":
                    self.scroll(view, 1)
                    self.scroll(view, -1)  # insert LeafGreen's green case
                elif system == "GBC":
                    self.scroll(view, -1)  # insert Crystal's blue case
                self.insert(view)
            finally:
                view.view_finished()
        self.card(
            [
                "Artwork: Slot / Brandon Kowalski (GPL-3.0)",
                "Photos: Game Boy hardware database (CC BY-SA 4.0)",
                "gekkio / ikk5 / Comrade Claire",
                "Rhetchid / fexcollects",
                "PyUI - Copyright (c) 2025 Christopher Jacobs",
                "Used under PyUI's non-commercial license",
            ],
            2600,
        )
        Controller.get_input(timeout=0)  # consume the bootstrap's one scripted idle tick

    def export(self) -> Path:
        """Save the GIF, frame durations and a video-conversion timeline."""
        paths = [self.frames / f"{index:03d}.png" for index in range(len(self.durations))]
        images = [Image.open(path).convert("RGB") for path in paths]
        target = self.output / "cartridge-demo.gif"
        try:
            images[0].save(
                target,
                save_all=True,
                append_images=images[1:],
                duration=self.durations,
                loop=0,
                optimize=True,
            )
        finally:
            for image in images:
                image.close()
        timeline = ["ffconcat version 1.0"]
        for path, duration in zip(paths, self.durations, strict=True):
            timeline.extend((f"file '{path.resolve()}'", f"duration {duration / 1000:.3f}"))
        timeline.append(f"file '{paths[-1].resolve()}'")
        (self.output / "timeline.ffconcat").write_text("\n".join(timeline) + "\n", encoding="utf-8")
        (self.output / "durations.json").write_text(json.dumps(self.durations), encoding="utf-8")
        (self.output / "README.md").write_text(_sharing_notes(), encoding="utf-8")
        with zipfile.ZipFile(self.output / "art-sources.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            artwork = REPO / "assets" / "cartridges"
            for path in sorted(artwork.rglob("*")):
                if path.is_file() and not path.name.startswith("."):
                    archive.write(path, path.relative_to(artwork))
            archive.write(REPO / "scripts" / "prepare_cartridge_art.py", "prepare_cartridge_art.py")
        return target


def _sharing_notes() -> str:
    """Keep credits and an accurate description alongside the shareable media."""
    return """# SpruceOS cartridge carousel — desktop concept demo

The GIF is rendered from the real PyUI view, including its browsing and insertion animations.
It shows seven cartridges across GB/GBC/GBA. Game launching is simulated. Emulator-return
ejection and on-device performance verification remain future integration work.
The selected title is at the top; the console slot fills the bottom with no button hints.
Large browsing cartridges shrink to fit, pause at the opening, then push into the slot.

Artwork: Slot by Brandon Kowalski, commit 868631d7b131540df87c8e3295638e27445cdba2 (GPL-3.0).
https://github.com/BrandonKowalski/slot
Photos: Game Boy hardware database by Gekkio and contributors (CC BY-SA 4.0).
Photographers: gekkio, ikk5, Comrade Claire, Rhetchid, fexcollects.
https://gbhwdb.gekkio.fi/
PyUI — Copyright (c) 2025 Christopher Jacobs; used under its non-commercial license.

art-sources.zip contains source URLs, license notices, original photographs, source shells,
and the reproducible pixel-sprite recipe (prepare_cartridge_art.py --root .).
Printed game artwork and trademarks remain the property of their respective rights holders.

Suggested caption: “A cartridge carousel concept for SpruceOS/PyUI: real cartridge prints,
animated browsing and insertion. Desktop proof of concept; device integration comes next.”

Re-record: make cartridge-demo
Optional MP4 conversion with FFmpeg:
ffmpeg -safe 0 -i timeline.ffconcat -vf fps=50 -c:v libx264 -pix_fmt yuv420p cartridge-demo.mp4
"""


def main() -> int:
    """Bootstrap the desktop device, substitute the recorder, and export the demo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "build" / "cartridge-demo")
    args = parser.parse_args()
    options = desktop.parse_options(
        ["--cartridges", "--headless", "--script", "wait:1", "--res", "640x480"]
    )
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    recorder = Recorder(args.out)
    result = desktop.run(options, cartridge_preview=recorder.run)
    if result == 0:
        recorder.export()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
