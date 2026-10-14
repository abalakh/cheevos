# Cartridge demo artwork

This is the editable asset source for the Spruce/PyUI cartridge proof of concept.
`manifest.json` records every game, photographer, source URL path, shell color and label crop.
Rebuild with `uv run python scripts/prepare_cartridge_art.py` (Pillow is a dev dependency).
The runtime loads the prepared PNGs and uses nearest-neighbour texture sampling.

## Shells and slot

The original neutral cartridge shells and two dark slot layers in `slot-source/` come from
[Slot by Brandon Kowalski](https://github.com/BrandonKowalski/slot), commit
`868631d7b131540df87c8e3295638e27445cdba2`. They are redistributed under Slot's GPL-3.0
license; the complete notice is in `LICENSE-slot-GPL-3.0.txt`. Our changes tint the plastic,
reduce it to a pixel grid, reduce the shell/slot palette, and fit the photographed labels.
No Slot launcher code was copied. Original sources and the build script are included.

`rendered/shell-*.png`, `rendered/slot-*.png` and the composed game cartridge PNGs are
GPL-3.0 adaptations. These artwork files have their own license; the Cheevos code's MIT
license does not relicense them.

## Cartridge photographs and labels

The photographs in `photos/` are from the
[Game Boy hardware database by Gekkio and contributors](https://gbhwdb.gekkio.fi/), under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The labels are cropped and
resized from the real cartridge photographs, including the original typography and seals.
The extracted `rendered/*-label.png` files remain CC BY-SA 4.0. The archive's photo license
does not replace the game publishers' rights in the printed artwork or trademarks.

| Game | Photographer | Original submission |
|---|---|---|
| Tetris | gekkio | [DMG-TRA-1](https://gbhwdb.gekkio.fi/cartridges/DMG-TRA-1/gekkio-1.html) |
| Super Mario Land | ikk5 | [DMG-MLA-0](https://gbhwdb.gekkio.fi/cartridges/DMG-MLA-0/ikk5-1.html) |
| Pokémon Crystal Version | Comrade Claire | [CGB-BYTE-0](https://gbhwdb.gekkio.fi/cartridges/CGB-BYTE-0/comrade-claire-1.html) |
| The Legend of Zelda: Oracle of Seasons | Rhetchid | [CGB-AZ7E-0](https://gbhwdb.gekkio.fi/cartridges/CGB-AZ7E-0/rhetchid-1.html) |
| Final Fantasy Tactics Advance | ikk5 | [AGB-AFXP-0](https://gbhwdb.gekkio.fi/cartridges/AGB-AFXP-0/ikk5-1.html) |
| Pokémon LeafGreen Version | fexcollects | [AGB-BPGE-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BPGE-1/fexcollects-1.html) |
| Advance Wars | ikk5 | [AGB-AWRP-0](https://gbhwdb.gekkio.fi/cartridges/AGB-AWRP-0/ikk5-1.html) |

GPLv3 is an approved one-way compatible license for contributions to adaptations of
CC BY-SA 4.0 works ([Creative Commons compatibility list](https://creativecommons.org/compatible-licenses/)).
The original photo credits and CC notice are retained for the composite cartridge sprites.

The demo's credits card and accompanying notes identify Slot, the photo contributors and
PyUI (Copyright (c) 2025 Christopher Jacobs). The demo demonstrates the desktop UI; game
launching is simulated, and emulator-return ejection remains a separate integration step.
