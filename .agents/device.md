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

`make package` builds `dist/App/PyUI/main-ui/cheevos/` and `dist/Cheevos-<version>.zip`.
The ZIP contains the native Python package, icon, MIT license, a short install note and
`spruceos-pyui.patch`. The patch adds Cheevos to Apps and preloads pure imports in the
background. B on Home returns to the existing launcher. There is no separate app launcher.
Desktop-only bootstrap code is excluded from the device package.

## Device gotchas (verified on a Miyoo Mini+, SpruceOS 4.5.0)
- **Idle check:** inspect a screenshot and check for a running game before acting. Native
  Cheevos shares PyUI's process.
- **Stray taps:** once Cheevos exits (B on its home screen), further taps reach Spruce's menu,
  where A starts a game. Take a screenshot
  between screens rather than sending long sequences.
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

| Metric | Target | Measured |
|---|---|---|
| List navigation | ≤ 100 ms per move | Images load lazily; only visible rows resolve them |
| Sync with no changes | ≤ 10 s | 1.4 s (12 games; 4 requests in the pacer's burst; 4.0 s at a flat 1/s) |
| First sync | Home, games list and awards within ~15 s; recent games' achievements within ~2 min | 2,937 games (2026-10-06): list in 8 s (list and awards in 5.6 s with the burst, measured from a Mac); all data in ~68 s (a 58-game working set); 5,114 icons and badges 2.5 min more, in the background. Downloading every game would take ~51 min. |
| Opening a game that isn't downloaded | ≤ 2 s | 1.8 s for 493 achievements during a sync (list on screen at 2.2 s) |
| Big lists | — | Games list with 2,940 games (2026-10-07): 1.4 s to open (first time in a run), 0.9 s to re-sort, 1.1 s to switch to details, 60 ms back from a game (the list is kept while its games don't change). It used to take 3.7, 2.9 and 3.0 s. Back to home: 50 ms (was 0.56 s: home read every game and award to show two counts). Awards wall (2,125 tiles): 1.0 s to open. Row text uses cached glyph widths; measuring each title with SDL_ttf took over 15 s for 1,000 rows. |
| Profile | ≤ 0.8 s | 2,940 games, 3,904 awards (2026-10-07): 0.79 s the first time in a run, 0.54 s after (was 1.18 and 0.91 s). Reading every game takes 0.27 s, and so does reading every award: a screen reads each at most once, and only the kinds it uses. |
| Memory | Well within the Mini's 128 MB | 2,940 games: app RSS at most 54 MB, `MemAvailable` never below 33 MB, MMA never below 4.1 MB, no OOM. Images are extracted to a bounded RAM scratch. |

The hardware: a Cortex-A7 at 1.2 GHz, 128 MB RAM, slow SD writes. Big lists and image-heavy
screens need a check on it.
