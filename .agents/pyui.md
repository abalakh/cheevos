# PyUI: the bridge, drawing and themes

PyUI is SpruceOS's Python/SDL2 UI toolkit. Cheevos imports it at runtime from
`/mnt/SDCARD/App/PyUI/main-ui` and never vendors it (Spruce is CC BY-NC, and PyUI changes
weekly). Only `cheevos.ui.pyui` (the bridge) and `cheevos.platform.desktop` (the desktop runner)
may import it ([code.md](code.md), "Layers"). Read this file before touching either.

Cheevos runs only inside PyUI's own process, as the Activity Tracker does ("In-process
sessions", below); it has no launcher of its own. The desktop runner brings PyUI up itself
first ("The desktop runner's start-up"), then runs the same session. PyUI's views draw what the
app needs: lists with icons and right-aligned values, badge grids, popups and custom screens.
Progress bars, frames and the bottom-bar status are drawn by the bridge on top of PyUI's
views, without patching PyUI.

## In-process sessions
- **How PyUI opens it:** `config.json` has `"pyuiEntry": "cheevos.native:run"`. PyUI's
  `apps/native_app.py` (SpruceOS) appends `App/Cheevos` to `sys.path` (PyUI stays at
  `sys.path[0]`), imports the module and calls `run()` from the Apps menu, or `run(game_id=N)`
  from the game menu's "View achievement progress", in PyUI's menu loop: PyUI doesn't exit, and
  B returns straight to its menu. It clears its texture caches before and after, and when
  `run` returns it drops every module imported from the app's folder, the loggers of those
  packages and their importer and `linecache` entries, then runs `gc.collect()` and glibc's
  `malloc_trim`. An exception escaping the entry point is logged to PyUI's log and shown as
  "The app stopped after an error"; PyUI carries on.
- **What `cheevos.native` does:** `run` adds the app log (a handler on the `cheevos` logger,
  which stops propagating, so neither log gets the other's records), then runs `session`, which
  the desktop runner also runs. `run` catches any error, logs it and shows "Cheevos stopped after
  an error" with the log's path. PyUI is already up and owns its device, configs, theme, display,
  controller, view state (`PyUiState`), logger and signal handlers; Cheevos sets none of them
  up. Spruce's environment (`PLATFORM`, `SSL_CERT_FILE`) is PyUI's. PyUI's configs and Spruce's
  are read, never written, except the API key copy below. `session` first applies Spruce's UI
  language (`host.language()`, PyUI's `PyUiConfig.get_language()`); PyUI has already loaded its
  own `Language`, and Cheevos doesn't call `Language.init()` ([product.md](product.md),
  "Languages").
- **Leave PyUI as we found it.** `session` undoes everything it puts into PyUI, in reverse and
  even after an error (an `ExitStack`): the texture budget (`host.enter`/`leave`); the bottom-
  and top-bar hooks (`status_bar.installed`, `title_bar.installed`, inside `app.run`); the
  workers (`app.run` closes them, then `_await_workers` waits up to 2 s more for any
  `cheevos-*` thread); and last the log redaction's record factory (`uninstall_redaction`: it
  is process-wide, and inside PyUI it would otherwise run our code for every PyUI record). It
  also copies the API key into Spruce's settings through PyUI ([integration.md](integration.md)).
  **Rule:** anything process-wide (a PyUI attribute, a logging hook, a signal handler, `atexit`,
  a thread) is undone by the session. `tests/screens/test_native_sessions.py` opens and closes
  the app twice in one PyUI process (once for a single game), drops its modules as PyUI does,
  and fails if any Cheevos module, object, thread or hook survives; a new kind of hook needs a
  check in `native_session.py`.
