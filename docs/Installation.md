# Installation

## Requirements
- **SpruceOS 4.5.0 or newer.** Cheevos uses Spruce's own UI toolkit (PyUI) and Python, so it
  needs nothing else.
- **A device Spruce runs on.** Cheevos is tested on the Miyoo Mini family; on other devices it
  should work too, and it tells you on first start if yours hasn't been tested yet (see
  [Themes and devices](Themes-and-Devices)).
- **A RetroAchievements account**, signed in on the device (in Spruce's RetroAchievements
  settings or in RetroArch), and its **Web API key**. See [Setup](Setup).
- **Wi-Fi** for the first sync. After that, Cheevos also works offline.

## Install
1. Download the latest release from the repository's **Releases** page, or build it yourself
   (`make package` creates `dist/App/Cheevos`; see `TESTING.md` in the repository).
2. Copy the `Cheevos` folder into the `App` folder of your SD card, so that
   `App/Cheevos/launch.sh` exists.
3. Put the SD card back, open **Apps** in Spruce's main menu and start **Cheevos**.

The first start asks for your Web API key (see [Setup](Setup)), then syncs your account. That
takes about a second per game the first time: a few minutes for a big library. You can browse
while it runs.

## Update
Replace the `App/Cheevos` folder with the new one. Your key and settings live in
`Saves/cheevos/`, so they survive an update. If the new version stores its cache differently,
it rebuilds the cache and syncs again on its own.

## Remove
Delete `App/Cheevos`. To remove your key and settings too, delete `Saves/cheevos`.
