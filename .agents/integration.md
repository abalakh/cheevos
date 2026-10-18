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
v1 uses only identifications that Spruce already made: RAOfflineProxy's
`cached_game_ids.txt` (game IDs only), read directly. Spruce no longer writes
`Saves/pyui-cheevos-cache.json`; its game list comes from the proxy too.

A game Spruce never identified isn't "on this device". The identification helper (below)
hashes one ROM the player picks in Spruce; scanning a whole library the same way, or reading
the helper's saved paths, could close that gap.

## Direct launch from Spruce (`core/identification/`, `platform/identify_rom.py`)
Spruce's game popup ("View achievement progress") resolves the selected ROM, then launches
`Cheevos/launch.sh --game-id N`. Spruce owns the menu, its first fast path, cancellation,
messages and the launch. Cheevos owns the rest, in a headless helper process.

**Why a Cheevos helper, not a proxy command:** the first version (SpruceOS #1885) added an
`identify-rom` command to Spruce's bundled RAOfflineProxy. A Spruce OTA then copied three
nightly-46 proxy files over a nightly-52 install; `rom_browser.py` imported a helper the newer
`network.py` no longer had, so the proxy couldn't start or stop, and RetroArch stayed pointed at
`127.0.0.1:8099`. Proxy updates also replace its directory, erasing any command we add. So we
never add or change proxy files: Cheevos ships the helper and reuses only the proxy's hashing
wrapper, from its own process.

1. **Spruce's mapping first.** Spruce trusts a loaded `CheevosCacheManager` path-to-game match,
   with no subprocess, ROM checks or cache access. A known association remains valid for
   viewing progress after a ROM is patched or replaced at the same path; this feature doesn't
   validate compatibility for submitting unlocks.
2. **The helper.** Otherwise Spruce runs
   `App/Cheevos/identify-rom.sh --path <absolute ROM path> --work-dir <scratch> --json` in a new
   session, polling for B with a 60 s timeout. Cancelling or timing out sends SIGTERM to the
   process group, then SIGKILL after 2 s. Spruce creates the scratch directory under
   `Saves/cheevos/cache/identify-work` and removes it afterwards, so cleanup also works after a
   forced kill. The launcher sources `appEnv.sh` (its output to stderr), sets `PLATFORM` and
   `PYTHONPATH`, changes to the app directory (Python puts the working directory on `sys.path`)
   and `exec`s `$SPRUCE_PYTHON -m cheevos.platform.identify_rom`. It never goes through
   `launch.sh` or `cheevos.__main__`, which start the UI. It adds no library path:
   `rom_hashing` finds `lib/<arch>/libraproxy_rchash.so` itself (it needs only libc).
3. **The result contract.** One JSON object on stdout; diagnostics go to the app log:
   `{"status":"matched","game_id":1479}`, `{"status":"no_match"}` or
   `{"status":"error","reason":"offline"}`. Exit status 0 for a match or a miss, 1 for an error.
   Reasons: `auth`, `offline` (RA unreachable), `network` (5xx or an unexpected status),
   `rate_limited`, `response` (malformed or refused answer), `file`, `hash`, `dependency` (the
   proxy's hasher is missing or incompatible), `unavailable` (anything unexpected); Spruce adds
   `timeout` and the `cancelled` status. Spruce treats malformed output or a crash as a failed
   lookup, keeps a structured error whatever the exit status, and accepts positive integer game
   IDs only (no booleans, no upper bound).
4. **Availability.** Spruce offers the action when Cheevos's `config.json` has
   `"gameProgress": 2` or more (1: `--game-id` launches; 2: also ships `identify-rom.sh`) and
   both scripts exist. A missing or broken proxy shows the `dependency` message instead.

**Inside the helper** (in this order; each step loads its code only when reached):
- **Saved paths:** `Saves/cheevos/cache/rom-identifications.json` (256 entries, at most
  256 KB, written atomically). It stores confirmed game IDs by absolute path, with no
  fingerprints or track dependency traversal. Version 2 reads earlier version-1 records and
  drops their obsolete metadata on the next save. Confirmed misses expire after seven days;
  errors are never saved, and a failed write never fails the lookup. Spruce-provided matches
  aren't copied into it. A saved path answers without loading the hasher, SQLite or network
  code (`tests/unit/test_identify_rom.py` checks the modules loaded).
- **The ROM:** not a file → `file`. Then the proxy's hasher loads
  (`platform/proxy_hasher.py`); any failure is `dependency`, logged, never a crash. The import
  sets `sys.dont_write_bytecode`: Python would otherwise write a `__pycache__` into the
  proxy's package (seen on a device after a proxy update, before the proxy had run).
- **Hash candidates** (`candidates.py`): the proxy's archive rules from
  `rom_browser.hash_candidates_for_manual_cache`, repeated here because `rom_browser` imports
  the proxy's service graph. A `.zip` or `.7z` with one ROM entry is hashed by content, one
  with none is an arcade set (hashed by file name), several ROMs can't be identified. A
  single-ROM ZIP streams in 64 KB chunks into a `rom-hash-*` directory inside the work
  directory, keeping the entry's file name (rc_hash picks the console by extension), and is
  removed after hashing, also on SIGTERM (the helper raises `SystemExit`). Never read the
  entry into Python or extract it to RAM-backed `/tmp`: those copies can exhaust the Mini's
  memory.
- **Hash to game** (`hash_lookup.py`), candidate by candidate in the hasher's order: the
  proxy's `api_cache` read-only (`gameid:<hash>` match, then `achievementsets:<hash>:<user>`,
  then a `gameid:` miss younger than a week), else RA's `dorequest.php?r=gameid&m=<hash>`.
  RA answers that request without credentials (RAWeb's `GetGameIdFromHashAction` isn't an
  authenticated action; rcheevos sends none), so identification needs no sign-in, token or
  Web API key, and no password is ever read. Only `{"Success":true,"GameID":0}` is a miss;
  401/403 are `auth` (403 `unsupported_client` is `response`), 429 `rate_limited`, anything
  malformed `response`. RA's answers are kept only in our path cache, never written to the
  proxy. Requests are spaced 0.3 s apart, like the proxy's.
- **Virtual game IDs:** for a hash RA hasn't marked compatible, `r=gameid` (and so the
  proxy's cache) answers the game's ID plus 1,000,000,000 (incompatible), 1,100,000,000
  (untested) or 1,200,000,000 (patch required), after RAWeb's `VirtualGameIdService`.
  `result.real_game_id` decodes them, logging the compatibility: the menu shows that game's
  progress, and Cheevos couldn't load a virtual ID. Saved entries are decoded too, since earlier
  Spruce builds stored RA's IDs as they came.

Cheevos opens the resolved game directly and refreshes only its details and visible images.
Start refreshes/cancels that game; B returns to Spruce. Home and account-wide auto-sync are
skipped. Opening the app normally retains its usual Home and sync behaviour.

## RAOfflineProxy (`core/proxy.py`)
The proxy takes RetroArch's unlocks while offline and sends them when Wi-Fi is back. It forces
Casual mode and refuses hardcore awards, so a queued unlock is always casual. Where queued
unlocks show in the UI: [product.md](product.md).
- **Detection**: `App/RAOfflineProxy/` exists, and the `enableOfflineProxy` setting is on in
  `spruce-config.json`.
- **Read its files directly. Never call its CLI or change its files.** The one code
  dependency is the identification helper's import of `raofflineproxy.rom_hashing` (above),
  in its own process: never `rom_browser`, `main`, `menu_sdl`, `storage` or the service.
  `platform/proxy_hasher.py` lists what it uses (`REQUIRED_FUNCTIONS`, `EXPECTED_MODULES`);
  `scripts/check_proxy_compat.py` checks a proxy build against them (TESTING.md).
- **Why not its CLI:**
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
