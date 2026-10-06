# Sync and storage

How RA data gets onto the SD card and stays fresh: the caches (`core/storage/`), the sync engine
(`core/sync/`) and the threads around them.

## Storage

**Rule: user data lives in plain files; every database is a disposable cache.** Nothing a user
entered or chose is stored in SQLite. Every database can be deleted at any moment; the app
then recreates it and re-syncs. There are no schema migrations: when a cache's
`schema_version` doesn't match the code (an app update), or the file is unreadable or corrupt,
the app deletes it and starts fresh.

| What | Where | Kind | Notes |
|---|---|---|---|
| API key | `Saves/cheevos/apikey.txt` | User data | Plain text, user-editable |
| Settings | `Saves/cheevos/settings.json` | User data | JSON, written atomically (temp file + rename). Unknown keys are ignored and invalid values fall back to defaults. |
| PyUI view state | `Saves/cheevos/pyui-state.json` | Cache | PyUI's last selections, kept apart from the launcher's own state. |
| RA data cache | `App/Cheevos/cache/data.db` | Cache | SQLite: profile, games, achievements, awards, sync state. Rebuildable from RA. |
| Image cache | `App/Cheevos/cache/media.db` | Cache | SQLite blobs keyed `badge/<BadgeName>[_lock]`, `icon/<gameId>`, `avatar/<user>`. Kept separate so "Clear image cache" doesn't drop RA data. |
| Image scratch | `/tmp/cheevos/media/` | Cache | The images the current screen needs, extracted from `media.db` because PyUI loads images by path (~17 ms per 40 badges). tmpfs is RAM, so it's bounded: 4 MB, LRU, counted in whole 4 KB pages (a 3 KB badge takes a page). |
| Drawing scratch | `/tmp/cheevos/scaled/` | Cache | Generated PNGs (swatches, award dots, button glyphs), and in `sharp/` the enlarged screenshots: only the newest 4 (up to 1.4 MB each). |
| Log | `Saves/spruce/cheevos-$PLATFORM.log` | — | Spruce's convention. Rotating, 1 MB × 2. |

- `Saves/` survives Spruce updates and app reinstalls, and Spruce's backup app includes it.
  It therefore holds only small files: the two user files and PyUI's view state.
  `App/Cheevos/cache/` can be wiped freely.
- Both databases use `journal_mode=DELETE` and `synchronous=NORMAL`. Writes are short
  transactions on the sync thread.
- The pending proxy queue is **not** copied into our cache. We read it live
  ([integration.md](integration.md)), so it can never go stale or out of step with the proxy.

**Schema sketch for `data.db`** (`core/storage/schema.py`, versioned through
`PRAGMA user_version`; a mismatch means recreate):

```sql
meta(key TEXT PRIMARY KEY, value TEXT)  -- username, last sync, unfinished full download,
                                        -- RA's pause, unlock window, first hardcore unlock
profile(username TEXT PRIMARY KEY, json TEXT, synced_at INTEGER)
games(game_id INTEGER PRIMARY KEY, title, console_id, console_name, image_icon,
      max_possible, num_awarded, num_awarded_hc, most_recent_awarded_at, highest_award_kind,
      highest_award_at, last_played_at, detail_synced_at, detail_fingerprint)
achievements(achievement_id INTEGER PRIMARY KEY, game_id, title, description, points,
      true_ratio, badge_name, display_order, type, num_awarded, num_awarded_hc,
      earned_at, earned_hc_at)
game_stats(game_id PRIMARY KEY, num_distinct_players, num_players_casual, num_players_hc)
awards(game_id, kind, title, console_id, console_name, image_icon, awarded_at, display_order,
       PRIMARY KEY(game_id, kind))
```

The profile's recent-points window (`API_GetAchievementsEarnedBetween`) is stored too, for
offline use. If the configured username differs from `meta.username`, the cache is for another
account and is recreated.

## The device constraints behind this
- **SD card:** FAT32 with 32 KB clusters, mounted `dirsync`. Many small files are slow and waste
  space: 200 badges as files took 0.70 s and 6.3 MB of disk on the Mini, as SQLite blobs 0.12 s
  and 832 KB. Hence images as blobs in `media.db`.
- **SQLite:** WAL needs shared memory and is unreliable on FAT32, so all databases use
  `journal_mode=DELETE`. A `kill -9` during a full re-sync leaves `PRAGMA integrity_check` ok and
  no journal file; the next sync carries on (`full_resync_since`).
- **Blob scans:** a badge spills into overflow pages, and a column stored after a blob is read
  by walking them. So a scan of `media` reads the whole file, even for `SUM(size)`: 2.4 s for
  48 MB on the Mini. Settings shows the size of `media.db` (`os.stat`, 0.1 ms) instead.
- **`/tmp`:** a 49 MB tmpfs, which is RAM. Keep extracted images bounded; the app deletes both
  scratch folders on exit.
- **Clock:** there's no RTC. Before NTP sync the clock reads 1970, and HTTPS fails. Check
  `net.clock_plausible` before syncing.

## Sync engine
It runs on a background worker thread. The UI reads committed DB state and a thread-safe
`SyncProgress` snapshot.

