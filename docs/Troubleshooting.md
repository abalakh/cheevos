# Troubleshooting

## Common problems
| What you see | What to do |
|---|---|
| "Cheevos stopped after an error" | Something went wrong and Cheevos closed. The log named in the message has the details; please report it on the project's GitHub page. |
| "The app stopped after an error" | Spruce couldn't open Cheevos at all, often because the `App/Cheevos` folder is incomplete. Copy it again from the release. Spruce's log (`Saves/spruce/pyui.log`) has the details. |
| "Sign in to RetroAchievements first" | Sign in in **Spruce Settings → RetroAchievements** (or in RetroArch), then start Cheevos again. |
| "API key rejected" | The Web API key is wrong or was reset on the site. Copy it again from retroachievements.org (**Settings → Keys**), press **Start** and type it. |
| "apikey.txt doesn't hold a Web API key" | The file needs just the key: 32 letters and digits on the first line, nothing else. Press **A** to type it instead. |
| "Offline · showing saved data" | No connection. Everything synced before is still there. Press **Start** to retry. |
| "RetroAchievements unavailable" | The site is busy or down. Cheevos uses your saved data; try again later. |
| "RetroAchievements asked to wait N min" | RetroAchievements limits how often an app may ask for data, and asked Cheevos to pause. Cheevos uses your saved data and syncs again once the time is up. Other tools using the same Web API key count towards the same limit. |
| A trophy (unlocked), grey lock (locked) or gamepad instead of a badge or game icon | The image appears when you open that screen online. To download badges for your entire library ahead of time, use **Settings → Download every game**. |
| Something looks out of date | Press **Start**. If it's still wrong, use **Settings → Download every game**: it downloads every game's achievements again. |
| "This game's achievements aren't downloaded yet" | Cheevos keeps the games you play and downloads others when you open them, which needs Wi-Fi. The message says what went wrong. To have every game offline, use **Settings → Download every game**. |
| No screenshot on an achievement | RetroArch only saves one when **Automatic Screenshot** is on (see [Setup](Setup.md)), and only for unlocks after that. |
| "No known RetroAchievements game matches this ROM's hash" (Spruce's game menu) | RetroAchievements doesn't recognise this version of the ROM. Cheevos checks it again after a week; deleting `Saves/cheevos/cache/rom-identifications.json` checks it at once. |
| "Game identification needs a compatible RAOfflineProxy" (Spruce's game menu) | Cheevos identifies ROMs with RAOfflineProxy's hasher, which is missing or a version Cheevos doesn't know. Update Spruce or Cheevos. The log has the details; the proxy itself isn't affected. |

## Starting over
Cheevos' data on the SD card:

| Path | What it is | Safe to delete? |
|---|---|---|
| `Saves/cheevos/apikey.txt` | Your Web API key | Yes. Cheevos asks for it again. |
| `Saves/cheevos/settings.json` | Your settings | Yes. Back to defaults. |
| `Saves/cheevos/cache/` | Synced data, downloaded images and ROM identifications | Yes. The next start syncs everything again. |

Deleting `Saves/cheevos/cache/` fixes most problems that downloading every game again doesn't.

## Logs
Cheevos writes a log to `Saves/spruce/cheevos-<device>.log` (e.g. `cheevos-MiyooMini.log`).
If it fails to start, the error is added there too. The log never contains your API key, so you
can attach it to a bug report.

Cheevos uses Spruce's PyUI log level when it opens. To capture debug output, turn on
**Verbose PyUI logging** under **Settings → Additional Settings → System Settings**, then open
Cheevos and reproduce the issue.

## Data and privacy
- Cheevos talks only to `retroachievements.org` and its image server, normally over HTTPS with
  certificate checks. There's no analytics or tracking. Identifying a ROM from Spruce's game
  menu sends only the ROM's hash.
- If TLS fails (including an unset or incorrect device clock), Cheevos automatically falls
  back to HTTP. This sends your Web API key and account data unencrypted, so someone able to
  observe the connection could read them. See [Setup](Setup.md).
- Your Web API key is stored as plain text on the SD card, like Spruce stores your RetroAchievements
  password. The key only gives read access through RetroAchievements' Web API. You can reset it
  on the site at any time.
- Cheevos reads Spruce's, RetroArch's and RAOfflineProxy's files but never writes to them, and
  uses RAOfflineProxy's ROM hasher without changing it. It writes only to `Saves/cheevos/`, its
  log, and temporary files in `/tmp`.

## Reporting a bug
Open an issue on the project's GitHub page with: your device and Spruce version, what you did,
what you expected, and the log file.
