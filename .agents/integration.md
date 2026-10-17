# Spruce, RetroArch and RAOfflineProxy: what we read

Cheevos reads other software's files on the SD card and never writes them. It writes only
`Saves/cheevos/`, `/tmp/cheevos/` and its log. Every path comes from
`cheevos.platform.paths`. One exception: after the app exits, `launch.sh` copies the Web API
key into Spruce's `webApiKey` setting (RetroAchievements Settings), when Spruce has it, so a key
typed in the app shows there too. PyUI isn't running at that point, so it can't overwrite it.

## Credentials and first run (`core/credentials.py`)
- **Username**, first non-empty of:
  1. Spruce's settings: `Saves/spruce/spruce-config.json → menuOptions."RetroAchievements
     Settings".username.selected`.
  2. RetroArch's `cheevos_username` in `$SPRUCE_RA_CONFIG`
     (`Saves/ra-configs/retroarch-<PLATFORM>.cfg`). Spruce's "Manual" RA mode leaves (1) empty:
     the player signs in inside RetroArch instead.

  If both are empty, show: "Sign in to RetroAchievements in Spruce Settings or RetroArch
  first."
- **Web API key**, in this order:
  1. `Saves/cheevos/apikey.txt`: the first non-empty line, with whitespace stripped. Windows
     Notepad's encodings are read too (UTF-8 with a BOM, UTF-16 "Unicode"), since most users
     will write the file there. Quotes or labels around the key are not: common mistakes only.
  2. If the file is missing, or its line isn't 32 letters and digits, the setup screen says
     so and offers two ways out: A types the key (PyUI's `OnScreenKeyboard`; saved to the same
     file once accepted), B exits so the file can be fixed.
- **Validation**: a single `API_GetUserProfile` call, for typed keys.
  - On HTTP 401 or 403, or an error payload: "RetroAchievements rejected this key". Nothing is
    saved; back to the setup screen (or Settings).
  - On no network: the key is saved unchecked, and the next sync checks it.
  - A key from the file isn't validated at start (that needs the network). If a sync rejects it,
    the bottom bar shows "API key rejected" and Start opens the keyboard. A key entered there or
    in Settings is used at once and synced.
- The key is stored in plaintext, the same way Spruce stores the RA password, and is **never
  logged** ([retroachievements.md](retroachievements.md), "Secrets").

## Unlock screenshots (`core/screenshots.py`)
- RetroArch, with `cheevos_auto_screenshot = true`, writes
  `<screenshot_directory>/<rom basename>-cheevo-<achievementID>.png`. The `%s/%s-cheevo-%u`
  format is confirmed in all six Spruce RetroArch binaries. On Spruce, `screenshot_directory` is
  `/mnt/SDCARD/Saves/screenshots`.
- On launch, and when the directory's mtime changes, we index files matching
  `*-cheevo-<digits>.png` into a map `achievementID → [paths]`. If there are several, the newest
  mtime wins.
- **Ignore ID 101000001.** It is RA's pseudo-achievement for the "unsupported emulator / core"
  warning. RetroArch saves a real `…-cheevo-101000001.png` for it, and RAOfflineProxy strips it
  too.
- The setting is off by default in RetroArch. We only display screenshots; the wiki (Setup page)
  explains how to turn it on.

## On-device games (`core/local_games.py`)
v1 uses only identifications that Spruce already made (no new ROM hashing): RAOfflineProxy's
`cached_game_ids.txt` (game IDs only), read directly. Spruce no longer writes
`Saves/pyui-cheevos-cache.json`; its game list comes from the proxy too.

A game Spruce never identified isn't "on this device". Hashing ROMs ourselves would close that
gap: on demand per system, with the proxy's `libraproxy_rchash.so` (rcheevos `rc_hash`) through
ctypes, or by matching title and console.

## Direct launch from Spruce
Spruce's game popup resolves the selected ROM before launching `Cheevos/launch.sh --game-id N`.
The PyUI integration first trusts a loaded `CheevosCacheManager` path-to-game match, with no
ROM checks, helper call or fallback-cache access. A known association remains valid for viewing
progress after a ROM is patched or replaced at the same path; this feature doesn't validate
compatibility for submitting unlocks. Spruce's mapping takes priority over any saved fallback.

Paths Spruce doesn't know use `Saves/cheevos/cache/rom-identifications.json` (256 entries, at
most 256 KB). It stores helper-confirmed game IDs by absolute path, with no fingerprints or
track dependency traversal. Version 2 reads earlier version-1 records and drops their obsolete
metadata on the next save. Confirmed misses expire after seven days; errors/cancellations are
never cached. Spruce-provided matches aren't copied into this cache.

