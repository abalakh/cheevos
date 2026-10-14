# Devices: platform, packaging and tooling

The safety rules for working on a real device are in [AGENTS.md](../AGENTS.md) ("Devices") and
always apply. The device commands are in [TESTING.md](../TESTING.md).

## Target platform

| Item | Value |
|---|---|
| OS | SpruceOS ≥ 4.5.0. Needs PyUI views, `spruce/scripts/appEnv.sh` and RAOfflineProxy 2.x. |
| Devices | Every device Spruce supports. Verified on a Miyoo Mini+ (640×480); the rest of the Mini family shares its setup. Others are untested. |
| Resolutions | Every resolution the default SPRUCE theme ships: 640×480, 720×480, 752×560, 720×720, 960×720, 1024×768, 1280×720, 480×800. |
| Runtime | Spruce's CPython **3.10.18**: `$SPRUCE_PYTHON` (32-bit: `spruce/bin/python/bin/python3.10`; 64-bit: `spruce/flip/bin/python3.10`). |
| Built-in modules we rely on | `ssl` (OpenSSL 3.5), `sqlite3`, `json`, `hashlib`, `zlib`, `ctypes`, `zoneinfo` |
| Third-party | **None of our own.** PySDL2 0.9.17 is loaded only indirectly, through PyUI. No `requests`, no Pillow. |
| UI toolkit | PyUI, imported at runtime from `/mnt/SDCARD/App/PyUI/main-ui` ([pyui.md](pyui.md)). |
| TLS | CA bundle at `$SSL_CERT_FILE` (`/mnt/SDCARD/spruce/etc/ca-certificates.crt`). An unset/incorrect clock or another TLS failure uses HTTP automatically. RA's Date supplies app time without changing the device clock. |

## Packaging

```
/mnt/SDCARD/App/Cheevos/
  config.json     {"label": "Cheevos", "icon": "cheevos.png", "launch": "launch.sh",
                   "description": "RetroAchievements hub"}   (no "devices": every device)
  launch.sh       sources helperFunctions.sh, sets the per-platform SDL env (mirroring PyUI's
                  launcher), runs Spruce's Python with -m cheevos; stderr to /tmp
  cheevos.png     app icon
  cheevos/        the Python package, with res/icons
  cache/          created at runtime
```

- `make package` builds it into `dist/App/Cheevos/` (no desktop runner, no tests) and zips that
  as `dist/Cheevos-<version>.zip`, with the `Cheevos/` prefix and no `App/` folder.
- The Apps launcher discovers any `App/*/config.json`. PyUI exits fully while the app runs and
  restarts when it quits.
- **No `devices` list:** a `devices` list in an app's `config.json` hides it on every device not
  named there. Cheevos ships without one, so the Apps menu shows it on every device.
  `launch.sh` covers every platform PyUI's launcher does.
- **Untested devices run the same code as the Mini.** Keep device-specific screens and code
  paths out of the app: we can't test them, so on exactly the devices they're for they would
  be the riskiest code. A one-time "untested device" note was removed for this reason (it also
  gave users nothing to act on). Release notes say which devices are tested.
- **Start-up failures:** when the app exits non-zero, `launch.sh` appends its stderr to the app
  log and shows a message ([product.md](product.md), "Offline and error behaviour").
  `/mnt/SDCARD/App/PyUI/launch.sh -msgDisplay "text" -msgDisplayTimeMs 5000` shows a message on
  any platform.
- The release is that zip; users copy its `Cheevos` folder into `App` on the SD card. Pushing a
  `v<version>` tag publishes it as a GitHub release (the `release` job in `ci.yml`; steps in
  [RELEASING.md](../RELEASING.md), under "Releases"). The description links merged PR titles
  and direct commit titles.
  Pre-releases start at the previous version tag; stable releases start at the previous stable tag.
  Game Nursery packaging follows whatever format the maintainers ask for.

## Device gotchas (verified on a Miyoo Mini+, SpruceOS 4.5.0)
- **Idle check:** a test once replaced the cache under an open session; hence the rule to check
  that neither Cheevos nor a game is running first.
- **Stray taps:** once Cheevos exits (B on its home screen), further taps reach Spruce's menu,
  where A starts a game. A blind tap loop once launched a game this way. `device.sh press` now
  refuses on the device unless Cheevos is running, and stops at the first refusal. Still,
  take a screenshot between screens rather than sending long sequences.
- **`pgrep -f` self-match:** a plain `pgrep -f` pattern also matches the remote shell's own
  command line. Use the `[x]` trick (`'[c]heevos'`).
- **busybox limits:** busybox tar rejects pax/xattr headers, so deploy uses
  `COPYFILE_DISABLE=1 tar --format ustar`. Busybox `sort` has no `-h`.
- **SSH:** ssh's ControlPath must be under ~104 bytes, so the control socket lives in
  `/tmp/cheevos-mini-%C`.
- **Screenshots:** `fbgrab` output is upside down; rotate it 180° (Spruce's `screenshot.sh`
  does the same).
- **Input injection:** `send_event /dev/input/event0 CODE:1|0`. Codes: A=57, B=29, X=42,
  Y=56, Start=28, Select=97, L1=18, R1=20, D-pad 103/108/105/106. Never send MENU (1), power
  or combos.
