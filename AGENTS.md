# Cheevos

On-device RetroAchievements hub for SpruceOS, built on PyUI (Spruce's Python/SDL2 UI).
Instructions for coding agents; `CLAUDE.md` imports this file.

- **Start here:** `.agents/roadmap.md` (what's next).
- `.agents/` explains how the app works, one file per area. Each file covers the design, its
  rules and the gotchas found so far. Read the file for an area before changing it. Code
  comments cite these files, e.g. `(.agents/integration.md)`.

  | File | Covers |
  |---|---|
  | `product.md` | Goals; every screen's behaviour, settings, controls, visual style; offline and error behaviour |
  | `code.md` | Layers and package layout; Python, tooling and style rules; tests |
  | `pyui.md` | The PyUI bridge, view and drawing gotchas, themes, buttons. Read before touching `ui/pyui/`. |
  | `retroachievements.md` | The RA client and API quirks; the website's rules we copy (colours, profile stats); secrets |
  | `sync-and-storage.md` | Caches, the sync engine, threads; FAT32, SQLite and RAM limits |
  | `integration.md` | What we read from Spruce, RetroArch and RAOfflineProxy: credentials, screenshots, on-device games |
  | `device.md` | Target platform, packaging and `launch.sh`, device tooling quirks, performance |
- User docs: `docs/` (published as the GitHub wiki). Keep them in step with the app, and
  regenerate their screenshots with `make doc-screens` after UI changes.
- `TESTING.md`: tests, desktop runner, drills, headless screenshots, device tools.
  `CONTRIBUTING.md`: commit and pull request style.

## Commands (details in TESTING.md)
- `make check`: lint, conventions, ty, and the test suite. Must be green before handing work back.
- `make run [RES=752x560] [SCALE=1]`: desktop window on recorded fixtures. Keys: arrows,
  X=A, Z=B, S=X, A=Y, Q/W=L1/R1, Enter=Start, RShift=Select, Esc=quit.
- Drills: `CHEEVOS_SIMULATE=offline|clock|auth|empty|proxy|showcase|awards|untested|setup make run`.
- `make screens`: headless PNGs in `build/screens/<WxH>/`. Read them to check UI changes.
- Ad hoc: `uv run python -m cheevos.platform.desktop --headless --res 640x480 --script "shot:a,down,shot:b"`
  (tokens: buttons, `shot:<name>`, `wait:N` idle ticks of ~1/12 s).
- `make doc-screens`: regenerate the wiki screenshots after UI changes.

## Devices
- `make deploy launch shot logs stop` with `DEVICE_HOST=<ip>` (or `DEVICE_SSH="ssh user@ip"`).
  `scripts/device.sh press down a b` taps buttons. Screenshots land in `build/device.png`.
  Read them.
- **Device safety:**
  - Write only inside `/mnt/SDCARD/App/Cheevos/`, `/mnt/SDCARD/Saves/cheevos/`, the app's log
    `Saves/spruce/cheevos-*.log`, and `/tmp`.
  - Treat everything else (Spruce/RetroArch configs, other apps' data) as read-only unless a
    change has been agreed.
  - **Never touch `/mnt/SDCARD/Roms`.** A ROM library is usually irreplaceable: don't modify it,
    and don't even list it recursively.
  - Only send single taps of A/B/X/Y/D-pad/L1/R1/Start/Select. Never MENU, power or combos:
    they trigger Spruce hotkeys.
  - **Check that the device is idle before acting.** Run
    `pgrep -f 'python3[.]10 -m [c]heevos'` and `pgrep -f '[r]a32[.]'` first. If Cheevos or a
    game is running, someone may be using the device: don't launch, tap, or replace files.
    Ask first.

## Ground rules
- **Don't commit or push** unless asked: a maintainer reviews and commits changes.
- `.spruceos/` is a sparse SpruceOS checkout with PyUI and the SPRUCE theme (`make pyui`), for
  the desktop runner and screen tests. It's git-ignored; never edit it.
- PyUI may be imported only in `cheevos.ui.pyui` (the bridge) and `cheevos.platform.desktop`
  (dev shim). `scripts/check_conventions.py` enforces this.
- The device runs CPython 3.10.18, so use no 3.11+ features and no third-party runtime
  dependencies.
- The PyUI commit the bridge was verified against is `[tool.cheevos] pyui-tested-commit` in
  `pyproject.toml`. Bump it after re-verifying against a newer SpruceOS.
- Keep the UI lean: prefer a section on an existing screen, or one page with "[X] See more",
  over new screens, and don't make the same screen reachable from several places.
