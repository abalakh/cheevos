# Installation

## Requirements
- **SpruceOS 4.5.0 or newer.** Cheevos uses Spruce's own UI toolkit (PyUI) and Python, so it
  needs nothing else.
- **A device Spruce runs on.** Cheevos is tested on the Miyoo Mini family; on other devices it
  should work too (see [Themes and devices](Themes-and-Devices)).
- **A RetroAchievements account**, signed in on the device (in Spruce's RetroAchievements
  settings or in RetroArch), and its **Web API key**. See [Setup](Setup).
- **Wi-Fi** for the first sync. After that, Cheevos also works offline.

## Install
1. Download `Cheevos-<version>.zip` from the latest release on the repository's **Releases**
   page (not the "Source code" archives), or build it yourself with `make package` (see
   `TESTING.md` in the repository).
2. Extract the zip to the root of your SD card, so that `App/Cheevos/launch.sh` exists.
3. Put the SD card back, open **Apps** in Spruce's main menu and start **Cheevos**.

The first start asks for your Web API key (see [Setup](Setup)), then syncs your account. That
takes about a second per game the first time: a few minutes for a big library. You can browse
while it runs.

## Update
Delete the `App/Cheevos` folder, then extract the new zip as when installing. Your key and
settings live in `Saves/cheevos/`, so they survive an update. The cache lives in
`App/Cheevos/cache`, so the first start after an update syncs everything again.

## Remove
Delete `App/Cheevos`. To remove your key and settings too, delete `Saves/cheevos`.
