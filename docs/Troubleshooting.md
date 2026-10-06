# Troubleshooting

## Common problems
| What you see | What to do |
|---|---|
| "Cheevos couldn't start" | Something went wrong before the first screen. The log named in the message has the details; please report it on the project's GitHub page. |
| "Sign in to RetroAchievements first" | Sign in in **Spruce Settings → RetroAchievements** (or in RetroArch), then start Cheevos again. |
| "API key rejected" | The Web API key is wrong or was reset on the site. Copy it again from retroachievements.org (**Settings → Keys**), press **Start** and type it. |
| "apikey.txt doesn't hold a Web API key" | The file needs just the key: 32 letters and digits on the first line, nothing else. Press **A** to type it instead. |
| "Clock not set · connect to Wi-Fi" | The device doesn't know the time yet, and secure connections need it. Turn on Wi-Fi, wait a moment, and press **Start**. |
| "Offline · showing saved data" | No connection. Everything synced before is still there. Press **Start** to retry. |
| "RetroAchievements unavailable" | The site is busy or down. Cheevos uses your saved data; try again later. |
| A pixel-art trophy (unlocked), grey lock (locked) or gamepad instead of a badge or game icon | The image isn't downloaded yet. It appears once you're online. To download more ahead of time, change **Badge downloads** in Settings. |
| Something looks out of date | Press **Start**. If it's still wrong, use **Settings → Full re-sync**. |
| No screenshot on an achievement | RetroArch only saves one when **Automatic Screenshot** is on (see [Setup](Setup)), and only for unlocks after that. |

## Starting over
Cheevos' data on the SD card:

| Path | What it is | Safe to delete? |
|---|---|---|
| `Saves/cheevos/apikey.txt` | Your Web API key | Yes. Cheevos asks for it again. |
| `Saves/cheevos/settings.json` | Your settings | Yes. Back to defaults. |
| `Saves/cheevos/pyui-state.json` | Last selected rows | Yes. |
| `App/Cheevos/cache/` | Synced data and downloaded images | Yes. The next start syncs everything again. |

Deleting `App/Cheevos/cache/` fixes most problems that a full re-sync doesn't.

## Logs
Cheevos writes a log to `Saves/spruce/cheevos-<device>.log` (e.g. `cheevos-MiyooMini.log`).
If it fails to start, the error is added there too. The log never contains your API key, so you
can attach it to a bug report.

## Data and privacy
- Cheevos talks only to `retroachievements.org` and its image server, always over HTTPS with
  certificate checks. There's no analytics or tracking.
- Your Web API key is stored as plain text on the SD card, like Spruce stores your RetroAchievements
  password. The key only gives read access through RetroAchievements' Web API. You can reset it
  on the site at any time.
- Cheevos reads Spruce's, RetroArch's and RAOfflineProxy's files but never writes to them. It
  writes only to `Saves/cheevos/`, `App/Cheevos/cache/`, its log, and temporary files in `/tmp`.

## Reporting a bug
Open an issue on the project's GitHub page with: your device and Spruce version, what you did,
what you expected, and the log file.
