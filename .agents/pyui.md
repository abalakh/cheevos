# PyUI: the bridge, drawing and themes

PyUI is SpruceOS's Python/SDL2 UI toolkit. Cheevos imports it at runtime from
`/mnt/SDCARD/App/PyUI/main-ui` and never vendors it (Spruce is CC BY-NC, and PyUI changes
weekly). Only `cheevos.ui.pyui` (the bridge) and `cheevos.platform.desktop` (dev shim) may import
it ([code.md](code.md), "Layers"). Read this file before touching either.

Both early questions have a yes: PyUI can be started from a separate app (`app/launch.sh` mirrors
the platform branch of PyUI's own launcher; about 3 s to a usable screen on the Mini), and its
views draw what the app needs (lists with icons and right-aligned values, badge grids, popups,
custom screens). Progress bars, frames and the bottom-bar status are drawn by the bridge on top
of PyUI's views, without patching PyUI.

## The bridge
- **Bootstrap**: mirror `mainui.py` start-up:
  1. `PyUiConfig.init`, `UserConfig.reload_config`, `CfwSystemConfig.init`, `Language.init`;
  2. `initialize_device(<name>, main_ui_mode=False)`, `PyUiState.init`;
  3. `Theme.init`, `Display.init`, `Controller.init`.
- **Device name**: the same `-device` value PyUI's `launch.sh` would pass, e.g.
  `MIYOO_MINI_PLUS`. `app/launch.sh` gets it from Spruce (`get_miyoo_mini_variant` on the Mini
  family) and passes `CHEEVOS_PYUI_DEVICE`; the bridge creates the device with PyUI's own
  `mainui.initialize_device(..., main_ui_mode=False)` (the mode Spruce's `-msgDisplay` helpers
  use), so every Spruce device works without copying PyUI's device table. Importing `mainui`
  doesn't start PyUI.
- **Standard views** (`ViewCreator.create_view`): lists (`ICON_AND_DESC`, `TEXT_AND_IMAGE`) and
  grids (`GRID`), through `views.choose()`.
- **Custom screens** (profile, achievement card, full-screen screenshot) are drawn with PyUI's
  `Display` primitives and `Theme` colours and fonts (`primitives.py`), so they still follow the
  theme.
- **Keyboard**: `display/on_screen_keyboard.OnScreenKeyboard`.
- The bridge exposes typed functions. Screens never touch PyUI objects directly.
- **Typing:** PyUI has no type hints and its ABCs confuse ty (`get_input(timeout)` declared
  without `self`, `pass` bodies inferring `None` returns). `pyproject.toml` treats PyUI as `Any`
  (`replace-imports-with-any`); the bridge keeps any `Any` inside and screens see only our types.
- **Version drift:** `pyui-tested-commit` (under `[tool.cheevos]` in `pyproject.toml`) records
  the SpruceOS commit the bridge was last verified against; `make pyui` checks it out into
  `.spruceos/`. The weekly `pyui-drift` workflow tests the latest `Development`. Bump the commit
  after re-verifying against a newer SpruceOS.

## Start-up gotchas
- **Import path:** PyUI must sit at `sys.path[0]`; `Language` finds `lang/` relative to it
  (`bootstrap.add_pyui_to_path`).
- **Logging:** never call `PyUiLogger.init`. It replaces stdout/stderr. Inject our logger into
  `PyUiLogger._logger` instead (`bootstrap.install_logger`). Skip
  `Theme.convert_theme_if_needed` (PyUI already did it at its own start-up).
- **Device object:** any device object must give the top bar real battery and charge numbers: a
  stub returning `None` crashes it.
- **Configs:** PyUI's and Spruce's configs are read, never written. PyUI's view state goes to
  our own `Saves/cheevos/pyui-state.json`. `UserConfig.FILEPATH` is hard-coded to the SD card,
  so the desktop bootstrap overrides it.
- **Timezone:** call `device.restore_saved_timezone()` after creating the device, or every
  clock shows UTC. PyUI's launcher does this; we must too.
- **Screensaver:** in non-launcher mode (`main_ui_mode=False`) the Mini lacks
  `miyoo_mini_flip_shared_memory_writer`, so the screensaver can't dim the backlight. The
  bridge creates it (`bootstrap._enable_backlight_control`).
- **Fullscreen window:** PyUI opens a fullscreen window at the monitor's size. On the desktop,
  `window.windowed()` swaps `sdl2.ext.Window` while the display starts.

## View gotchas
- **Timeouts:** `view.get_selection()` never returns `None`. On a timeout or cursor move it
  returns a `Selection` whose input is `None`. That is our tick for live refreshes (sync
  progress).
- **Popups:** a `POPUP` view freezes the current frame as its backdrop
  (`Display.lock_current_image`) until `view_finished()` is called. Forget it and every later
  screen is drawn over the frozen frame. `views.choose()` always calls it.
- **Lazy icons:** `icon_searcher` is called on every render, which is good for lazy images.
  `image_path_searcher` is cached after the first call. Grids ask
  `image_path_selected_searcher` for the highlighted tile; leave it unset and the selected
  tile has no image.
- **Grids need an image size:** without `grid_resized_width/height`, `GridView.__init__` resolves
  and loads every tile's image to find the tallest. With 2,000 awards that took half a second on
  a Mac. It also extracted hundreds of images through the 4 MB scratch LRU, which evicted files
  whose paths PyUI had already cached; loading those failed, and PyUI blacklisted them for the
  session. `choose()` always passes a tile size.
- **Grid tiles cache their image path:** `GridOrListEntry` drops its searchers after one call.
  `views._TileImages` re-arms the visible tiles' searchers when `MediaResolver.version` changes,
  so lazily downloaded icons appear. List rows use `icon_searcher`, which PyUI calls every frame.
- **Grid overlays:** `GridView._render` ends with `present()`, so anything drawn after it is
  lost. Wrap the per-tile `_render_cell` instead (`grid_frames.py`); PyUI calls it with keyword
  arguments (`visible_index=`, `imageTextPair=`).
- **Row bars:** progress bars in list rows wrap one view's `_render` (`row_bars.py`) and
  replicate `DescriptiveListView._render`'s geometry (icon column = 1/8 of the selected-row
  background, description at `text_offset_y + title height`). An item with `progress` gets an
  empty (not `None`) description, so PyUI keeps the two-line layout. Colours:
  `bar_colors.py`, after RA's website ([retroachievements.md](retroachievements.md)).