- **Memory** (Miyoo Mini+, 20-game account, 2026-10-30, same boot): while Cheevos is open the
  system's anonymous memory is the same as with the separate process it used to be (Home
  51.8 MB against 52.5 MB, Awards 52.8 against 53.0; MemAvailable within 0.5 MB): PyUI's own
  ~15 MB of dirty memory stays, but Cheevos no longer loads a second copy of Python and PyUI.
  After closing, every Cheevos module, object, thread, file and texture is gone (Python's live
  objects end within ~350 of where they started), but PyUI keeps ~6-7 MB more dirty memory than
  before the first session: CPython never returns an arena while any block in it is alive, and glibc
  doesn't trim its thread heaps. It's reused: over six sessions PyUI stayed flat at 22.2 MB
  (±16 KB) from the second one on, so it doesn't grow per session. PyUI exits before every game,
  which returns it all. Preloading the C extensions, one glibc arena, fixed trim thresholds and
  a 256 KB SQLite page cache made no difference. Inside PyUI the sync imports `ssl`,
  `http.client`, `email` and `sqlite3` (PyUI on devices loads none of them), and they stay
  loaded: only the app's own folder is dropped.
- **Speed** (same device): A to Cheevos running 0.5 s warm, its Home 0.05 s later; B to
  PyUI's menu with everything unloaded 0.1 s. The first open after an update compiles the
  package (3 s). As a separate process it took 1.8 s to its UI, plus PyUI's exit before and
  its restart after.
- **On a device without the menus:** `make launch [GAME=<id>]` saves the running PyUI's
  environment and command line, asks it to exit, and `principal.sh` runs
  `scripts/device_session.py` with PyUI's interpreter: it brings PyUI up as `mainui.py` does
  and opens Cheevos through PyUI's own `native_app.run`, then exits, and PyUI restarts. Dev
  only, never packaged; it has no per-platform set-up to maintain. Its memory figures leave
  out PyUI's menus.

## The bridge
- **Standard views** (`ViewCreator.create_view`): lists (`ICON_AND_DESC`) and popups
  (`POPUP`), through `views.choose()`, or a `views.PreparedView` that a screen keeps to show
  again ("Showing a view again", below). The same `PreparedView` builds our two subclasses of
  PyUI's views: the badge grid (`GridView`) and the awards carousel (`CarouselView`).
- **Custom screens** (profile, achievement card, full-screen screenshot) are drawn with PyUI's
  `Display` primitives and `Theme` colours and fonts (`primitives.py`), so they still follow the
  theme.
