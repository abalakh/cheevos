# Installation

## Requirements
- **SpruceOS 4.5.0+.** Cheevos uses Spruce's own UI toolkit (PyUI) and Python, so it
  needs nothing else.
- **A device Spruce runs on.** Cheevos is tested on the Miyoo Mini family; on other devices it
  should work too (see [Themes and devices](Themes-and-Devices.md)).
- **A RetroAchievements account**, signed in on the device (in Spruce's RetroAchievements
  settings or in RetroArch), and its **Web API key**. See [Setup](Setup.md).
- **Wi-Fi** for the first sync. After that, Cheevos also works offline.

## Install
1. Download `Cheevos-<version>.zip` from the latest release on the repository's **Releases**
   page (not the "Source code" archives), or build it yourself with `make package` (see
   `RELEASING.md` in the repository).
2. Copy the ZIP's `App/` folder onto the SD card, merging with the existing folder.
   Cheevos goes in `App/PyUI/main-ui/cheevos/`.
3. Apply the included PyUI patch as described in the ZIP's `README.md`, then restart PyUI
   and open **Apps → Cheevos**.

The first start asks for your Web API key (see [Setup](Setup.md)), then syncs your account. That
takes about a second per game the first time: a few minutes for a big library. You can browse
while it runs.

## Update
Delete the old `App/PyUI/main-ui/cheevos` folder, then copy its replacement from the ZIP.
Your key and settings live in `Saves/cheevos/`, so they survive an update. Cached data stays in
`App/Cheevos/cache/` and is reused across updates.

## Remove
Revert the included PyUI patch and remove `App/PyUI/main-ui/cheevos`.
To remove your key and settings too, delete `Saves/cheevos`.