- **Long text:** PyUI does not truncate list titles against `value_text`, or descriptions at
  the screen edge. The bridge fits both (`ui/pyui/text.py`).

## Drawing gotchas
- **Texture caches never evict:** `Display` caches a texture per distinct string and per image
  path forever. When an allocation fails, it flushes both and retries ("Clearing cache : Out of
  memory" in the log). On the Mini that happened every half minute of browsing long lists, and
  a big screenshot texture could fail to load. `texture_budget.py` swaps each cache's dict for
  an LRU of 2.5 screens' worth of pixels (3 MB each at 640×480), installed after
  `Display.init`. Text that changes every frame (sync progress) is still drawn with
  `alpha=255`, which skips the cache entirely.
- **PyUI logs text it can't draw:** `Display.render_text` logs the string on SDL errors ("SDL
  Error received on loading <text>"), which do happen when memory runs low. Don't put secrets
  on screen without muting its log (`ask_text(..., secret=True)`).
- **Measurement cost:** measuring text with SDL_ttf for every row is very slow on a Mini
  (1,000 rows took more than 15 s). Use cached glyph advances (`text.text_width`). PyUI's own
  `_calculate_line_height` still measures every entry once, costing about 1 s per 1,000 rows.
- **Image measurement:** `Display.get_image_dimensions` loads the file every call. Cache widths.
- **Fonts:** theme fonts vary. Pico-8 has no "·" or "…" and no accented letters, and no theme has
  emoji. Every string goes through `text.displayable(value, role)`, which checks glyphs with
  `TTF_GlyphIsProvided32` and falls back to ASCII (accents: the NFKD base letter).
- **Image scaling:** PyUI scales images with linear filtering, which blurs pixel art.
  `primitives.sharp_scaled` enlarges by the next whole factor above the fit with
  nearest-neighbour (BMP in the RAM scratch), then PyUI shrinks it into the box: "sharp
  bilinear", crisp and using the whole box (a GBA shot on 640×480: 3× = 720×480, drawn
  640×427). An exact whole-factor fit is drawn 1:1.