- **Keyboard**: `display/on_screen_keyboard.OnScreenKeyboard`. Its text field is the theme's
  list highlight (`bg-list-l`, 640x90 in SPRUCE) drawn a sixteenth of the screen width tall at
  its natural aspect: 44% of the width, so a 32-character key ran past it. While the keyboard
  is open, `ask_text` swaps `Theme.keyboard_entry_bg` for a 16:1 swatch in the field's colour,
  which scales to the full width (every tested theme's highlight is a flat colour). Its
  background (`bg-grid-s`) is transparent in SPRUCE and missing in the other tested themes, so
  the bottom bar drawn by `Display.clear` stays visible and carries the keyboard's hints.
- The bridge exposes typed functions. Screens never touch PyUI objects directly.
- **Typing:** PyUI has no type hints and its ABCs confuse ty (`get_input(timeout)` declared
  without `self`, `pass` bodies inferring `None` returns). `pyproject.toml` treats PyUI as `Any`
  (`replace-imports-with-any`); the bridge keeps any `Any` inside and screens see only our types.
- **Version drift:** `pyui-tested-commit` (under `[tool.cheevos]` in `pyproject.toml`) records
  the SpruceOS commit the bridge was last verified against; `make pyui` checks it out into
  `.spruceos/`. The weekly `pyui-drift` workflow tests the latest `Development`. Bump the commit
  after re-verifying against a newer SpruceOS.

## The desktop runner's start-up
`platform/desktop/pyui_setup.py` mirrors `mainui.py`'s start-up for PyUI's `DESKTOP` device
(`initialize_device("DESKTOP", main_ui_mode=False)`): configs, device, time zone, view state,
theme, display, controller.
- **Import path:** PyUI must sit at `sys.path[0]`; `Language` finds `lang/` relative to it
  (`add_pyui_to_path`).
- **Logging:** never call `PyUiLogger.init`. It replaces stdout/stderr. Inject our logger into
  `PyUiLogger._logger` instead (`install_logger`).
- **Configs:** `UserConfig.FILEPATH` is hard-coded to the SD card, so the runner points it at
  the fake card; PyUI's view state goes to `Saves/cheevos/pyui-state.json` there.
- **Language:** `--lang <Language>` writes `"language"` into the runner's PyUI config, so PyUI's
  own text and the app both follow it, as on a device. `--lang Pseudo` leaves PyUI in English
  (it has no such file) and hands the app a generated translation instead.

## View gotchas
- **Timeouts:** `view.get_selection()` never returns `None`. On a timeout or cursor move it
  returns a `Selection` whose input is `None`. That is our tick for live refreshes (sync
  progress); "Idle frames" below says how often it comes.
- **Popups:** a `POPUP` view freezes the current frame as its backdrop
  (`Display.lock_current_image`) until `view_finished()` is called. Forget it and every later
  screen is drawn over the frozen frame. `PreparedView.show()` (and so `choose()`) always calls
  it.
- **Showing a view again:** preparing a big list is the slow part (2,940 games: 0.9 s on a Mini),
  so the games list keeps its `PreparedView` and shows it again, back from a game (60 ms). PyUI's
  list keeps its selection and scroll position, and `view_finished()` does nothing for lists and
  grids. Before each later show, the bridge sets the title again (the top bar forgets an award
  dot once another title is drawn) and `VisibleImages.resume()` asks for the visible rows' images
  again (the screens in between moved the downloads to their rows). A popup can be shown once:
  its backdrop is released when it ends.
- **Lazy icons:** `icon_searcher` is called on every render, which is good for lazy images.
  `image_path_searcher` is cached after the first call. But `ViewCreator.create_view` also calls
  every row's `get_icon()` for an `ICON_AND_DESC` list (to pick the selection background), so
  opening a 138-row list used to queue all 138 badge downloads, top to bottom, and a jump to the
  end waited for all of them. `PreparedView` marks that scan `ImageDemand.MEASURED`: the
  resolver returns the fallback icon without downloading or even looking in the cache (first
  thing, and from a dict: building a `Path` per row cost 0.2 s for 2,940 rows). Returning cached
  images extracted every row's icon: with 1,012 cached game icons that pushed ~20 MB through
  the 4 MB scratch LRU (851 evictions) and made the view 10× slower to build. Grids ask
  `image_path_selected_searcher` for the highlighted tile; leave it unset and the selected
  tile has no image.
- **Grids need an image size:** without `resized_width/height`, `GridView.__init__` resolves
  and loads every tile's image to find the tallest. With 2,000 awards that took half a second on
  a Mac. It also extracted hundreds of images through the 4 MB scratch LRU, which evicted files
  whose paths PyUI had already cached; loading those failed, and PyUI blacklisted them for the
  session. The badge grid always passes its badge size.
- **Badge grid** (`badge_grid.py`, a game's achievements and the Awards grid, `Layout.BADGES`):
  a `GridView`
  subclass that keeps PyUI's input, wraparound, L1/R1 paging and touch, and replaces `_render`
  (and `cell_at_touch_point`). It draws the visible tiles every frame, as PyUI's grid does; the
  selected tile last, enlarged, so it covers its neighbours; then the details, scrollbar and
  index. `layout()` is pure: cells are a badge, its gold frame and a gap; room is kept around
  the grid for the enlarged selection and its focus ring (`Frame.FOCUS`, whose inner black band
  is exactly a gold frame, drawn after it). Text is fitted only when the selection changes. A
  new view starts with the selection on its first visible row (PyUI's puts it last). Measured
  on a Mini+ (640×480, 12 frames/s when drawing every frame): 59 draw calls, 16.5 ms to draw
  plus 10 ms to present; every badge framed (a mastered set) 89 calls, 21 + 13 ms. The games
  list is 52 calls, 22 + 10 ms. D-pad moves take 40–65 ms, a new row ~100 ms, R1 to an unseen
  page ~160 ms (decoding 32 badges), and back to a seen page ~65 ms. Caching the composed page
  in a texture would only save ~10 ms per idle frame, so it isn't done.
  - The strip's title uses the normal text colour: the "selected" colour is meant for a
    highlight bar and disappears on MINIMAL's and ART_BOOK_NEXT's plain background.
  - Awards use it as they are: a game icon fits the badge square, and the date goes where an
    achievement's tags go (right-aligned parts are fitted first, so it stays whole).
- **Carousel** (`carousel.py`, the Awards screen, `Layout.CAROUSEL`): a `CarouselView`
  subclass. PyUI keeps the input and the animation (left/right, wraparound, L1/R1 by a
  screenful); the subclass:
  - replaces `_clear` (drawn before every steady and animated frame) to draw the theme, the
    selection's title and description under the images, fitted once per selection, and to
    resolve the visible and outgoing tiles' images (`get_icon()`, since the entry caches its
    image path) plus two more each side as `ImageDemand.NEXT`; a new selection drops the
    downloads still waiting (`visible_images.new_window`). `VisibleImages` doesn't fit: the
    carousel's window wraps around the list;
  - replaces `_render_image` to fit images in the room above the details and frame their
    actual drawn bounds. PyUI passes only the entry's `image_path`, so `_clear` sets it to
    `<path>#<entry id>` and the painter looks up that entry's image and frame. Keyed by path
    alone, awards sharing a fallback (a mastered and a completed game, images not downloaded)
    lost their frames depending on which tiles the slide included, which only CI caught;
  - draws short lists once each: PyUI repeats the options until there are more than twice the
    tiles (`PreparedView` maps the index back with `% count`), and skips the animation below
    three; PyUI resumes drawing after an animation without clearing, so `_clear` runs again;
  - pages with L1/R1 itself on themes with tabs (PyUI returns those to the caller there);
  - sets `options_are_sorted = False` (no letter next to the index);
  - five tiles (centre 40% of the width, shrinking further away), three for fewer than five
    awards (50%) or on a portrait screen (60%: PyUI sizes images by width, and a tall screen
    has height to spare). Images are scaled linearly, as PyUI does (the approved design).
- **Grid tiles cache their image path:** `GridOrListEntry` drops its searchers after one call.
  `visible_images.VisibleImages` re-arms the visible tiles' searchers when `MediaResolver.version` changes,
  so lazily downloaded icons appear. List rows use `icon_searcher`, which PyUI calls every frame.
- **Downloads follow the visible rows:** `visible_images.VisibleImages` wraps each list's and grid's `_render`.
  When the window (`current_top/bottom`, `current_left/right`) moves, it drops the downloads
  still waiting, asks the visible rows again (front of the queue) and queues one more screenful
  in the scroll direction (`ImageDemand.NEXT`, back of the queue). Sizes come from the view, so
  they scale with the screen (5 rows at 640x480, 9 at 480x800).
- **Badge outlines** (`image_frames.py`): hardcore achievements have a gold border; casual,
  pending and locked ones stay plain. Mastered games, events and most site badges use the same
  gold border; completed games stay plain; the $2 Patreon badge gets `Frame.HOLO`, as wide as
  gold, painted with RA's 135° `holoimage` gradient. A transparent PNG frame surrounds the fitted image, with a 1 px black
  outer edge so gold stays gold and readable on bright themes. Thickness scales with the
  image, at least 2 px. Generate once per style and rendered size in the RAM scratch, shared
  across badges: one texture draw per border, with no per-badge image copies. PyUI's bounded
  texture cache includes these assets. Only the bands' pixels are computed (the gradient is
  pure Python, about 55× slower on a Mini+ than on a Mac).
  - **The carousel fills rectangles instead** (`fill()`, `Display.render_box`): its slides
    draw every tile at a new size in each frame, and a PNG per size stalled. Measured on a
    Mini+ with 1,877 awards (2026-10-14): PNG frames took 609 ms for the first move (16 gold
    PNGs, 3–52 ms each) and, for holographic frames, 2.3 s per 224 px PNG: 3.8 s to open
    Awards and an 11.9 s freeze on the first move. Fills: 335 ms for the first move, 314–348
    ms after (warm PNGs: 296–349 ms); every award holographic, as a stress test, ~600 ms a
    move (about 60 fills per holographic tile). Opening Awards: 1.0–1.1 s.
  - Lists wrap `_render` before the list presents and mirror the icon column and row
    geometry; only visible framed icons are measured, in a bounded cache. Cache the fitted
    rectangles until the visible window, options identity or media revision changes, so
    scrolling, on-tick updates and lazy downloads stay correct.
- **Row bars:** progress bars in list rows wrap one view's `_render` (`row_bars.py`) and
  replicate `DescriptiveListView._render`'s geometry (icon column = 1/8 of the selected-row
  background, description at `text_offset_y + title height`). An item with `progress` gets an
  empty (not `None`) description, so PyUI keeps the two-line layout. Colours:
  `bar_colors.py`, after RA's website ([retroachievements.md](retroachievements.md)).
  Every bar has the same length; larger award circles overlay its right endpoint.
  `award_images.py` selects bundled PNGs from `res/awards/`, baked on the development machine
  by `scripts/render_awards.py`. The Games list does no circle rasterization or award PNG writes.
  Dark/light assets follow each row's background; black/white assets handle contrast fallback.
  Each source circle is 48 px across (50 px canvas, or 116 px including the mastery halo),
  scaled with the theme's description line height. For hollow rings, an opaque swatch in the
  row's average background colour covers only the strip of bar inside the ring, ending at
  the circle centre; the rim hides the strip's left edge. The top bar uses these same PNGs
  at a smaller size, including mastery glow, with no bar to mask inside hollow rings.
