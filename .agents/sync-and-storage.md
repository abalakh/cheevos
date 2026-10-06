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
meta(key TEXT PRIMARY KEY, value TEXT)  -- username the cache belongs to, last sync times, plan
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
2. **Profile**: `GetUserSummary` (`g=1` for the last game).
3. **Game list**: every page of `GetUserCompletionProgress`. Upsert the `games` rows. Compute a
   fingerprint per game: `(MaxPossible, NumAwarded, NumAwardedHardcore, MostRecentAwardedDate,
   HighestAwardKind)`.
4. **Plan detail fetches** for games where any of these hold:
   - never fetched;
   - the fingerprint changed;
   - the details are older than 30 days. At most 20 of these per sync, oldest first, so revised
     sets slowly converge;
   - a Full re-sync was requested (fetch everything).
5. **Fetch details**: `GetGameInfoAndUserProgress` per planned game, committed **one game at a
   time**. An interrupted sync (power-off, sleep, app exit) resumes from the remaining plan on the
   next run.
6. **Awards**: `GetUserAwards`.
7. **Badges** (the "Badge downloads" setting):
   - On-device + recent: games in `local_games` plus games played or unlocked within the recent
     window.
   - All: every synced game.
   - None: nothing is downloaded during sync.
   - Only the variant matching the current state is fetched: colour if unlocked, `_lock` if
     locked. This halves the file count. A newly unlocked achievement gets its colour badge on the
     next sync. In every mode, missing images are fetched lazily while browsing online
     (`lazy_media.py`).
   - The `_lock` blob stays after an unlock, on purpose: it's a few KB, it's needed again if
     progress is reset on RA, and "Clear image cache" removes it.
8. **Local matching refresh** ([integration.md](integration.md), "On-device games").

- **Triggers**: auto on app open when the network is up and the setting is on; Start on any
  screen; Settings → "Sync now" / "Full re-sync".
- **Cancellation**: sync stops at the next safe point when Start is pressed again or the app
  exits.
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
- **SQLite**: one connection per thread. Writes happen only on the sync thread, in short
  transactions. The UI never waits on the network.
