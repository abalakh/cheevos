"""Build the demo's pixel sprites from attributed Slot shells and cartridge photographs.

Pillow is development-only. All output is checked in, so the prototype and PyUI never need
it at runtime. Inputs, crop rectangles and credits are kept in assets/cartridges/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1] / "assets" / "cartridges"
PANELS = {"GBA": (48, 50, 312, 186), "GB": (46, 98, 266, 293), "GBC": (45, 110, 268, 309)}
COLORS = {"GBA": (72, 77, 88), "GB": (163, 164, 151), "GBC": (66, 73, 77)}
PIXEL_DIVISOR = 2
SHADES = 20
OPAQUE_THRESHOLD = 128


class GameArt(TypedDict):
    """Describe one attributed demo cartridge and its measured label crop."""

    id: str
    title: str
    system: str
    color: list[int]
    crop: list[float]
    photographer: str
    entry: str
    photo: str


def plastic(system: str, color: tuple[int, int, int], root: Path = ROOT) -> Image.Image:
    """Tint Slot's neutral shell, retaining its moulded lighting and transparent outline."""
    source = Image.open(root / "slot-source" / f"{system.lower()}_neutral.png").convert("RGBA")
    gray = source.convert("L")
    channels = [
        gray.point(lambda value, channel=channel: min(255, round(value * channel / 128)))
        for channel in color
    ]
    tinted = Image.merge("RGBA", (*channels, source.getchannel("A")))
    size = tuple(round(side / PIXEL_DIVISOR) for side in source.size)
    sprite = tinted.resize(size, Image.Resampling.BOX)
    alpha = sprite.getchannel("A").point(lambda value: 255 if value >= OPAQUE_THRESHOLD else 0)
    sprite = sprite.convert("RGB").quantize(SHADES, dither=Image.Dither.NONE).convert("RGBA")
    sprite.putalpha(alpha)
    return sprite


def label_crop(game: GameArt, root: Path = ROOT) -> Image.Image:
    """Extract an authentic print from a contributor's photographed cartridge."""
    photo = ImageOps.exif_transpose(Image.open(root / "photos" / f"{game['id']}.jpg"))
    left, top, right, bottom = game["crop"]
    return photo.crop(
        (
            round(left * photo.width),
            round(top * photo.height),
            round(right * photo.width),
            round(bottom * photo.height),
        )
    )


def game_sprite(game: GameArt, out: Path, root: Path = ROOT) -> None:
    """Place a photographed label into the matching pixel shell without inventing lettering."""
    system = str(game["system"])
    color = game["color"]
    sprite = plastic(system, (color[0], color[1], color[2]), root)
    panel = tuple(round(value / PIXEL_DIVISOR) for value in PANELS[system])
    width, height = panel[2] - panel[0], panel[3] - panel[1]
    label = label_crop(game, root).resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", label.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=2, fill=255)
    label.putalpha(mask)
    sprite.alpha_composite(label, panel[:2])
    sprite.save(out / f"{game['id']}.png")
    label.save(out / f"{game['id']}-label.png")


def build(root: Path = ROOT) -> None:
    """Write reusable shells, two slot layers and the seven complete demo cartridges."""
    out = root / "rendered"
    out.mkdir(exist_ok=True)
    for system, color in COLORS.items():
        plastic(system, color, root).save(out / f"shell-{system.lower()}.png")
    for layer in ("back", "front"):
        source = Image.open(root / "slot-source" / f"slot_{layer}_dark.png").convert("RGBA")
        size = tuple(side // PIXEL_DIVISOR for side in source.size)
        sprite = source.resize(size, Image.Resampling.BOX)
        alpha = sprite.getchannel("A").point(lambda value: 255 if value >= OPAQUE_THRESHOLD else 0)
        sprite = sprite.convert("RGB").quantize(SHADES, dither=Image.Dither.NONE).convert("RGBA")
        sprite.putalpha(alpha)
        sprite.save(out / f"slot-{layer}.png")
    games = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["games"]
    for game in games:
        game_sprite(game, out, root)
    print(f"Built {len(games)} cartridge prints, three shells and two slot layers in {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    build(parser.parse_args().root)
