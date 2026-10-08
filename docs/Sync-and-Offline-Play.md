# Sync and offline play

## What syncing does
Cheevos keeps a copy of your RetroAchievements data on the SD card and shows that copy. Syncing
updates it:
1. Your profile (points, rank, last played game).
2. Your list of games with their progress.
3. The achievements of the games on your SD card and the games you played recently (see
   **Recent games** in [Settings](Settings.md)), plus any game that changed since you last
   downloaded it. Games not refreshed for 30 days are checked a few at a time, so changes
   RetroAchievements makes to old sets also arrive.
4. Your awards.
5. Badges and game icons (see **Badge downloads** in [Settings](Settings.md)).

**The first sync** spaces game downloads about 3 seconds apart: seconds for small libraries,
and a few minutes for one with thousands of games, because only the games you play are downloaded.
Image downloads are spaced a quarter of a second apart and can take longer for large sets.
Your games list, profile and awards are complete either way. You can browse while syncing. If a
sync is interrupted (you leave the app, the device sleeps, the battery runs out), the next one
carries on where it stopped.

**Other games** are downloaded when you open them: "Loading achievements…" for a second or two,
then they stay on the card. To have every game's achievements on the card, for example before a
trip without Wi-Fi, use **Settings → Download every game**. It spaces downloads about 3 seconds
apart (about 2.5 hours for 3,000 games, plus images), carries on in later syncs until it's done,
and can be stopped from the same place.

**When it runs:** when you open Cheevos (unless you turn that off in Settings), and whenever you
press **Start**. Press Start again to cancel.

## Offline
Everything you've synced is available without Wi-Fi: games, achievements, badges, screenshots,
profile and awards. The bottom bar says "Offline · showing saved data", and **Start** retries.

Three things need a connection when you ask for them:
- The achievements of a game you never opened, haven't played lately and that isn't on your
  SD card (unless you used **Download every game**).
- Badges and icons that weren't downloaded yet (they appear as soon as you're online and open a
  screen that needs them).
- The profile's **See more** numbers (points in the last 7 and 30 days). The last values fetched
  stay available offline.

Cheevos normally uses verified HTTPS. If the device's clock is unset or incorrect, or TLS fails
for another reason, it automatically retries over HTTP. **Sync Time via Network** in Spruce
isn't required. Cheevos uses RetroAchievements' response time for its own recent activity and
sync calculations, without changing the device's clock.

The HTTP fallback sends your Web API key and account data unencrypted. See [Setup](Setup.md).

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
A sync with no changes is a handful of small requests. The first sync downloads the achievement
lists of the games you play, plus badges and icons as set in **Badge downloads**. After that,
only games that changed are downloaded again.
