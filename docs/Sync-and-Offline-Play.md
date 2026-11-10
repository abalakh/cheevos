# Sync and offline play

## What syncing does
Cheevos keeps a copy of your RetroAchievements data on the SD card and shows that copy. Syncing
updates it:
1. Your profile (points, rank, last played game).
2. Your list of games with their progress.
3. Your awards and latest 100 unlocks. Recent unlocks are saved separately, so they don't
   require downloading entire achievement lists for old games. For event awards, the event's
   tiers too (what each tier needs, and its badge), once per event and again after 30 days.
4. Achievements for games on your SD card and games with play or unlock activity in the last
   30 days. Cached games that changed are refreshed too. Games last refreshed 30 or more days
   ago are checked a few at a time to pick up edits to old achievement sets.
5. Badges for on-device games, games active in the last 30 days, Recent unlocks, and event and
   site awards. Sync also downloads game icons for your entire library.

**The first sync** spaces game downloads about 3 seconds apart: seconds for small libraries,
and a few minutes for one with thousands of games, because only the games you play are downloaded.
Image downloads are spaced a quarter of a second apart and can take longer for large sets.
Your games list, profile and awards are complete either way. You can browse while syncing. If a
sync is interrupted (you leave the app, the device sleeps, the battery runs out), the next one
carries on where it stopped.

The bottom bar shows the current stage. During game downloads it shows, for example,
**Games 3/12**, with a fixed total for that stage. While finding recent unlocks, it shows how
many it has found; the number of history requests needed isn't known ahead of time.
During a full download, the image stage shows how many images it has processed so far.

**Other games** are downloaded when you open them: "Loading achievements…" for a second or two,
then they stay on the card. To keep your entire library's achievements and badges on the card
for a trip without Wi-Fi, use **Settings → Download every game**. It spaces game requests about
3 seconds apart (about 2.5 hours for 3,000 games, plus images) and resumes in later syncs.
You can stop it from the same menu.

**When it runs:** when you open Cheevos (unless you turn that off in Settings), and whenever you
press **Start**. Press Start again to cancel.

## Offline
Everything you've synced is available without Wi-Fi: games, achievements, recent unlocks,
badges, screenshots, profile and awards. The bottom bar says "Offline · showing saved data",
and **Start** retries.

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
Recent unlock queries use the account's member date and latest unlock date from
RetroAchievements, so they also work when the device still shows 1970.

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
A sync with no changes is a handful of small requests. The first sync downloads the achievements
and badges of the games on your SD card and the games you played in the last 30 days, plus every
game's icon. After that, only games that changed are downloaded again.
