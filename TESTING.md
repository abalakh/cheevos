# Testing and development tools

Most development needs no device: unit tests cover the logic, and a desktop runner shows the
real app on a Mac or PC, from recorded data or the live RetroAchievements API. A device is only
needed for the last check (real SDL driver, fonts, speed, Wi-Fi).

For CI, releases and publishing, see [RELEASING.md](RELEASING.md).

| Layer | Covers | Command | Speed |
|---|---|---|---|
| Unit tests | API parsing, storage, sync planning, stats, settings, credentials, screenshots, proxy reader | `make test` | seconds |
| Screen tests | The real app, headless, on recorded data and drills | `make test` (needs PyUI, below) | ~1 min |
| Desktop runner | Any screen, any resolution or theme, by keyboard or gamepad | `make run` | instant |
| Device | The real thing | `make deploy launch shot` | ~30 s per round |

## Setup
1. Install [uv](https://docs.astral.sh/uv/). It provides Python 3.10, the version SpruceOS ships
   (pinned in `.python-version`).
2. `make sync` installs the development tools: pytest, ruff, ty, shellcheck, and PySDL2 with
   bundled SDL libraries (the same PySDL2 version the device has).
3. `make pyui` fetches PyUI, which Cheevos draws its screens with, and the default SPRUCE theme
   into `.spruceos/`: a sparse checkout of SpruceOS at the commit the bridge was verified against
   (`pyui-tested-commit` in `pyproject.toml`). PyUI isn't vendored. `make pyui
   REF=origin/Development` tries the latest instead.

   To use a checkout elsewhere, set `CHEEVOS_PYUI_DIR` (to `App/PyUI/main-ui`) and
   `CHEEVOS_THEMES_DIR` (to `Themes`). Without PyUI, unit tests still run and screen tests are
   skipped.

`make help` lists every target.

## Checks
| Command | What it runs |
|---|---|
| `make check` | Everything CI runs: lint, conventions, type check and tests. Keep it green. |
| `make lint` | `ruff format --check`, `ruff check`, the conventions checker, shellcheck |
| `make fmt` | Formats and auto-fixes lint |
| `make conventions` | `scripts/check_conventions.py`: module size caps, docstrings everywhere, layering (PyUI only in the bridge) |
| `make typecheck` | `ty check` |
| `make test` | pytest with coverage. Tests never touch the network: a fixture blocks sockets. |

Run one file or test with `uv run pytest tests/unit/test_stats.py -q` or `-k <name>`.

## The desktop runner
`make run` opens the real app in a window on recorded data (`tests/fixtures/ra/`, a real
account's responses), with no network.

```sh
make run                      # 640×480, window zoom 2
make run RES=752x560 SCALE=1  # any resolution Spruce supports
uv run python -m cheevos.platform.desktop --res 1280x720 --theme SPRUCE
```

**Keys** (RetroArch layout plus Menu): arrows = D-pad, X = A, Z = B, S = X, A = Y,
Q / W = L1 / R1, Enter = Start, Right Shift = Select, M = Menu, F8 = screenshot (into
`build/screens/<WxH>/`), Esc = quit. A USB or Bluetooth gamepad works too. Cheevos accepts Y
and Menu as separate inputs for its options popups, so either A or M opens them on the desktop.

**Resolutions:** pass any of Spruce's: 640x480, 720x480, 752x560, 720x720, 960x720, 1024x768,
1280x720, 480x800.

**Real badges and icons in fixture mode:** run `uv run python scripts/fetch_dev_media.py` once.
It mirrors the images the fixtures mention into `dev/media-host`, and the `showcase` drill's
event and site badges (site art from RA's static host, under `assets/`). CI has no mirror, so
its screen tests see fallback icons everywhere. A screen test that compares images can pass
here and fail there (awards sharing a fallback once lost their frames): before pushing one,
run it once with `dev/media-host` renamed.

**Unlock screenshots in fixture mode** come from `dev/sdcard/Saves/screenshots` if it exists.
Otherwise the fake card gets a generated stand-in for Final Fantasy Tactics Advance's two unlocks,
so scripts that open a screenshot work the same everywhere, CI included.

**Other themes:** copy theme folders from a device's `Themes/` into `dev/themes/`, then:

```sh
CHEEVOS_THEMES_DIR=$PWD/dev/themes uv run python -m cheevos.platform.desktop --theme MINIMAL
```

**Live mode** uses the real API with a development SD card in `dev/sdcard`:

```sh
uv run python -m cheevos.platform.desktop --live
```

The card needs a username and a key, like a device. Put `cheevos_username = "<name>"` in
`dev/sdcard/Saves/ra-configs/retroarch-MiyooMini.cfg` and the key in
`dev/sdcard/Saves/cheevos/apikey.txt`, or let the app's setup screens ask for them.

`dev/` and `build/` are git-ignored.

## Simulations (drills)
`CHEEVOS_SIMULATE=<name> make run` starts fixture mode in a situation that's hard to set up for
real. Each drill gets a fresh card.

| Drill | What it shows |
|---|---|
| `offline` | No network: the sync on open fails, saved data stays usable |
| `clock` | App clock starts in 1970, then recovers from RA's response time and syncs |
| `auth` | The API key is rejected |
| `empty` | An account with no games |
| `noset` | Fire Emblem, the first game in the list, with its achievement set and counts removed. Shows the zero-total list row and the message; A or B returns to the games list. |
| `proxy` | RAOfflineProxy enabled, with unlocks waiting to sync (games list `+N`, Recent unlocks, the Settings row). Descent's has no `patch:` data, as after playing online with RetroArch 1.22. |
| `showcase` | Every kind of progress (mastered, completed, beaten in both modes, mixed hardcore and casual), with achievement lists to match, awards (games, tiered and plain events, site badges with a holographic one; `showcase_awards.py` also answers the v2 API), a month of recent unlocks and a made-up account. Used for the docs' screenshots. |
| `awards` | A big account's Awards screen, from a recording of that account's awards and events (below), with live images. Its games aren't in the fixtures, so opening one tries to load it and says "Loading failed". |
| `setup` | First start without a key file: the key screen (A types the key, B exits) |
| `ondemand` | Only the working set is downloaded, as after a first sync. Opening an older game (Metroid, last in the games list) loads it, slowed to 1.5 s to show the loading page. |

The `awards` drill needs a recording of the awards, and of what the sync asks RA's v2 API
about their events (tiers and points; a few requests, with the key in a header):

```sh
uv run python scripts/record_fixtures.py <username> --awards-only --out dev/fixtures/awards
CHEEVOS_SIMULATE=awards make run
```

`CHEEVOS_AWARDS_FIXTURES=<dir>` points the drill at another recording. Without the events in
it, event badges show RA's own titles with "Event award" (the offline fallback).

## Headless screenshots
The runner can play a script of button presses without a window and save the screens as PNG:

```sh
uv run python -m cheevos.platform.desktop --headless --res 640x480 \
    --script "shot:home,down,a,shot:games,y,shot:options"
```

Script tokens: `up down left right a b x y l1 r1 l2 r2 start select menu`, `shot:<name>` (save
`build/screens/<WxH>/<name>.png`, or `--out <dir>`), and `wait:N` (N idle ticks of 1/12 s, for
things that take time, like a sync).

- `make screens` renders the standard walk-through at 640×480, 752×560 and 1280×720 into
  `build/screens/`. Each resolution starts on a fresh temporary SD card, so settings and view
  state saved by `make run` don't affect the captures. The cards are removed when the command
  finishes, including on failure. The weekly PyUI drift job uploads the screenshots.
- A run fails if the app exits before the script ends. That usually means the script drifted
  from the screens, e.g. a B too many after a press that did nothing.
- `make doc-screens` renders the wiki's screenshots (`docs/images/`) from the `showcase`
  drill. Themes found in `dev/themes/` (MINIMAL, Pico-8) are included.

## Icon assets

The app and UI icons are original SVGs in `assets/icons/` (design rules in its `README.md`).
After changing them, run `uv run python scripts/render_icons.py` to regenerate the bundled
PNGs, then review `make screens` and refresh the wiki with `make doc-screens`. List and
fallback icons use 96 or 144 px sources, while bottom-bar icons stay at 24 or 48 px. PyUI
fits list icons into each theme's layout; all themes use the same gold and muted-lock colours.

## Award indicators

The Games list uses bundled PNGs in `src/cheevos/res/awards/`, generated on a development
machine with `uv run python scripts/render_awards.py`. Each circle is 48 px across, with a
transparent margin for anti-aliasing and a larger margin for mastery's glow. PyUI scales them
to the theme's row size and keeps them in its bounded texture cache. There is no runtime
circle or glow rasterizer. The game title reuses the same PNGs at a smaller size.

Dark/light variants suit the ordinary and selected rows independently; black/white variants
cover themes where gold and grey have too little contrast. Hollow rings stay transparent.
The bridge covers just the bar strip inside them with the row's background colour.

After changing the assets, review `make screens` and refresh `make doc-screens`.

## Recorded data
- `uv run python scripts/record_fixtures.py <username> [--out tests/fixtures/ra]` records an
  account's API responses (profile, games, awards, recent unlocks, every game's achievements) as fixtures. The
  key comes from `CHEEVOS_API_KEY` or `dev/sdcard/Saves/cheevos/apikey.txt` and is never written
  to the files. Requests are spaced out to be polite to RetroAchievements.
- `uv run python scripts/make_synthetic_cache.py OUT_DB USERNAME --games 1000` builds a big
  synthetic cache for performance tests (large lists on a slow device).

`scripts/benchmark_proxy.py` measures pending-award metadata reads on a disposable proxy
cache. It creates 2,001 games with 100 achievements each and tests queues of two unlocks:
early and late matches, another account's fallback, and unknown achievements. Each read gets
a fresh process; the JSON report gives median elapsed time and peak RSS (including Python).
Every run checks the returned metadata and queue order. It never uses an installed proxy.

To compare a change, save the baseline before editing the lookup, then run:

```sh
mkdir -p build
git show HEAD:src/cheevos/core/proxy.py > build/proxy-before.py
# Make the lookup change, then:
uv run python scripts/benchmark_proxy.py --baseline build/proxy-before.py
```

Without `--baseline`, it measures the current reader only. `--games`, `--per-game` and
`--repeats` change the cache size and sample count. The RSS measurement needs macOS or Linux;
desktop timings are comparisons, not estimates of speed on the Mini.

## Sync without the UI
The sync engine runs on its own against a card:

```sh
CHEEVOS_SDCARD_ROOT=$PWD/dev/sdcard CHEEVOS_SCRATCH=$PWD/dev/scratch uv run python -m cheevos.core.sync
```

## On a device
The device tools work over SSH. Turn SSH on in Spruce's settings and connect the device to the
same network.

```sh
export DEVICE_HOST=<device ip>     # or DEVICE_SSH="ssh user@ip" for a full ssh command
make package deploy                # build dist/App/Cheevos and copy it to App/Cheevos
make launch                        # start Cheevos, as the Apps menu would
make shot                          # screenshot into build/device.png
make logs                          # the app log and the last stderr
make stop                          # ask Cheevos to exit
scripts/device.sh press down a b   # tap buttons
```

Password prompts work; an SSH key saves typing. The only thing `deploy` deletes is the old
`App/Cheevos/cheevos` package before copying the new one.

**Keep backups off the device's `/tmp`.** On the Mini it is a 49 MB tmpfs backed by RAM;
an 18 MB app backup was enough to cause memory pressure, thread creation failures and a
device freeze. Stream backups over SSH directly to the development machine. Stream deployment
archives straight into `tar` on the SD card, as `device.sh deploy` does, instead of staging
them in the device's `/tmp`.

**Be careful with a device that's in use:**
- Check that it's idle before launching, tapping or deploying: neither Cheevos nor a game should
  be running (`pgrep -f 'python3[.]10 -m [c]heevos'`, `pgrep -f '[r]a32[.]'`).
- `press` sends single taps, and only while Cheevos is running: a tap after it exits would reach
  Spruce's menu, where A starts a game. Don't send MENU, power or button combinations: they
  trigger Spruce hotkeys.
- Treat everything outside `App/Cheevos/`, `Saves/cheevos/` and `/tmp` as read-only, and leave
  `Roms/` alone entirely. A ROM library is usually irreplaceable.

To run a sync on the device without the UI, over SSH:

```sh
cd /mnt/SDCARD/App/Cheevos && PLATFORM=MiyooMini \
  SSL_CERT_FILE=/mnt/SDCARD/spruce/etc/ca-certificates.crt \
  /mnt/SDCARD/spruce/bin/python/bin/python3.10 -m cheevos.core.sync
```

## How the desktop runner works
The window, keyboard, gamepad, scripts and screenshots are PyUI's own `DESKTOP` device
(SpruceOS `App/PyUI/main-ui/devices/desktop/`, documented in `App/PyUI/docs/desktop_readme.txt`;
in a SpruceOS checkout, `python3 App/PyUI/main-ui/desktop.py` runs Spruce's whole launcher the
same way). Cheevos starts it with `devices.device_factory.initialize_device`
(`bootstrap.pyui_device("DESKTOP")`), falling back to `mainui.initialize_device` on older
SpruceOS releases. `src/cheevos/platform/desktop/` adds only Cheevos' side: the command line,
recorded fixtures or the live API, and the drills.
- **Configuration:** the runner passes its options to PyUI as `PYUI_DESKTOP_*` variables (size,
  zoom, headless, script, capture folder). The fake card is PyUI's data folder, so the device's
  own settings land in its `Saves/desktop-system.json`.
- **Device:** battery fixed at 87% and Wi-Fi off, so screenshots are stable. Display and volume
  settings are saved but not applied.
- **Scripts:** a `shot:` step runs when PyUI next waits for input, i.e. after the frame is
  complete, and saves the logical frame whatever the zoom. While PyUI checks whether Menu starts
  a button combination, scripted steps wait. Headless runs use SDL's dummy video driver and the
  software renderer.
- **PyUI version:** a SpruceOS checkout from before the `DESKTOP` device (October 2026) stops
  the runner with "has no DESKTOP device"; `make pyui` fetches the pinned commit.
- **SDL** comes from `pysdl2-dll` (SDL2, SDL2_ttf, SDL2_image); PySDL2 is pinned to the
  device's 0.9.17.

## What the desktop can't show
- The Mini's custom `mmiyoo` SDL driver: for example, it ignores blending for filled rectangles
  (see `.agents/pyui.md`), double buffering, evdev input.
- Real speed: a dual-core Cortex-A7 at 1.2 GHz, 128 MB RAM, slow SD writes. Big lists and
  image-heavy screens need a check on hardware.
- FAT32 on the SD card (32 KB clusters, `dirsync`), the real RAOfflineProxy, Wi-Fi, and a clock
  that reads 1970 until it syncs.
