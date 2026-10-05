# Sync and offline play

## What syncing does
Cheevos keeps a copy of your RetroAchievements data on the SD card and shows that copy. Syncing
updates it:
1. Your profile (points, rank, last played game).
2. Your list of games with their progress.
3. The achievements of every game that changed since the last sync: the details of a game you
   haven't touched aren't fetched again. Games not refreshed for 30 days are checked a few at a
   time, so changes RetroAchievements makes to old sets also arrive.
4. Your awards.
5. Badges and game icons (see **Badge downloads** in [Settings](Settings)).

**The first sync** fetches every game once: about a second per game, so a few minutes for a big
library. Later syncs take seconds. You can browse while syncing. If a sync is interrupted (you
leave the app, the device sleeps, the battery runs out), the next one carries on where it stopped.

**When it runs:** when you open Cheevos (unless you turn that off in Settings), and whenever you
press **Start**. Press Start again to cancel. **Settings → Full re-sync** fetches every game
again, in case something looks wrong.

## Offline
Everything you've synced is available without Wi-Fi: games, achievements, badges, screenshots,
profile and awards. The bottom bar says "Offline · showing saved data", and **Start** retries.

Two things need a connection when you ask for them:
- Badges and icons that weren't downloaded yet (they appear as soon as you're online and open a
  screen that needs them).
- The profile's **See more** numbers (points in the last 7 and 30 days). The last values fetched
  stay available offline.

HTTPS needs the right time, and these devices have no clock battery. Right after power-on the
clock may still read 1970 until Spruce syncs it over Wi-Fi. Cheevos then says "Clock not set ·
connect to Wi-Fi" and waits.

## RAOfflineProxy
SpruceOS ships RAOfflineProxy, which lets you earn achievements without Wi-Fi: it keeps the
unlocks and sends them to RetroAchievements when you're back online. It works in casual mode only.
Turn it on in **Spruce Settings → RetroAchievements**.

Cheevos reads the proxy's queue and shows the unlocks that are still waiting:
- in **Recent unlocks**, first, marked "Pending sync";
- in **a game's achievements** and on **the achievement**, marked "Pending sync" or "Unlocked
  offline · waiting to sync";
- in **the games list**, counted in the bar (grey: casual) and flagged in the count, e.g.
  `34+2/47` (2 waiting).

**Settings → RAOfflineProxy** shows whether the proxy is on, online, how many unlocks are
waiting and how many games it can run offline. Cheevos only reads the proxy's data. It never
sends, changes or deletes its queue: the proxy does that itself.

## Data usage
A sync with no changes is a handful of small requests. The first sync downloads each game's
achievement list once, plus badges and icons as set in **Badge downloads**. After that, only
games that changed are downloaded again.