- **No bars:** PyUI always draws the theme's top and bottom bars; full-screen images paint
  black over them (`begin_bare`). A theme with `renderTopAndBottomBarLast` would draw them on
  top again; none of the themes tested does (SPRUCE, MINIMAL, ART_BOOK_NEXT, Pico-8).
- **Translucent fills don't work on the Mini:** its SDL renderer (MMIYOO) ignores
  `SDL_SetRenderDrawBlendMode` for `SDL_RenderFillRect`, so a 60-alpha fill draws opaque. It
  blends textures fine. Draw translucent rectangles as a stretched translucent PNG
  (`generated.swatch`, `ResizeType.ZOOM`). ZOOM crops the source to the target's shape, so the
  swatch must match the strip's orientation (256×16 wide, 16×256 tall), or a thin side rounds
  to 0 px and nothing is drawn. The desktop can't show this; check on a device.
- **Generated images:** `generated.py` writes PNGs (swatches, award dots, button glyphs) with a
  stdlib encoder into the RAM scratch: SDL_image can't always save PNG on devices.
- **Bottom bar hook:** the sync status wraps `Display.bottom_bar.render_bottom_bar` (an instance
  attribute), not `Display.clear`. Themes with `renderTopAndBottomBarLast` draw the bar in
  `present()`, after the content. The hook (`status_bar.py`) skips frames where PyUI shows its
  own bar text, and frames under a popup (`Display.bg_canvas` set): the frozen backdrop already
  holds the status, and redrawing changed text over it would smear on translucent bars (SPRUCE,
  Pico-8).

## Themes
- **Bottom bar:** every theme tested (SPRUCE, MINIMAL, ART_BOOK_NEXT, Pico-8) keeps PyUI's bottom
  bar on (a 60 px strip at 640×480). SPRUCE hides the A/B hints with 640 px transparent icons,
  so the sync status is centred; MINIMAL, ART_BOOK_NEXT and Pico-8 show "A Okay / B Back", so it
  starts after them. A theme with `showBottomBar: false` gets no status at all.
- **Button icons:** SPRUCE and MINIMAL ship `icon-x.png` and `icon-y.png` (26×26) and
  `icon-START.png` (48×26 "START" badge). There is no Select icon, and SPRUCE's A/B icons are
  640 px-wide transparent images. `glyphs.py` generates missing ones from the START badge's
  colours, height and the theme font (bold).
- **Layout differences:** some themes replace the top bar (ART_BOOK_NEXT shows tabs instead
  of our title), and some have line metrics that make PyUI's own rows overlap (Pico-8). Both
  are theme or PyUI behaviour, not ours.
- **Testing other themes on the desktop:** copy them from the device into `dev/themes/`, then
  set `CHEEVOS_THEMES_DIR` ([TESTING.md](../TESTING.md)).

## Buttons
In PyUI's game lists (`menus/games/roms_menu_common.py`):
- **A** launches.
- **X** opens the game's context menu (`GameConfigMenu`).
- **Select** toggles list/grid.
- **Menu** opens the options popup.
- **L1/R1** page.

**Start** is unused in lists. Elsewhere in Spruce, X is always per-item (Bluetooth: forget
device; themes: theme options) and Start means "confirm" (on-screen keyboard, RAOfflineProxy's
menu). Our mapping (the full table is in [product.md](product.md), "Controls"):
- **Start**: sync / cancel, on every screen. `choose()` and `wait_for()` route it to
  `status_bar.press_start()`; popups and the keyboard (`ask_text` hides the status) don't.
- **Y**: filter/sort/view popup.
- **X**: contextual: reveal a hidden description, "See more" on the profile. That fits PyUI's
  per-item convention.
- **Select**: switch the view (games: bars/details; a game's achievements: list/grid).