- **Launching an app remotely:** write `/tmp/cmd_to_run.sh` (PyUI's own format), then send
  SIGTERM to PyUI; `principal.sh` runs the command and restarts PyUI afterwards. This also
  records autoresume, exactly as launching from the Apps menu does.
- **Graphics memory:** SDL textures come from the MMA pool (`mma_heap=…sz=0x1500000`, 21 MB),
  not from the RAM `MemAvailable` reports. The framebuffer and PyUI's screen-sized canvases
  take about 11.5 MB of it, leaving about 9 MB for textures. Free space:
  `/proc/mi_modules/mi_sys_mma/mma_heap_name0` (`chunk_mgr_avail`, hex). Big textures need
  one contiguous block. See [pyui.md](pyui.md), "Texture caches never evict".
- **Log times are UTC** (marked `Z`): PyUI applies the saved time zone partway through
  start-up, so local times would jump within one run.
- **PIDs wrap at 4096**, so a low PID doesn't mean an old process. Check
  `/proc/<pid>/stat` against `/proc/uptime` for its age.
- **Network services:** Spruce restarts Samba and SFTPGo after every app exits; SSH (dropbear)
  survives.
- **Storage, `/tmp` and the clock:** see [sync-and-storage.md](sync-and-storage.md).
- **What the desktop can't show:** the MMIYOO SDL driver's quirks (translucent fills, see
  [pyui.md](pyui.md)), real speed, FAT32, the real proxy, Wi-Fi and an unset clock.

## Performance (Miyoo Mini+)

The hardware: a dual-core Cortex-A7 at 1.2 GHz, 128 MB RAM (103 MB for Linux, the rest for the
graphics pool), slow SD writes. Big lists and image-heavy screens need a check on it.
- **Memory headroom is small.** Measured 2026-10-14 on Spruce 4.5.5 nightly with a 2,948-game
  account: about 17 MB available on Home, with RAOfflineProxy's service at 30–36 MB beside
  Cheevos (33–36 MB RSS). Browsing images fills the 4 MB `/tmp` image scratch, and the heap
  levels off at +3–4.5 MB. Below about 8 MB available, starting a thread fails (the kernel's
  heuristic refuses an 8 MB stack): PyUI's Wi-Fi status refresh then raised `can't start new
  thread` and Cheevos exited. 0.1.6 and the Awards carousel both got there after 20–30 pages
  of awards; a long desktop run under `tracemalloc` showed no Python leak.
- **CPU:** measure per thread from `/proc/<pid>/task/*/stat` (fields 14 + 15, 1/100 s ticks);
  100 ticks a second is one core. Busybox `top` shows % of both cores together.

### Start-up
Measured 2026-10-14 (Spruce 4.5.5 nightly, PyUI `346b4092`, warm, 2,948-game account), before
[SpruceOS #1857](https://github.com/spruceUI/spruceOS/pull/1857): Home's first frame appeared
4.1–4.5 s after Python started, down from 4.6–4.9 s before Cheevos deferred its screens and
sync imports. The first start after an update also compiled every module, about 1.5 s more.
Python's imports took most of it (3.4 s): finding and reading each module from the SD card
costs a few ms before its code even runs, and each dataclass 5–7 ms to build. The upstream
factory and game-menu fixes have not yet been timed on a device.
- **Rule: import what Home's first frame doesn't need on first use.** Every screen but Home
  (`home._open`), the badge grid and carousel (`views`), the RA client and transport (`app`'s
  factories), the sync engine (on the sync thread, `background`) and `email.utils` (`clock`)
  load when first used; `ra_client/__init__.py` imports nothing. Names the UI needs without
  the engine live in `sync/options.py`; `Credentials` lives in `core/credentials.py`.
  `tests/unit/test_startup_imports.py` fails if any of them loads with `cheevos.app`: add a
  new screen or worker to its list. The modules that import on first use are listed in
  `pyproject.toml`'s per-file `PLC0415` ignores. The cost moves to each screen's first
  opening (Games +0.3 s, Profile +0.2 s, Awards +0.1 s the first time).
- **The auto-sync starts after Home's first frame** (`Home(sync_when_shown=...)`, on its
  first tick): started before, the sync thread's imports competed with the first frame
  (+0.3 s).
- **PyUI's upstream device factory:** `bootstrap.pyui_device` imports `initialize_device`
  from `devices.device_factory` for every device, including `DESKTOP`. This avoids the
  launcher imports without copying any device branches. If that module is absent on an
  older supported SpruceOS, it falls back to `mainui.initialize_device`; errors inside the
  factory still surface. `tests/unit/test_ui_bootstrap.py` covers both paths.
- **PyUI's game menus load on first activity-icon lookup:** SpruceOS #1857 (merge commit
  `a3c494b1`) moved the two menu imports into `MiyooTrimCommon.get_image_for_activity`, which
  Cheevos never calls. On a Mac, after importing PyUI's shared UI modules, the Mini device
  adds 48 modules instead of 141, and the Brick 43 instead of 137. The pre-fix device timing
  put about 0.36 s in these menu imports; the new hardware saving remains unmeasured.
- **PyUI's Wi-Fi status is read on a thread during the display's start-up**
  (`bootstrap._warm_wifi_status`): its first read runs `wifiCmd status` (0.4 s) and the top
  bar draws it from the first frame.
- **PyUI's remaining share** in the pre-fix measurements: `display.display` imports pysdl2's
  `sdl2.ext`, whose `resources` module imports `urllib.request` with `http.client`, `email`
  and `ssl` (0.2 s). `Display.init` took about 1 s (0.63 s re-initialising, 0.32 s loading
  fonts). Don't plant stub modules to skip them: Spruce updates PyUI without a Cheevos release.
- **How it was measured:** a patched build (never shipped) logs the first frame's time from
  the process start (`/proc/self/stat`), and can run `cProfile` up to it or start Python with
  `-X importtime`. A launch with `-X` doesn't match `pgrep -f 'python3[.]10 -m [c]heevos'`
  (`device.sh` misses it): stop it by PID.
