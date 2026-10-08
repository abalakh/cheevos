# Troubleshooting

## Common problems
| What you see | What to do |
|---|---|
| "Cheevos couldn't start" | Something went wrong before the first screen. The log named in the message has the details; please report it on the project's GitHub page. |
| "Sign in to RetroAchievements first" | Sign in in **Spruce Settings → RetroAchievements** (or in RetroArch), then start Cheevos again. |
| "API key rejected" | The Web API key is wrong or was reset on the site. Copy it again from retroachievements.org (**Settings → Keys**), press **Start** and type it. |
| "apikey.txt doesn't hold a Web API key" | The file needs just the key: 32 letters and digits on the first line, nothing else. Press **A** to type it instead. |
| "Offline · showing saved data" | No connection. Everything synced before is still there. Press **Start** to retry. |
| "RetroAchievements unavailable" | The site is busy or down. Cheevos uses your saved data; try again later. |
| "RetroAchievements asked to wait N min" | RetroAchievements limits how often an app may ask for data, and asked Cheevos to pause. Cheevos uses your saved data and syncs again once the time is up. Other tools using the same Web API key count towards the same limit. |
| A pixel-art trophy (unlocked), grey lock (locked) or gamepad instead of a badge or game icon | The image isn't downloaded yet. It appears once you're online. To download more ahead of time, change **Badge downloads** in Settings. |
| Something looks out of date | Press **Start**. If it's still wrong, use **Settings → Download every game**: it downloads every game's achievements again. |
| "This game's achievements aren't downloaded yet" | Cheevos keeps the games you play and downloads others when you open them, which needs Wi-Fi. The message says what went wrong. To have every game offline, use **Settings → Download every game**. |
| No screenshot on an achievement | RetroArch only saves one when **Automatic Screenshot** is on (see [Setup](Setup.md)), and only for unlocks after that. |

## Starting over
Cheevos' data on the SD card:

| Path | What it is | Safe to delete? |
|---|---|---|
| `Saves/cheevos/apikey.txt` | Your Web API key | Yes. Cheevos asks for it again. |
| `Saves/cheevos/settings.json` | Your settings | Yes. Back to defaults. |
| `Saves/cheevos/pyui-state.json` | Last selected rows | Yes. |
| `Saves/cheevos/cache/` | Synced data and downloaded images | Yes. The next start syncs everything again. |

Deleting `Saves/cheevos/cache/` fixes most problems that downloading every game again doesn't.

## Logs
Cheevos writes a log to `Saves/spruce/cheevos-<device>.log` (e.g. `cheevos-MiyooMini.log`).
If it fails to start, the error is added there too. The log never contains your API key, so you
can attach it to a bug report.

## Data and privacy
- Cheevos talks only to `retroachievements.org` and its image server, normally over HTTPS with
  certificate checks. There's no analytics or tracking.
- If TLS fails (including an unset or incorrect device clock), Cheevos automatically falls
  back to HTTP. This sends your Web API key and account data unencrypted, so someone able to
  observe the connection could read them. See [Setup](Setup.md).
- Your Web API key is stored as plain text on the SD card, like Spruce stores your RetroAchievements
  password. The key only gives read access through RetroAchievements' Web API. You can reset it
  on the site at any time.
- Cheevos reads Spruce's, RetroArch's and RAOfflineProxy's files but never writes to them. It
  writes only to `Saves/cheevos/`, its log, and temporary files in `/tmp`.

## Reporting a bug
Open an issue on the project's GitHub page with: your device and Spruce version, what you did,
what you expected, and the log file.
