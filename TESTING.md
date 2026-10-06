# Testing and development tools

Most development needs no device: unit tests cover the logic, and a desktop runner shows the
real app on a Mac or PC, from recorded data or the live RetroAchievements API. A device is only
needed for the last check (real SDL driver, fonts, speed, Wi-Fi).

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

**Keys** (RetroArch's default keyboard layout): arrows = D-pad, X = A, Z = B, S = X, A = Y,
Q / W = L1 / R1, Enter = Start, Right Shift = Select, Esc = quit. A USB or Bluetooth gamepad
works too.

**Resolutions:** pass any of Spruce's: 640x480, 720x480, 752x560, 720x720, 960x720, 1024x768,
1280x720, 480x800.

**Real badges and icons in fixture mode:** run `uv run python scripts/fetch_dev_media.py` once.
It mirrors the images the fixtures mention into `dev/media-host`.

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
| `clock` | Clock not set (the device just booted): sync waits |
| `auth` | The API key is rejected |
| `empty` | An account with no games |
| `proxy` | RAOfflineProxy enabled, with unlocks waiting to sync (games list `+N`, Recent unlocks, the Settings row). Descent's has no `patch:` data, as after playing online with RetroArch 1.22. |
| `showcase` | Every kind of progress (mastered, completed, beaten in both modes, mixed hardcore and casual), awards, a month of recent unlocks and a made-up account. Used for the docs' screenshots. |
| `awards` | A big account's awards wall, from a recording of that account's awards (below), with live images. Its games were never synced, so opening one says "not synced yet". |
| `untested` | Runs as a device Cheevos hasn't been tested on: the one-time "untested device" note |
| `setup` | First start without a key file: the key screen (A types the key, B exits) |

The `awards` drill needs one recorded response:

```sh
uv run python scripts/record_fixtures.py <username> --awards-only --out dev/fixtures/awards
CHEEVOS_SIMULATE=awards make run
```

## Headless screenshots
The runner can play a script of button presses without a window and save the screens as PNG:

```sh
uv run python -m cheevos.platform.desktop --headless --res 640x480 \
    --script "shot:home,down,a,shot:games,y,shot:options"
```

Script tokens: `up down left right a b x y l1 r1 l2 r2 start select`, `shot:<name>` (save
`build/screens/<WxH>/<name>.png`, or `--out <dir>`), and `wait:N` (N idle ticks of 1/12 s, for
things that take time, like a sync).

- `make screens` renders the standard walk-through at 640×480, 752×560 and 1280×720 into
  `build/screens/`. The weekly PyUI drift job uploads them.
- A run fails if the app exits before the script ends. That usually means the script drifted
  from the screens, e.g. a B too many after a press that did nothing.
- `make doc-screens` renders the wiki's screenshots (`docs/images/`) from the `showcase`
  drill. Themes found in `dev/themes/` (MINIMAL, Pico-8) are included.

## Recorded data
- `uv run python scripts/record_fixtures.py <username> [--out tests/fixtures/ra]` records an
  account's API responses (profile, games, awards, every game's achievements) as fixtures. The
  key comes from `CHEEVOS_API_KEY` or `dev/sdcard/Saves/cheevos/apikey.txt` and is never written
  to the files. Requests are spaced out to be polite to RetroAchievements.
- `uv run python scripts/make_synthetic_cache.py OUT_DB USERNAME --games 1000` builds a big
  synthetic cache for performance tests (large lists on a slow device).

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
PyUI has no desktop mode, but its parts are pluggable: `Controller` takes its input from the
device object, `Display` and `Theme` ask the device only for the screen size and a few flags,
and PyUI's core UI modules don't hard-code `/mnt/SDCARD`. So the runner needs no PyUI patches
(`src/cheevos/platform/desktop/`):
- **Device:** `DesktopDevice` subclasses PyUI's `DeviceCommon`. Its abstract methods become
  logging no-ops (`abc.update_abstractmethods`), and `__getattr__` turns calls PyUI makes
  outside the abstract interface into no-ops too, so the shim keeps up as PyUI grows. Real
  overrides: screen size, state path, controller, battery and charge (PyUI's top bar needs
  numbers), Wi-Fi off.
- **Input:** keyboard by scancode (RetroArch's default layout), the first SDL gamepad, or a
  script. `still_held_down()` reports real key state, so PyUI's own hold/turbo logic works.
- **Window:** PyUI opens a fullscreen window at the monitor's size; the runner swaps
  `sdl2.ext.Window` for a plain window while the display starts.
- **Capture:** after `present()`, PyUI's off-screen canvas is still the render target, so
  `SDL_RenderReadPixels` gives the exact logical frame. `shot:` steps run when PyUI waits for
  input, i.e. after the frame is complete. Headless runs use `SDL_VIDEODRIVER=dummy` and the
  software renderer.
- **SDL** comes from `pysdl2-dll` (SDL2, SDL2_ttf, SDL2_image); PySDL2 is pinned to the
  device's 0.9.17.

## What the desktop can't show
- The Mini's custom `mmiyoo` SDL driver: for example, it ignores blending for filled rectangles
  (see `.agents/pyui.md`), double buffering, evdev input.
- Real speed: a Cortex-A7 at 1.2 GHz, 128 MB RAM, slow SD writes. Big lists and image-heavy
  screens need a check on hardware.
- FAT32 on the SD card (32 KB clusters, `dirsync`), the real RAOfflineProxy, Wi-Fi, and a clock
  that reads 1970 until it syncs.

## CI
- **CI** (`.github/workflows/ci.yml`): on every push and pull request, checks out PyUI at
  `pyui-tested-commit`, then runs lint, type check and tests. When a test fails, it uploads the
  screen tests' captures (`screen-test-captures`).
- **PyUI drift** (`.github/workflows/pyui-drift.yml`): weekly, the same tests and `make screens`
  against SpruceOS's latest `Development` branch, as an early warning when PyUI changes. It
  uploads the screens either way. After re-verifying against a newer SpruceOS, bump
  `pyui-tested-commit`.
- CI has no `dev/media-host`, so badges, icons and avatars in CI screens are placeholders.

## Releases
`make package` builds `dist/App/Cheevos/` and `dist/Cheevos-<version>.zip`, which extracts to
the SD card root. To publish a release:

1. Set the version in `pyproject.toml` and `src/cheevos/__init__.py` (a test checks that they
   match). Use PEP 440: `0.1.0b1` for a pre-release, `0.1.0` for a release. Run `uv lock`, since
   CI installs with `--locked`, then `make check`.
2. Commit, tag `v<version>` and push both: `git tag v0.1.0b1 && git push origin master v0.1.0b1`.
3. Once the checks pass, CI's `release` job publishes a GitHub release with the zip. Versions
   with `a`, `b`, `rc` or `dev` in them are marked as pre-releases. A tag that doesn't match
   the version fails the job.

GitHub adds its own "Source code" archives to every release; they can't be removed. Testers
need only the `Cheevos-<version>.zip`.

## Publishing the wiki
The pages in `docs/` are written for the GitHub wiki, which is a separate repository
(`<repo>.wiki.git`). Copy the folder's contents, `images/` included, into a clone of it and
push. Regenerate the screenshots first with `make doc-screens` when screens have changed.