Only an unknown/expired path uses the proxy's `identify-rom` command (native rcheevos hashing
plus the existing hash-to-ID cache/RA lookup), with no game-set download or proxy service start.
This CLI call belongs to Spruce; Cheevos itself keeps the read-only proxy boundary below.
For a single-ROM ZIP, the proxy streams extraction in 64 KB chunks into a temporary
`rom-hash-*` directory on SD and removes it after hashing, including on failure. Spruce owns
the lookup's parent directory under `Saves/cheevos/cache/identify-work` and passes it as
`RAOFFLINEPROXY_HASH_WORK_DIR`, so it also cleans up after force-killing a stalled helper.
Without that override, the proxy uses its own data directory. The identification CLI also
unwinds cleanup on SIGTERM. Never read the whole entry into Python or extract it to RAM-backed
`/tmp`: those copies can exhaust the Mini's memory before the RA lookup.

Cheevos opens the resolved game directly and refreshes only its details and visible images.
Start refreshes/cancels that game; B returns to Spruce. Home and account-wide auto-sync are
skipped. Opening the app normally retains its usual Home and sync behaviour.

## RAOfflineProxy (`core/proxy.py`)
The proxy takes RetroArch's unlocks while offline and sends them when Wi-Fi is back. It forces
Casual mode and refuses hardcore awards, so a queued unlock is always casual. Where queued
unlocks show in the UI: [product.md](product.md).
- **Detection**: `App/RAOfflineProxy/` exists, and the `enableOfflineProxy` setting is on in
  `spruce-config.json`.
- **Read its files directly. Never call its CLI:**
  - Opening the proxy's `Storage` creates the database and tables if they're missing, so the CLI
    would create `proxy.sqlite3` on devices where the proxy never ran.
  - `pending-awards` prints human-readable text, not JSON.
  - Every call starts a new Python, which takes seconds on the Mini.
- **Files** (under `App/RAOfflineProxy/data/`, only if they exist):
  - `proxy.sqlite3`, opened read-only with `sqlite3.connect("file:…?mode=ro", uri=True)`, which
    can't create anything. Query `pending_awards WHERE status='pending'` and `api_cache` keys
    `patch:<gameId>:<user>` and `achievementsets:<hash>:<user>` for titles and points,
    mirroring the proxy's `list_pending_awards`.
  - `online_state.json` (`{"online": bool}`).
  - `cached_game_ids.txt` (one ID per line).
- **Bounded metadata reads**: pass only queued achievement IDs to the metadata lookup. Stream
  the current account's responses first (using the stripped, lowercase username), then other
  accounts only for unresolved IDs. Keep metadata only for those IDs and stop once all are
  resolved. Iterate list or dictionary achievements without copying the collection. Memory is
  bounded by the queue and one parsed response, rather than the whole proxy cache; an unknown
  ID can still require scanning every cached response. Match account suffixes literally with
  bound SQL parameters. Use the existing `cacheKey`/`responseBody` columns and indexed `GLOB`
  prefix lookup, with no new schema, JSON SQL extension or writes. Only after both patch-account
  passes, fill gaps from `achievementsets:` responses, current account first then other accounts.
  Accept direct `Achievements` lists or dictionaries, or otherwise nested `Sets[].Achievements`
  in either shape. A direct collection (even empty) takes priority over `Sets`. Require a positive
  integer root `GameId`; nested sets inherit it unless they provide their own positive integer
  `GameId` for a subset. Ignore malformed bodies, sets and achievements without hiding valid
  queue rows. Use the response's `Title`, with the usual game-ID and achievement-ID fallbacks.
- **An unlock's game** comes from our synced achievement lists first (`AppContext.pending_awards`),
  then from the proxy's `patch:` or `achievementsets:` entries. Spruce's RetroArch (1.22.2) only requests
  `r=achievementsets`, so the proxy caches `achievementsets:<hash>:<user>` while you play
  online. It writes `patch:` entries only when you cache a game from its own menu. Without a
  game, a queued unlock is missing from the games list's "+N". Resolving metadata alone does not
  add an entirely uncached achievement to Recent unlocks; that screen still needs synced details.
- Guarded by a schema check. Any `sqlite3.Error` on the read-only open (locked, or a WAL without
  its `-shm` file while the service starts) or anything unexpected means "proxy unavailable":
  the features hide and the next screen tries again. Never crash: the screens don't catch
  errors, so one escaping the reader would close the app. A missing proxy (older Spruce),
  a proxy that never ran (no `data/`) and a missing or broken `spruce-config.json` all read as
  "no proxy".
- We never flush, delete or write the proxy's queue or state.
