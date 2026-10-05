# RetroAchievements: API, client and the website's rules

Everything Cheevos knows about RetroAchievements (RA) comes from its public Web API, and the
look and counting rules come from the website's own source (RAWeb). The client lives in
`core/ra_client/`; profile numbers in `core/stats.py`.

## The client
- **Web API** only: `https://retroachievements.org/API/API_*.php?y=<key>&u=<user>&...`.
  We never call the Connect API (`dorequest.php`); that belongs to emulators and the proxy.
- **Endpoints**:

  | Endpoint | Used for |
  |---|---|
  | `API_GetUserProfile` | Key validation, profile basics |
  | `API_GetUserSummary` (`g=1&a=10`) | Rank, TotalRanked, last game and rich presence |
  | `API_GetUserCompletionProgress` (`c=500&o=`) | Game list and change detection |
  | `API_GetGameInfoAndUserProgress` (`g=&a=1`) | Achievement definitions, unlock dates, game stats |
  | `API_GetUserAwards` | Awards wall |
  | `API_GetUserRecentlyPlayedGames` (`c=50`) | The "recent" set for the badge scope |
  | `API_GetAchievementsEarnedBetween` (`f=&t=`) | Points in the last 7/30 days; only on demand (profile "See more" and 30-day chart), 500 rows per page |

- **Media**: `https://media.retroachievements.org/Badge/<BadgeName>.png` and `_lock.png`,
  `https://media.retroachievements.org<ImageIcon>`, and
  `https://media.retroachievements.org/UserPic/<User>.png`.
- **Transport**:
  - `http.client.HTTPSConnection` kept open per host (API, media) with
    `ssl.create_default_context(cafile=$SSL_CERT_FILE)`. Measured on the Mini: the first
    request on a new connection takes 0.7–1 s (DNS and a TLS handshake on a Cortex-A7), later
    ones on the same connection about 0.1 s (about 7× faster), so connections are reused. With
    that, HTTPS is fast enough on the Mini.
  - Timeouts: 10 s connect/read for the API, 20 s for media.
  - User-Agent: `Cheevos/<version> (SpruceOS <spruce version>; <PLATFORM>)`.
- **Politeness**: RA publishes no rate limits, and none were seen.
  - API calls are serial, at least 300 ms apart (configurable).
  - Images: the sync downloads them itself, stored in batches of 25 per transaction; images
    needed while browsing come from one background worker.
  - HTTP 429 honours `Retry-After`; 5xx retries with exponential backoff (3 tries).
- **Errors** map to typed exceptions: `AuthError`, `RateLimitedError`, `NetworkError`,
  `ApiPayloadError`.
- Responses are parsed into dataclasses at the client boundary. No raw dicts leak past
  `ra_client`.
- `FixtureTransport` replays recorded JSON for tests and for the desktop runner's fixture mode.

## API gotchas
- **Two date formats:** `"2026-08-22T11:42:13+00:00"` and `"2026-08-21 17:02:50"`, both UTC.
- **Completion progress is incomplete:** `API_GetUserCompletionProgress` omits games played
  without any unlock. Merge in `API_GetUserRecentlyPlayedGames`.
- **Pseudo-achievement 101000001:** RA's "unsupported emulator/core" warning. RetroArch even
  saves a `-cheevo-101000001.png` for it. Ignore it everywhere.
- **Unauthenticated calls:** answered with 401 and
  `{"message":"Unauthenticated.","errors":[...]}`.
- **Sizes:** badges are ~3 KB, avatars ~7 KB, a game's details 30–55 KB.
- **The summary needs `g>=1`** to include `LastGame` (title, console, icon). Its `LastActivity`
  is always an empty stub and `Status` always "Offline"; `RichPresenceMsgDate` is the closest
  thing to a last-activity time. `Rank` is null below 250 hardcore points.
- **`API_GetAchievementsEarnedBetween`** returns at most 500 rows, oldest first: page on from
  the last row's `Date` (`RaClient.unlocks_between`).
- **Awards:** `VisibleUserAwards` leaves out awards the player hid on the site, but the counts
  include them. `DisplayOrder` is the player's own arrangement. A mastered game usually holds a
  Beaten award too.
- **No spoiler flag:** achievements carry only type tags (progression, win_condition, missable),
  set by developers since 2023; many older sets have none.
- **Not available through the Web API** (so not shown): casual rank, real last activity, role
  badges, forum stats, time-to-beat.

## Following the website
**Visual language** (from RAWeb's `PlayerGameProgressBar`, `AwardIndicator`,
`buildAwardLabelColorClassNames`):
- hardcore progress amber→gold, casual-only `neutral-500`;
- award dots gold (mastery family) or silver (beaten family), filled = hardcore, hollow = casual;
  RA draws them as CSS circles, not images;
- mastered game icons get a 2 px gold border (`goldimage`);
- light mode swaps gold for `yellow-600`.

`ui/pyui/bar_colors.py` mirrors this and judges a row's background from the theme's background
and highlight images (averaged once). Where the contrast is too low, it falls back to the theme's
text colour in three strengths.

**Profile numbers** (`core/stats.py`), after RAWeb's rules:
- subsets (recognised by "[Subset" in the title) and test kits never count as games;
- averages only consider sets of 6+ achievements and never Hubs or Events (consoles 100/101);
- "retail" leaves out tagged titles (~Demo~, ~Hack~, …) and homebrew consoles (71, 72, 80);
- casual-heavy players count casual unlocks in the recent points.

## Secrets
- The API key is plaintext on the SD card (`Saves/cheevos/apikey.txt`), like Spruce's RA
  password.
- Never log or format the key or full API URLs. `redact.py` wraps the logging record factory,
  so every record (ours and PyUI's) has `y=<...>` query values and the key itself masked: the
  message, the traceback and the stack. The key is registered as soon as it's known: when
  `credentials.py` reads or saves it, and when a client is created. Tests assert the key never
  appears in captured logs.
- **Typing the key:** PyUI logs any text it fails to draw (SDL errors happen when memory runs
  low), and a key being typed isn't registered yet. `ask_text(..., secret=True)` mutes PyUI's
  log while the keyboard is open.
- Players send their log (`Saves/spruce/cheevos-<device>.log`) with bug reports, so keep
  personal data out of it too. Today it holds no username or key; game titles appear in file
  paths.
- `scripts/record_fixtures.py` strips `y=` before saving; the key never reaches fixtures.
- Only HTTPS. Certificates are always verified; there's no `-k` fallback.
