# Contributing

Bug reports, device reports and pull requests are all welcome.

## Reporting a bug or a device
Open an issue with:
- your device, SpruceOS version and theme;
- what you did and what happened (a photo or a Spruce screenshot helps);
- the log from your SD card: `Saves/spruce/cheevos-<device>.log`.

Cheevos is tested on the Miyoo Mini family. A report from another Spruce device, whether it
works or not, is as useful as a bug report: it's how a device gets confirmed.

## Making a change
1. Set up the tools and run the app on your computer: see [TESTING.md](TESTING.md). Most changes
   need no device.
2. Follow the project's rules. The checks enforce most of them:
   - Python 3.10 (the version on the devices) and the standard library only at runtime.
   - PyUI, Spruce's UI toolkit, is used only in `src/cheevos/ui/pyui/`. Screens use that
     package's typed functions.
   - Google-style docstrings on every module, class and function, private ones included.
     Modules stay under 500 lines.
   - User-facing text goes in `src/cheevos/ui/strings.py`.
   - Keep the UI lean: extend an existing screen rather than adding a new one.
3. Run `make fmt`, then `make check` (format, lint, conventions, type check, tests). CI runs
   the same checks.
4. For UI changes, check `make screens` at a few resolutions. Update the user guide in `docs/`
   to match, and refresh its screenshots with `make doc-screens`.

How the app works inside, area by area (PyUI, RetroAchievements, sync and storage, devices), is
in [`.agents/`](.agents/), indexed by [AGENTS.md](AGENTS.md). It's written for coding agents,
and it's also the best reference for people changing the code.

## Pull requests
- One topic per pull request. Say what changed and why, and add screenshots for UI changes.
  If you tried it on a device, say which one.
- Commit subjects follow SpruceOS's style, `Area: imperative summary`, at most 72 characters.
  Areas: `Core`, `Sync`, `UI`, `Bridge`, `Desktop`, `Device`, `Build`, `Docs`. Example:
  `Sync: resume interrupted runs from the saved plan`.
- Branches: `feat/<topic>` or `fix/<topic>`.

## License
Contributions are licensed under the project's [MIT license](LICENSE).