- **Long text:** since [SpruceOS #1900](https://github.com/spruceUI/spruceOS/pull/1900), PyUI
  fits list titles to their room in pixels: a title that fits is left alone, a longer one ends
  with "..." before the right-aligned value, and the selected one scrolls after a second.
  The bridge passes titles whole (after `displayable()`). A selected title that scrolls keeps
  the screen redrawing (about 66% of a core on a Mini+, against 7% idle) until the next press
  or the screensaver. That's Spruce's own behaviour, accepted on 2026-10-22 so long titles can
  be read. PyUI still doesn't fit descriptions: unselected ones run off the right edge, and
  selected ones scroll past 70 characters. The bridge fits them (`text.fit_with_tail`), and a
  `MenuItem.tail` (an award's date) stays whole: the description is shortened first.
  `displayable()` strips a leading space, so the separator before the tail is added after it.
  The width (`text.description_room`) takes the icon column from the selected-row
  background's width, as PyUI does. Only SPRUCE scales that background to the screen: the
  other themes have a 640 px one at every resolution, and SPRUCE's is 640 px at 480×800.

## Drawing gotchas
- **Idle frames:** since [SpruceOS #1890](https://github.com/spruceUI/spruceOS/pull/1890),
  `Controller.get_input()` returns at once (one frame) while the screen changes or was used in
  the last 1.5 s. Once six frames in a row come out the same, it waits up to a second for a
  key. A change made on another thread would then show up to a second late, so the image, game
  and sync workers call `redraw.request_redraw()` after publishing it
  ([sync-and-storage.md](sync-and-storage.md), "Waking idle screens"). That wraps
  `Controller.request_redraw()`, which is safe from any thread and ends the wait without
  dismissing the screensaver.
  Time-based text (the clock, "synced 5 min ago") needs no request: idle frames still come
  every second.
- **Texture caches never evict:** `Display` caches a texture per distinct string and per image
  path forever. When an allocation fails, it flushes both and retries ("Clearing cache : Out of
  memory" in the log). On the Mini that happened every half minute of browsing long lists, and
  a big screenshot texture could fail to load. `texture_budget.py` swaps each cache's dict for
  an LRU of 2.5 screens' worth of pixels (3 MB each at 640×480) for the session
  (`host.enter`), and `uninstall` destroys them and gives PyUI plain dicts back when it ends.
  Text that changes every frame (sync progress) is still drawn with
  `alpha=255`, which skips the cache entirely.
- **PyUI logs text it can't draw:** `Display.render_text` logs the string on SDL errors ("SDL
  Error received on loading <text>"), which do happen when memory runs low. Don't put secrets
  on screen without muting its log (`ask_text(..., secret=True)`).
- **Measurement cost:** measuring text with SDL_ttf for every row is very slow on a Mini
  (1,000 rows took more than 15 s; one `TTF_SizeUTF8` call is about 105 µs). Use PyUI's cached
  glyph advances (`Display.get_text_width_from_glyphs` and `count_chars_that_fit`, through
  `text.text_width` and `fit_text`): about 30 µs a title. They leave out kerning, so they come
  out 0–4 px wider than SDL_ttf's measurement, never narrower. `displayable()` returns plain
  ASCII at once and looks up any other character once per font, through PyUI's
  `Display.requires_fallback_font`: every description has a "·".
- **Row height:** PyUI's own `_calculate_line_height` sizes every row's title and description
  with SDL_ttf to find the tallest (0.66 s for 2,940 rows). `views._one_sample_row` has it
  measure one sample row instead, holding every character the rows use; our rows share one
  layout, so it comes out the same (checked in SPRUCE, MINIMAL, ART_BOOK_NEXT and Pico-8 at
  640x480, 480x800 and 1280x720).
- **Image measurement:** `Display.get_image_dimensions` loads the file every call. Cache widths.
- **Fonts:** theme fonts vary. Pico-8 has no "·" or "…" and no accented letters, and no theme has
  emoji. Every string goes through `text.displayable(value, role)`, which checks glyphs with
  `TTF_GlyphIsProvided32` and falls back to ASCII (accents: the NFKD base letter). Scripts the
  font lacks entirely (Chinese in Pico-8) draw as boxes: nothing uses PyUI's fallback font
  (`allow_fallback_font_for_missing_glyphs`), PyUI's own menus included.
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
- **Generated images:** `generated.py` writes PNGs (swatches and button glyphs) with a
  stdlib encoder into the RAM scratch: SDL_image can't always save PNG on devices.
- **Bottom bar hook:** the sync status wraps `Display.bottom_bar.render_bottom_bar` (an instance
  attribute), not `Display.clear`. Themes with `renderTopAndBottomBarLast` draw the bar in
  `present()`, after the content. The hook (`status_bar.py`) skips frames where PyUI shows its
  own bar text, and frames under a popup (`Display.bg_canvas` set): the frozen backdrop already
  holds the status, and redrawing changed text over it would smear on translucent bars (SPRUCE,
  Pico-8). `status_bar.hidden()` (the keyboard) drops the status and the Start action but keeps
  hints. `app.run` installs the bar before setup too (no status, Start does nothing), so setup
  screens can show hints.
- **Top-bar title** (`title_bar.py`): PyUI draws the title centred at `int(width / 2)`. A game's
  `Title` shortens only its name, so the count stays. For the award dot, the bridge passes PyUI
  the whole title with a run of spaces in it, and a hook on `Display.top_bar.render_top_bar`
  draws a smaller bundled award PNG in the gap (measured once with SDL_ttf, including room for
  the halo). Its path and size are kept with the title. If the hook draws nothing, the title
  still reads right. Gotchas:
  - `displayable()` collapses runs of spaces, so the gap is added after fitting the name.
  - Unlike the bottom bar, PyUI redraws the whole top bar on popup frames, over the frozen
    backdrop; the dot is drawn there too.
  - The dot belongs to one exact title string and is forgotten the first time the top bar
    draws any other title, so no screen gets a stale one. Themes that show tabs
    (`skip_main_menu`, ART_BOOK_NEXT) or hide the title get no dot.

## Themes
- **Size and DPI:** nothing in Spruce or PyUI knows a panel's DPI or physical size. PyUI draws at
  the device's logical resolution: the panel's own, except the Miniloong Pocket 1 (960x720
  scaled 1.5x to a denser panel). Themes do the sizing: SPRUCE ships `config_<WxH>.json` and
  `skin_<WxH>/` per resolution, scaled from the 640x480 design by `min(width/640, height/480)`
  (PyUI's `Theme._default_multiplier`). List rows are 18.8% of the height on every landscape
  screen, so each shows 5 rows, just sharper; 720x720 shows 7 and 480x800 (drawn at 640x480
  size) 9. Follow the theme rather than the pixel count: size things from its measurements
  (row height, fonts, offsets), and add items only where the screen has room left, never by
  shrinking them, or a sharper small screen gets unreadable.
- **Top-bar title:** PyUI centres it between the clock (left) and the battery and Wi-Fi icons
  (stacked from the right edge). Those have fixed pixel widths, so a fixed share of the screen
  ran into the clock at 480x800. `text.fit_title` measures them once (`_title_room`, mirroring
  `TopBar.render_top_bar_menu_not_skipped`) and falls back to 44% of the width.
- **Bottom bar:** every theme tested (SPRUCE, MINIMAL, ART_BOOK_NEXT, Pico-8) keeps PyUI's bottom
  bar on (a 60 px strip at 640×480). SPRUCE hides the A/B hints with 640 px transparent icons,
  so the sync status is centred; MINIMAL, ART_BOOK_NEXT and Pico-8 show "A Okay / B Back", so it
  starts after them. A theme with `showBottomBar: false` gets no status at all.
- **Button icons:** SPRUCE and MINIMAL ship `icon-x.png` and `icon-y.png` (26×26) and
  `icon-START.png` (48×26 "START" badge). There is no Select icon, and SPRUCE's A/B icons are
  640 px-wide transparent images. `glyphs.py` generates missing ones from the START badge's
  colours, height and the theme font (bold).
- **Selected-text colour is for the highlight bar:** themes pick `selectedcolor` to read on their
  selection background. SPRUCE uses its normal cream, Pico-8 a peach, but MINIMAL and
  ART_BOOK_NEXT use black for a white bar, so on their black page it vanished: the card title,
  the profile name and headings, and the whole "Games by console" table. Titles and rules on
  the page use `primitives.accent_color()` (`ui.text(..., accent=True)`): the selected colour
  where it stands out from the page's average colour (`bar_colors.stands_out`, the bars'
  contrast rule), otherwise the theme's text colour. Only rows drawn on the highlight bar
  itself use `Theme.text_color_selected` directly (`row_bars.py`).
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
- **Y / Menu (tap)**: filter/sort/view popup. Screens accept both buttons as separate inputs;
  desktop M maps to Menu.
  PyUI polls for combinations for 0.3 s before passing Menu to a view. The desktop controller
  pauses scripted steps with `cache_last_event` / `restore_cached_event` during that check,
  so a following capture or tap waits for the popup instead of becoming a hotkey.
- **X**: contextual: reveal a hidden description, "See more" on the profile. That fits PyUI's
  per-item convention.
- **Select**: switch the view (games: bars/details; a game's achievements: list/grid).