1. **Pre-flight**:
   - Connectivity: interface up plus `HEAD https://retroachievements.org` with a 3 s timeout.
   - Clock plausibility: year ≥ 2026. If the clock is wrong, show "Clock not synced" and skip.
   - Rate limit: if RA asked for a long pause (`meta.rate_limited_until`) and the time isn't up,
     stop with "RetroAchievements asked to wait N min" without a request. A finished sync
     clears it.
2. **Profile**: `GetUserSummary` (`g=1` for the last game).
3. **Game list**: every page of `GetUserCompletionProgress`. Upsert the `games` rows. Compute a
   fingerprint per game: `(MaxPossible, NumAwarded, NumAwardedHardcore, MostRecentAwardedDate,
   HighestAwardKind)`.
4. **Awards**: `GetUserAwards`. One request, before the details, so the awards wall and the
   home screen are complete as early as the games list.
5. **Plan detail fetches.** A game's details take one request, about a second at RA's pace,
   so a sync doesn't fetch every game: 2,937 games would take ~51 min. It keeps a **working
   set**: games on this device (`local_games`) and games played or unlocked within the "Recent
   games" window (30 days by default). Other games are fetched when opened (the game worker,
   below). Planned:
   - never fetched, for a game in the working set;
   - the fingerprint changed, for any cached game;
   - the details are older than 30 days, for any cached game. At most 20 of these per sync,
     oldest first, so revised sets slowly converge;
   - every game, while "Download every game" is unfinished (`meta.full_resync_since`). It
     resumes in every later sync until a sync finishes, unless the user stops it in Settings.
6. **Fetch details**: `GetGameInfoAndUserProgress` per planned game, committed **one game at a
   time**. An interrupted sync (power-off, sleep, app exit) resumes from the remaining plan on the
   next run.
   - Then **Recent unlocks coverage**: uncached games, newest last unlock first, until the
     newest 100 cached unlocks (`RECENT_UNLOCK_COUNT`, what Recent unlocks shows) are newer than
     the next game's last unlock. Usually nothing: recent games are in the working set. A
     player with no activity lately gets their last few games.
   - The test account (2,937 games) has 60 games in a 30-day working set: about a minute.
7. **Badges** (the "Badge downloads" setting):
   - On-device + recent: games in `local_games` plus games played or unlocked within the recent
     window.
   - All: every game whose details are cached.
   - None: nothing is downloaded during sync.
   - Only the variant matching the current state is fetched: colour if unlocked, `_lock` if
     locked. This halves the file count. A newly unlocked achievement gets its colour badge on the
     next sync. In every mode, missing images are fetched lazily while browsing online
     (`lazy_media.py`).
   - The `_lock` blob stays after an unlock, on purpose: it's a few KB, it's needed again if
     progress is reset on RA, and "Clear image cache" removes it.
8. **Local matching refresh** ([integration.md](integration.md), "On-device games").

- **Triggers**: auto on app open when the network is up and the setting is on; Start on any
  screen; Settings → "Sync now" / "Download every game".
- **Cancellation**: sync stops at the next safe point when Start is pressed again or the app
  exits. A wait for the next request slot or a retry ends at once (the client raises
  `RequestCancelledError`).
- **Progress**: phase, `done/total`, current game title, and an ETA from a moving average.

`python -m cheevos.core.sync` runs a sync without the UI ([TESTING.md](../TESTING.md)).

## Threads
- **UI thread**: PyUI and SDL only.
- **Sync thread**: network and DB writes.
- **Image worker**: one thread fetching images needed on screen (`LazyMediaFetcher`), with its
  own cache connection. Not a FIFO: an image for the screen goes ahead of everything waiting
  (in draw order), asking again moves a waiting image up, the next page's images wait at the
  back, and when the visible rows change the UI drops whatever is still waiting
  (`MediaResolver.new_window`). So a jump to the end of a long list waits for its own screen
  only ([pyui.md](pyui.md), "Downloads follow the visible rows").
- **Game worker**: one thread fetching the achievements of a game the user opens when they
  aren't cached (`DetailFetcher`, `core/sync/detail_fetch.py`), with its own client and cache
  connection. The latest request goes first. It checks the clock and RA's stored pause before
  asking, stores a long pause for the sync to respect, and reopens its client after a key
  rejection. The game screen shows "Loading achievements…" and polls it every input tick; B
  backs out and the fetch still completes. A game it fetched after the sync planned the same
  game isn't fetched again by the sync.
- **SQLite**: one connection per thread. Writes happen on the sync thread and the game worker,
  one short transaction per game (the 5 s busy timeout covers the other's writes), plus small
  `meta` writes from the UI (the unlock window, stopping "Download every game"). The UI never
  waits on the network, except for "See more", behind a Loading page.
- **Noticing changes:** `DataCache.version()` changes after any write to `data.db`: SQLite's
  `PRAGMA data_version` for other connections, plus the UI connection's own `total_changes`.
  It reads no table, so the games list checks it on every visit and reads the games again only
  when it changed.
- **Request pacing**: every thread that calls the Web API takes its slots from the app's one
  `Pacer`, so together they stay within a short burst, then 1 request/s
  ([retroachievements.md](retroachievements.md), "Politeness").
