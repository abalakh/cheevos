# Cheevos

Your [RetroAchievements](https://retroachievements.org) on your
[SpruceOS](https://github.com/spruceUI/spruceOS) handheld: profile, game progress, every
achievement with its badge, awards and the screenshots RetroArch took when you unlocked them.
Works offline, follows your Spruce theme.

<p align="center">
  <img src="docs/images/games.png" width="400" alt="Games with progress bars">
  <img src="docs/images/achievement.png" width="400" alt="An achievement with its unlock screenshot">
</p>

## Features
- **Progress bars like RetroAchievements' own:** hardcore in gold, casual in grey, a dot for
  mastered and beaten games.
- **Achievements as a list or a badge grid**, with points, rarity, type tags and unlock dates.
  Filter and sort them.
- **Unlock screenshots** shown on each achievement, and full screen.
- **Profile, recent unlocks and awards** (game, event and site badges, as on your profile).
- **Offline-ready:** everything is cached on the SD card, and syncs only fetch what changed.
  Unlocks still waiting in RAOfflineProxy show as "Pending sync".
- **Optional spoiler protection** for locked descriptions: all of them, or just the story ones.

## Install
Cheevos is included in SpruceOS public and nightly releases and supports **every device
supported by SpruceOS**.

1. You need **SpruceOS 4.5.0+**, signed in to RetroAchievements (Spruce Settings →
   RetroAchievements, or RetroArch).
2. Open **Apps → Cheevos** and enter your **Web API key** when asked. Find it at
   retroachievements.org → Settings → Applications.

For a manual installation or update, download the latest [release](../../releases) and copy
the `Cheevos` folder into `App/` on your SD card.

The [user guide](docs/Home.md) explains every screen, setting and limitation.

## Development
Python 3.10 with no third-party packages at runtime; the screens are drawn with PyUI, the UI
toolkit SpruceOS ships. A desktop runner shows the real app on a Mac or PC without a device.
- [CONTRIBUTING.md](CONTRIBUTING.md): reporting bugs, making changes, pull requests.
- [TESTING.md](TESTING.md): setup, tests, the desktop runner, simulations, the device workflow.
- [RELEASING.md](RELEASING.md): CI, releases, SpruceOS pull requests and wiki publication.
- [AGENTS.md](AGENTS.md) and [.agents/](.agents/): how it works inside, area by area. Written for
  coding agents, and just as useful to people.

## Credits and license
MIT, see [LICENSE](LICENSE). Data, badges and game icons come from
[RetroAchievements.org](https://retroachievements.org); Cheevos isn't affiliated with it. Screens
are drawn with PyUI (Copyright (c) 2025 Christopher Jacobs), which SpruceOS installs; it isn't
bundled. App and UI icons are [original Cheevos artwork](assets/icons/README.md), under the same
MIT license. Details in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
