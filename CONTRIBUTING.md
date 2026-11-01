# Contributing

Bug reports and pull requests are welcome.

## Reporting a bug
Open an issue with:
- your device, SpruceOS version and theme;
- what you did and what happened (a photo or a Spruce screenshot helps);
- the log from your SD card: `Saves/spruce/cheevos-<device>.log`.

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

CI and the maintainer's publishing workflow are in [RELEASING.md](RELEASING.md).

## Translating
Cheevos shows itself in the language chosen in Spruce's settings, when it has a translation for
it. Translations live in this repository, not in Spruce: SpruceOS copies each Cheevos release
whole, so a change to `App/Cheevos/` in Spruce is lost at the next one.

1. Run `make languages`. It writes every string in English to `build/lang/English.json`.
2. Copy it to `src/cheevos/res/lang/<Language>.json`, named exactly as Spruce's own file for the
   language in `App/PyUI/lang/` (`Catalan.json`, `Chinese (S).json`), and translate the values.
   Keep the names on the left as they are. `Ukrainian.json` there is a complete example.
   - Keep every `{field}`: the app fills them in. `{day:02d}` may become `{day}`.
   - A text with `{count}` that counts something takes plural forms:
     `{"one": "{count} punt", "other": "{count} punts"}`. Use the forms your language needs
     (`one`, `few`, `many`, `other`; `other` is required). The rules for each language are in
     `src/cheevos/ui/plurals.py`.
   - A text with several numbers can't take plural forms. Put a label before each number
     instead, as Ukrainian does: `"Хардкор: {hardcore} · казуал: {softcore}"`.
   - Lists keep their length: 12 `MONTHS`, 4 `SIZE_UNITS`.
   - Leave a value as `""`, or out, to keep it in English for now. Keys starting with `_` are
     notes and are ignored, e.g. `"_translators": "Your name"`.
3. Run `make languages` again until it reports nothing left out, and `make check`.
4. Run `make screens UI_LANGUAGE=<Language>` and look through `build/screens/<Language>/`: text
   that's cut short or crowded needs a shorter wording. The walk-through doesn't reach every
   screen, so browse the rest in `CHEEVOS_SIMULATE=showcase make run UI_LANGUAGE=<Language>`.
   Popups (the options under Y, the choices in Settings) are the tightest: a line there has
   room for about as much as "Filter: Progression and win". A value may drop its label when it
   reads well alone, as Ukrainian's sort orders do ("За назвою" for "Sort: Title"). Attach a
   few screenshots to the pull request.

Game, achievement and console names come from RetroAchievements and stay in English.

## Pull requests
- One topic per pull request. Say what changed and why, and add screenshots for UI changes.
  If you tried it on a device, say which one.
- Commit subjects follow SpruceOS's style, `Area: imperative summary`, at most 72 characters.
  Areas: `Core`, `Sync`, `UI`, `Bridge`, `Desktop`, `Device`, `Build`, `Docs`. Example:
  `Sync: resume interrupted runs from the saved plan`.
- Branches: `feat/<topic>` or `fix/<topic>`.

## License
Contributions are licensed under the project's [MIT license](LICENSE).
