# Limitations

Cheevos is a viewer for your RetroAchievements data. Some things are out of scope on purpose,
and some are limits of the data RetroAchievements offers.

## Out of scope
- **Earning achievements.** RetroArch (and RAOfflineProxy, when you're offline) does that. Cheevos
  only shows the results.
- **Launching games, leaderboards, social features** (friends, comments, messages).
- **More than one account.** Cheevos follows the account signed in on the device.
- **Changing settings of RetroArch or Spruce.** Cheevos only reads them. For example, it doesn't
  turn on unlock screenshots for you (see [Setup](Setup)).

## Devices
Cheevos is tested on the Miyoo Mini family. It installs and starts on Spruce's other devices
too, but those haven't been tried yet: expect rough edges, and please report them
(see [Themes and devices](Themes-and-Devices)).

## Data from RetroAchievements
- **The first sync takes a while for big libraries:** the details of every game are fetched one
  by one, about a second each. Later syncs only fetch what changed.
- **Spoiler protection is coarse.** RetroAchievements has no spoiler flag. "Story only" uses the
  Progression and Win condition tags, which many older sets don't have. See [Settings](Settings).
- **"Last active"** is when your rich presence last changed. RetroAchievements doesn't expose
  your real last activity through its API.
- **Rank** shows "Unranked" until you have 250 hardcore points. That's RetroAchievements' rule.
- **Hidden awards** (awards you hid on your RetroAchievements profile) don't appear on the awards
  wall. They still count in the totals.
- **Points in the last 7 and 30 days** are fetched when you press See more on the profile, so they
  need Wi-Fi the first time.
- **Subsets** are recognised by "[Subset" in their title, as an approximation of how the site
  groups them. Profile stats leave them out.

## On this device
The "On this device" filter lists games Spruce already recognised as RetroAchievements games: ones
you've played with achievements on this SD card, or that RAOfflineProxy has cached. Cheevos
doesn't scan or hash your ROMs itself, so a game you've never started won't be listed.

## Offline unlocks
RAOfflineProxy works in casual mode only, so unlocks earned offline are always casual. Cheevos
shows them as "Pending sync" until the proxy has sent them.

## Unlock screenshots
Cheevos can show only the screenshots RetroArch saved, which needs RetroArch's
**Automatic Screenshot** setting. They're matched by achievement, from RetroArch's
`<game>-cheevo-<achievement>.png` file names in `Saves/screenshots`. If you rename or move them,
Cheevos can't find them.

## Themes
Theme fonts have no emoji, so emoji in rich presence are left out. Pixel fonts without accented
letters show the plain letter instead.
