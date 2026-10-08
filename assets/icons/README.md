# Cheevos icons

All SVGs here are original Cheevos artwork, covered by the repository's [MIT license](../../LICENSE).
The shapes follow the SPRUCE theme's rounded outline style; no third-party icon set is bundled.

- `cheevos.svg`: app icon, a 70 × 70 canvas with 4 px rounded strokes and about 10 px padding.
- `ui/`: menu, status and fallback icons. Use the same canvas and stroke, rounded caps and joins,
  and `currentColor`. Keep silhouettes simple enough to read at 24 px. The trophy matches the
  app icon. `lock-muted` is rendered from `lock.svg`, rather than having a separate source.
  The gamepad uses the wider, flatter proportions and compact button spacing of SPRUCE's
  Games category icon, while retaining the set's 4 px stroke and gold colour.

Regenerate the bundled PNGs with `uv run python scripts/render_icons.py`. It uses the existing
desktop SDL dependency; there is no runtime SVG renderer or additional dependency.

The app icon is 105 px. UI icons are rendered in SPRUCE gold (`#D7B45F`), with a muted lock
(`#7C6F64`), at 24 and 48 px for the bottom bar and 96 and 144 px for lists and image fallbacks.
The larger list sources keep curves clean when PyUI fits them into each theme's icon column.
Other themes retain their own fonts, backgrounds and layout; icon colours stay fixed.
