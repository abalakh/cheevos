# RetroAchievements: API, client and the website's rules

Everything Cheevos knows about RetroAchievements (RA) comes from its public Web API, and the
look and counting rules come from the website's own source (RAWeb). The client lives in
`core/ra_client/`; profile numbers in `core/stats.py`.

## The client
- **Web API**: `https://retroachievements.org/API/API_*.php?y=<key>&u=<user>&...`, plus two
  resources of RA's v2 JSON:API for what v1 lacks about events (below). We never call the
  Connect API (`dorequest.php`); that belongs to emulators and the proxy.
- **Endpoints**:

  | Endpoint | Used for |
  |---|---|
  | `API_GetUserProfile` | Key validation, profile basics |
  | `API_GetUserSummary` (`g=1&a=10`) | Rank, TotalRanked, last game and rich presence |
  | `API_GetUserCompletionProgress` (`c=500&o=`) | Game list and change detection |
  | `API_GetGameInfoAndUserProgress` (`g=&a=1`) | Achievement definitions, unlock dates, game stats |
  | `API_GetUserAwards` | The Awards screen, the profile's beaten counts |
  | v2 `/v2/events?filter[id]=&include=awards` | Event titles, badges and award tiers (label, points, badge); 50 events a request |
  | v2 `/v2/event-achievements?filter[eventId]=&fields[...]=achievementPoints,event` | What an event is worth (its achievements' points), 100 rows a page, for earned tiers only |
  | `API_GetUserRecentlyPlayedGames` (`c=50`) | The "recent" set for the badge scope |
  | `API_GetAchievementsEarnedBetween` (`f=&t=`) | Latest 100 unlocks during sync; points in the last 7/30 days and the first hardcore unlock on demand (profile "See more" and 30-day chart); capped at 500 rows |

- **v2 API**: `https://api.retroachievements.org/v2/...`, JSON:API, the same Web API key in an
  `X-API-Key` header (RAWeb's `api-token-header` guard; never in the URL). RA's v1 API is
  frozen ("permanent maintenance mode", RAWeb `public/API/CODE_FREEZE.md`); new data goes to
  v2. Not yet in RA's published API docs, but served in production: verified on 2026-10-14
  with our key (HTTP 200, `x-ratelimit-limit: 60` a minute). Its requests share the app's
  `Pacer` like every other request. A refusal or odd answer is logged and skipped
  (`sync/events.py`); never "API key rejected", since v1 took the key.
- **Media**: `https://media.retroachievements.org/Badge/<BadgeName>.png` and `_lock.png`,
  `https://media.retroachievements.org<ImageIcon>`, and
  `https://media.retroachievements.org/UserPic/<User>.png`. The site's own badge art (Patreon,
  Certified Legend, developer and media contributions) is on its static host:
  `https://static.retroachievements.org/assets/images/badge/<name>.png`; `client.media` sends
  `/assets/...` paths there.
- **Transport**:
  - `http.client.HTTPSConnection` kept open per host (API, v2 API, media, static) with
    `ssl.create_default_context(cafile=$SSL_CERT_FILE)`. Measured on the Mini: the first
    request on a new connection takes 0.7–1 s (DNS and a TLS handshake on a Cortex-A7), later
    ones on the same connection about 0.1 s (about 7× faster), so connections are reused. With
    that, HTTPS is fast enough on the Mini.
  - On TLS errors (certificate dates, verification, protocol failures, or an unreadable CA
    bundle), retry over `http.client.HTTPConnection`. Only RA's four fixed hosts
    (`transport.RA_HOSTS`) may fall back; over HTTP the v2 key header is as exposed as v1's
    `y=`. Remember HTTP per host for that transport's lifetime; a new transport tries
    HTTPS again. DNS failures, timeouts, dropped sockets and HTTP statuses never cause a
    downgrade. No redirects are followed. The reachability HEAD uses this transport too.
  - The API host's `Date` updates the shared app clock (`core/clock.py`); media dates are ignored
    because CDN responses may be cached. The device clock and Spruce settings stay unchanged.
  - Timeouts: 10 s connect/read for the API, 20 s for media.
  - User-Agent: `Cheevos/<version> (SpruceOS <spruce version>; <PLATFORM>)`.
- **Rate limit**: RA limits requests per API key but publishes no numbers; its API docs only
  say rate limiting is enabled. Measured on 2026-10-06 with a 2,937-game account:
  - at ~2.6 requests/s (the old 0.3 s spacing), HTTP 429 within 7 s (`Retry-After: 1`), then
    one about every 5 s, and after about 9 of those `Retry-After: 600`;
  - at 1 request/s, none in 20 minutes (1,154 game details);
  - per key, not per IP: a keyless request from the same network still got a normal 401;
  - images: 5,101 downloads at ~20/s drew none.
- **Politeness**:
  - API calls share one `Pacer` (`ra_client/pacer.py`) across the whole app: the sync, the
    game worker, "See more" and the key check. It's a token bucket: after an idle spell, up to
    3 requests 1 s apart, then one every 3 s for extra headroom beyond the measured clean
    1 request/s. A sync with nothing new (4 requests) stays quick. No burst after a 429 pause.
  - Images use a separate pacer per client, with no burst and 0.25 s between starts. The sync
    downloads them itself, stored in batches of 25 per transaction; images needed while
    browsing come from one background worker. Disabling API pacing (`Pacer(0)` or a private
    client's `min_interval=0`) disables media pacing too, so unit tests and the desktop
    runner's recorded fixtures never wait for normal request slots.
  - HTTP 429 with a `Retry-After` of up to 10 s pauses every client, then retries (3 tries;
    exponential backoff without the header). A longer one fails at once with
    `RateLimitedError`: the sync stops, stores the time in `meta.rate_limited_until` and
    doesn't ask RA again before it ([sync-and-storage.md](sync-and-storage.md)).
  - 5xx retries with exponential backoff (3 tries).
  - Waits for a slot or a retry can be interrupted: Cancel and exit act at once.
- **Errors** map to typed exceptions: `AuthError`, `RateLimitedError`, `NetworkError`,
  `ApiPayloadError`, and `RequestCancelledError` for a cancelled wait.
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
  the last row's `Date` (`RaClient.unlocks_between`) for profile statistics. For Recent unlocks,
  search backwards in disjoint date windows and narrow every capped response before using
  it (`ra_client/recent.py`): reversing a capped response would miss the newest unlocks.
  Bounds come from RA's member/latest-unlock dates, not system time. The feed keeps one
  row per achievement at its newest returned event date and mode; it does not fabricate
  rarity from the endpoint's missing player statistics.
- **Awards:** `VisibleUserAwards` leaves out awards the player hid on the site, but the counts
  include them. Its order is the profile's (RAWeb `getUsersSiteAwards`: `DisplayOrder`, then
  date, type and tier), kept as `Award.position`. A mastered game usually holds a Beaten award
  too. `AwardType` is a label: "Mastery/Completion", "Game Beaten", "Event", "Site Event" (an
  event whose award counts as a site award), "Playtest", "Achievement Unlocks Yield",
  "Achievement Points Yield", "Patreon Supporter", "Certified Legend", "Media Contribution".
  `AwardData` is a game ID, an event ID, a site award ID or a tier, depending on the type, so
  awards are told apart by type and data together (`Award.key`). `AwardDataExtra` is 1 for
  hardcore on game awards and the earned tier otherwise; `display_award_tier` is the tier whose
  image the player chose to show. Site awards come without a title or image (RA's renderer
  supplies them).
- **No spoiler flag:** achievements carry only type tags (progression, win_condition, missable),
  set by developers since 2023; many older sets have none.
- **Not available through the Web API** (so not shown): casual rank, real last activity, role
  badges, forum stats, time-to-beat.

## Awards (the profile's galleries)
RAWeb's `site-award.php` (`SeparateAwards`, `RenderSiteAwards`, `RenderAward`) decides what
the profile shows; `core/awards.py` mirrors it:
- **Game Awards**: "Mastery/Completion" not on the "Events" console. Mastered (extra 1): gold
  border (`goldimage`), "Mastered on <date>"; completed: plain, "Completed on <date>".
- **Event Awards**: "Event", and "Mastery/Completion" on the "Events" console (old event
  games, drawn like games). Gold border.
- **Site Awards**: "Site Event", "Playtest" (only with an image), and the site's own badges:
  developer unlocks and points (`contribYield-<AwardData>`, `contribPoints-<AwardData>`, with
  RA's thresholds by tier, `PlayerBadge` in RAWeb), media contributions (`mediaContrib-<shown
  tier>`, the threshold of the earned tier), Patreon (`holoimage`, a 135° gold-orange-pink-
  violet-cyan-gold border, for the $2 tier, AwardDataExtra 2; gold otherwise) and Certified
  Legend. Wording: RA's titles; its tooltips' reasons are shortened to the threshold, which
  they put last, so the line fits beside the date (`strings.py`).
- **Never shown**: "Game Beaten" (the renderer has no branch for it) and unknown types.
- **Order**: each gallery keeps the list's order; galleries follow each other in the order of
  their first visible award.

### Event tiers
RA's tooltip for an event award (`RenderAward`): the image is the tier the player shows
(`display_award_tier`, else the earned one; the event's own badge if that tier has none); the
text is the tier earned. If the earned tier exists and needs fewer points than the whole event
(`points_required < legacyGame.points_total`), the title gets the tier's label (with the event
title stripped from its start, and only if the title doesn't already end with it) and the text
is "Awarded for earning at least N point(s)"; otherwise "Awarded for completing this event".
Tier numbers are indices, not hardcore flags.
- The v1 list has the event ID, the tier numbers and the event's own badge only. v2 `events`
  (tiers included) gives each tier's label, points and badge.
- **API gap (needs an upstream change):** no API states an event's total points. We add up
  its published achievements' points from v2 `event-achievements` (published only, for an
  ordinary key), which is what RA's `points_total` sums. v2 `events` has
  `achievementsPublished`, but it's a count, not points: event achievements are worth 1 to 50
  points, and on the 35-event account below 5 of the 14 tiered events had more points than
  achievements (10 worth 16). Asking RA to expose `pointsTotal` on v2 `events` would save these
  requests: RAWeb's `EventSchema` already joins the event's game, so it's one field
  (`games.points_total`). Measured: a 35-event account with 14 tiered awards needs 8 pages
  (about 710 rows, ~25 s at our pacing) on its first sync, then again after 30 days.
- Until the total is known (the request failed), a tier is described by its points, which is
  always true; before an event is fetched at all, RA's own title and image show with "Event
  award".
- Checked against a real 35-event account (2026-10-14): single-tier events whose tier is the
  whole event ("RetroAchievemas 2024", 6 of 6 points) read "completing this event", as on RA.

## Following the website
**Visual language** (from RAWeb's `PlayerGameProgressBar`, `AwardIndicator`,
`buildAwardLabelColorClassNames`):
- hardcore progress amber→gold, casual-only `neutral-500`;
- award dots gold (mastery family) or silver (beaten family), filled = hardcore, hollow = casual;
  RA draws them as CSS circles, not images;
- hardcore achievement badges and mastered game icons get a 2 px gold border (`goldimage`);
  casual achievement badges and completed game icons stay plain; event and most site badges
  are gold too, and the $2 Patreon badge holographic (`holoimage`, `Frame.HOLO`);
- light mode swaps gold for `yellow-600`.

`ui/pyui/bar_colors.py` mirrors this and judges a row's background from the theme's background
and highlight images (averaged once). Where the contrast is too low, it falls back to the theme's
text colour in three strengths; award indicators use contrasting black or white.

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
- The v2 API gets the key in an `X-API-Key` header, so its URLs (logged as resource names,
  e.g. `v2/events`) never hold it; headers are never logged or recorded.
- Prefer verified HTTPS. If TLS fails, HTTP is an automatic compatibility fallback, explicitly
  requested for devices with unset or incorrect clocks. It sends the Web API key and account
  data unencrypted; this tradeoff is documented in the wiki's Setup page. Never disable
  certificate verification on an HTTPS connection.
