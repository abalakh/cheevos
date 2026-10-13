# Product: what Cheevos does

An on-device RetroAchievements hub for SpruceOS. It shows the player's profile, game progress,
achievement lists with badges, descriptions and unlock modes, mastery awards, unlocks waiting in
RAOfflineProxy, and the screenshots RetroArch took when achievements were unlocked.

The wiki (`docs/`) explains the screens to players. This file holds the rules behind them: data
sources, orderings, edge cases. Keep both in step. Keep the UI lean: prefer a section on an
existing screen, or one page with "[X] See more", over a new screen, and don't make one screen
reachable from several places.

Related: what we read from Spruce, RetroArch and the proxy is in
[integration.md](integration.md); the website's rules we copy (colours, profile numbers) are in
[retroachievements.md](retroachievements.md).

## Goals and non-goals

**Goals (v1)**
- A themed, controller-driven RA hub that looks native on every SpruceOS device.
- Works offline once synced. When Wi-Fi is up, it syncs incrementally in the background.
- Shows Hardcore and Casual progress side by side, plus unlocks still queued in RAOfflineProxy.
- Links achievements to their unlock screenshots when they exist.
- Quality good enough to ship publicly (GitHub release, then Spruce Game Nursery or an upstream
  PR).

**Non-goals (v1)**
- Launching games from the hub.
- Leaderboards.
- Earning or submitting achievements. RetroArch and RAOfflineProxy own that.
- Changing RetroArch settings. For example, we do **not** toggle `cheevos_auto_screenshot`.
- Multiple RA accounts.
- Social features (friends, feeds, messages, wall comments, forum stats).

## Home
A menu where each row summarises its screen: Profile · Games · Recent unlocks · Awards ·
Settings.
- **Profile**: avatar, username, Hardcore (`TotalPoints`), Casual (`TotalSoftcorePoints`) and
  RetroPoints (`TotalTruePoints`), and the rank `#Rank` ("Unranked" when null).
- **Games**: number of games, mastered or beaten. **Recent unlocks**: the latest one.
  **Awards**: mastered and beaten counts.
- **Sync status** lives in PyUI's bottom bar, not in a home row:
  - Home and Settings always show it with a Start hint: "✓ Synced 5 min ago · [START] Sync",
    "Games 3/12 · [START] Cancel", "Offline · showing saved
    data · [START] Retry".
  - Every other screen shows only progress while a sync runs, and the result for 5 s after it
    ends, with no hint. That keeps the bar clean on themes whose own A/B hints leave little room.
  - RAOfflineProxy's status is a row in Settings.

## Games list
- **Source**: every game in `API_GetUserCompletionProgress` (paginated, 500 per page), merged
  with `API_GetUserRecentlyPlayedGames` (up to 50). Completion progress omits games played
  without any unlock: the account the fixtures come from has 7 there vs 12 recently played.
- **Row**: game icon, title and `NumAwarded/MaxPossible`, then one of two views (Select toggles;
  the choice is saved as `game_list_details` in `settings.json`, and the bottom bar hints it):
  - **Progress** (default): a bar in place of the description line, drawn like RA's web client
    (`PlayerGameProgressBar`): hardcore unlocks gold, casual-only unlocks grey, side by side
    (30% hardcore + 35% casual-only = 65%). An award circle overlays the bar with its centre
    at the right endpoint: Mastered is filled gold with a bright rim and soft glow; Completed
    is a quiet hollow amber ring; Beaten is filled grey in hardcore or hollow grey in casual.
    Hollow centres cover the bar in the row's background colour. The percentage takes the
    award's colour (never 100% before the end, never 0% after an unlock). All bars in a list
    share one length, including rows without awards. Circle diameter and bar height follow
    the theme's description line height. Light rows get RA's light-mode darker gold. Where a
    theme's background fights these colours (a yellow theme), the bar falls back to the
    theme's text colour in three strengths, and circles use contrasting black or white while
    keeping filled vs hollow.
  - **Details**: console, plus the award or the last activity ("7 h ago").
- **Filters** (Y menu): All · On this device · In progress · Mastered or beaten · Not started.
- **Sort** (Y menu): Recent activity (default, by `MostRecentAwardedDate`) · Title · Console ·
  Completion %.
- **Coming back** from a game (or from a Y menu left unchanged) shows the list as it was, with
  the same selection and scroll position, unless its games changed meanwhile (a sync). Then it
  is rebuilt with the same game selected; so is a Select toggle. A new filter or sort starts at
  the top. Over 1,000 games, "Loading…" shows while the list is built.
- **On this device** is a best-effort match from existing Spruce data
  ([integration.md](integration.md), "On-device games"). Unmatched games are still listed under
  All.

## A game's achievements
- **Top bar**: the title and `unlocked/total`. Only the title is shortened, so the count always
  shows. A game with an award gets the same bundled award circle as the Games list, scaled
  smaller between them (including mastery glow); without
  one, a space separates them (a plain dot there would look like an award).
- **Row**:
  - badge: colour with a gold outline in hardcore, plain colour in casual or pending offline,
    `_lock` variant when locked; the same outline applies in the grid, card and Recent unlocks;
  - title, points, and a type tag (Progression / Win / Missable);
  - an unlock marker: Hardcore, Casual or Pending sync;
  - "screenshot" if an unlock screenshot exists.
- **View**: list or badge grid (Select). Going into a card and back returns to the same view and
  page; so does a Y menu left unchanged. A new filter or sort starts at the top.
- **Badge grid**: badges packed close together, like the achievement wall on RA profiles: 8×4
  at 640×480, 11×4 at 1280×720, 8×6 at 720×720, 6×8 at 480×800 (whole rows and columns at the
  theme's badge size, never shrunk to fit more). Every cell has room for a gold outline, so no
  badge moves with its unlock mode.
  - The selected badge is drawn last, about 10% larger, over its neighbours, inside a white
    focus ring with a black edge (a hardcore badge keeps its gold outline inside the ring).
  - Under the grid, two lines for the selection: title | points, then description | unlock mode
    (Hardcore, Casual, Pending sync or Locked) and type tag. Each part is shortened with "…"
    when needed, right-hand parts first; the card (A) has the full text. The description follows
    the card's spoiler setting ("Description hidden").
  - A thin scrollbar on the right when the set is longer than a screen; PyUI's `selected/total`
    counter stays in the bottom bar. D-pad, wraparound and L1/R1 (a screenful) are PyUI's.
- **Sort**: RA display order (default, `DisplayOrder` then achievement ID) · Unlocked first ·
  Locked first · Points (highest first) · Rarest first. The choice is shared by all games,
  including games opened from Awards, and saved in settings on app exit, like the list/grid view.
  An empty filter resets only the filter to All, keeping the chosen view and sort.
- **Filter**: All · Locked · Unlocked · Missable · Progression and Win.

## Achievement card
- Large badge (gold outline in hardcore), title, points with RetroRatio (`TrueRatio`), and type.
- **Description**: the card's main text, in the title font behind an accent rule (the body
  font when the title font would overflow). The "Hide locked descriptions" setting can hide it
  for locked achievements; X reveals it once ("[X] Reveal" in the bottom bar). RA has no
  spoiler flag (its site shows every description), so "Story only" uses RA's type tags:
  locked Progression and Win condition achievements, the story beats and the ending. Sets
  without type tags (mostly pre-2023) hide nothing in that mode. An unlock waiting in
  RAOfflineProxy's queue counts as unlocked.
- **Unlock info**: "Hardcore · 2026-09-30 21:14", or "Casual · …", or "Pending sync · queued
  …", or "Locked".
- **Rarity**: `NumAwarded / NumDistinctPlayers` as a percentage, for both modes. A card
  opened from the independent Recent feed can lack game statistics: show unknown rarity,
  draw its saved content immediately, and load the statistics in the background online.
- **Screenshot**: a preview if one exists; A opens it full screen ("[A] Full screen" in the
  bottom bar): no bars, black around it, as large as the screen allows and still sharp (enlarged
  by the next whole factor with nearest-neighbour, then shrunk to fit).

## Recent unlocks
A feed of the latest 100 distinct unlocks across games, newest first, fetched during sync
and cached separately from complete game sets. Browsing it uses saved definitions and game
titles, even for games whose full sets were never downloaded. Pending proxy unlocks come
first, marked; already-online entries are not duplicated. A row opens the achievement card.

## Awards wall
- A grid of game icons from `API_GetUserAwards` (`VisibleUserAwards` of type
  "Mastery/Completion" and "Game Beaten"; `AwardDataExtra` 1 = hardcore).
- One tile per game, with its highest award: Mastered > Completed > Beaten > Beaten (casual).
  A mastered game usually holds a Beaten award too.
- Tiles: the game icon framed in RA's colours. RA draws mastered icons with a 2 px gold border
  (`goldimage`); we extend that with its award-indicator colours. Mastered: thick gold.
  Completed: plain. Beaten: thick silver. Beaten (casual): thin silver. The caption is the
  game title.
- Y: filter (all / mastered and completed, RA's own showcase / beaten) and sort (newest first,
  site order = the player's own `DisplayOrder` on RA, title, console). The top bar shows the
  count.
- A opens that game's achievement list.

## Profile (after RA's own profile page)
One page, scrolled with the D-pad (up/down: a row, L1/R1: a page; a thin scrollbar on the
right; `ui/screens/page.py`). No social features (wall, forum stats, followers), and no links to
other screens. Top to bottom:
- **Account:** avatar, name, rank "#N of M · top x%", member since, last active (rich presence
  time), then hardcore points, casual points and RetroPoints.
- **Last played:** the summary's last game (`g=1`): icon, title, console, when, rich presence.
- **Player stats:** achievements unlocked (hardcore, casual), games beaten (retail count),
  RetroRatio, started games beaten.
- **"[X] See more"** (like RA): points in the last 7 and 30 days, average points per week,
  average completion, a 30-day points chart, and every console in the table below. Requests are
  made when X is pressed, both `API_GetAchievementsEarnedBetween`:
  - the recent points, kept 10 minutes and stored for offline use;
  - once, the first hardcore unlock for points per week (RA counts weeks since it). The cache
    doesn't hold every game, so it can't tell; one request from the "member since" date
    returns it as the first row. Stored for good.
- **Games by console:** a table of games played, beaten and mastered per console (cumulative:
  mastered games count as beaten), most recently played console first, with a total row over
  all of them. Only the five latest show until See more ("and N more consoles"), so big
  libraries keep a short page.

The numbers follow RA's own counting rules (`core/stats.py`; see
[retroachievements.md](retroachievements.md), "Following the website").

## Unlocks waiting in RAOfflineProxy (no screen of their own)
Queued unlocks appear where unlocks do. The proxy forces Casual mode, so they're always casual.
- **Recent unlocks:** first, labelled "Pending sync".
- **A game's achievements:** "Pending sync" with the unlocked badge.
- **The achievement card:** "Unlocked offline · waiting to sync since …".
- **The games list:** in the count ("34+2/47") and in the bar's grey casual part. The details
  view adds "2 not synced". Unlocks RA already has are not counted twice.
- **Settings → RAOfflineProxy** (only when it's installed): "On · offline · 2 waiting · 5 games
  cached", or "Off". A explains what the proxy does, or how to turn it on in Spruce.

How the queue is read: [integration.md](integration.md), "RAOfflineProxy".

## Settings
Stored in `Saves/cheevos/settings.json`.

| Setting | Default | Options |
|---|---|---|
| Badge downloads | On-device + recent | On-device + recent · All games (whose achievements are downloaded) · None (download while browsing online) |
| "Recent" window | 30 days | 7 · 30 · 90 days. Also decides which games' achievements every sync keeps ([sync-and-storage.md](sync-and-storage.md)). |
| Hide locked descriptions | Off | Off · Story only (Progression and Win condition tags) · All |
| RAOfflineProxy | — | Read-only status, shown when the proxy is installed |
| Auto-sync on open | On | On · Off |
| Actions | — | Sync now · Download every game (every game's achievements; resumes until done; reads "Stop downloading every game" until then) · Re-enter API key · Clear image cache (shows size) |
| About | — | Version, license (MIT), credits: PyUI (Copyright (c) 2025 Christopher Jacobs; its license requires this user-facing credit), RetroAchievements as the data source |

The file also remembers `game_list_details` (the games list view), `achievement_grid` (the
achievement list/grid view) and `achievement_sort` (the achievement sort, initially `"order"`
for RA display order). Achievement preferences are shared by all games. Changes take effect in
memory immediately and are written once on app exit, only if they changed.

## Controls
These follow the conventions of Spruce's own menus (see [pyui.md](pyui.md), "Buttons"): X acts
on the highlighted item, Start is free in lists, Select switches the view.

| Button | Action |
|---|---|
| D-pad | Move |
| A | Open / confirm |
| B | Back |
| Start | Sync, or cancel the running sync, on every screen except popups and the keyboard. After "API key rejected": enter a new key |
| Y / MENU (tap) | Options popup: filter and sort (games, awards); view, filter and sort (a game's achievements) |
| X | Reveal a hidden (spoiler) description on the achievement card (per-item, like PyUI); "See more" on the profile |
| Select | Games: progress bars ↔ details. A game's achievements: list ↔ grid (like PyUI's game lists) |
| L1 / R1 | Page up / down (PyUI default) |
| MENU (hold) | Reserved by Spruce (game switcher) |

Screen-specific buttons are hinted in the bottom bar ("[Y] Filter", "[SELECT] Details",
"[A] Full screen"); when space runs out, later hints go first. Themes ship X, Y and START badges;
missing ones (A, Select) are generated in the style of the theme's START badge. Message pages
hint "[A] OK", and the setup key screen "[A] Enter key [B] Exit": the bar is installed before
setup starts, with no sync status and Start doing nothing.

**On-screen keyboard** (PyUI's, for the Web API key): A types the highlighted key, B deletes
(cancels when empty), Start submits, L1 is shift, R1 caps lock. PyUI's keyboard draws no hints,
so the bridge shows "[START] Done [B] Delete [L1] Shift [R1] Caps" in the bottom bar.

## Visual style (a "gaming app" feel)
- **Themed throughout**: fonts, colours, backgrounds and top bar come from the active Spruce
  theme through PyUI.
- **RA pixel art carries the screens**:
  - game icons in game lists;
  - colour badges for unlocked achievements, a gold outline for hardcore unlocks, and RA's
    `_lock` badges for locked ones; pending offline unlocks stay plain and coloured;
  - the player's avatar on the profile row and profile screen.
- **Menu and status icons**: original Cheevos outlines (MIT) in the SPRUCE theme's style,
  from `assets/icons/ui/`: 70 px canvases, 4 px rounded strokes, caps and joins. All themes
  use the same SPRUCE gold (`#D7B45F`); the theme still supplies the layout, fonts and
  backgrounds. Pre-rendered list and fallback sources are 96 px below 1000 px screen width,
  144 px above, so curves stay clean when PyUI fits them into the icon column. Bottom-bar
  icons stay at 24/48 px because they are drawn at their natural size. Every row gets an icon;
  a missing image falls back to an outline, so columns stay aligned. A badge not downloaded
  yet shows a gold trophy if unlocked and a grey lock (`lock-muted`, rendered in SPRUCE's
  muted text colour, `#7C6F64`) if locked, so the state reads at a glance, as RA greys out
  locked badges. There is no third-party icon set.
- **App icon**: an original trophy outline in the SPRUCE theme's app-icon style (4 px rounded
  stroke, 10 px padding, `#D7B45F`), from `assets/icons/cheevos.svg`, rendered at 105 px by
  `scripts/render_icons.py` and shipped as `cheevos.png`. Themes can override it with
  `icons/app/cheevos.png`.
- **Text hygiene**:
  - Emoji and pictographs (e.g. in rich presence) are stripped, because theme fonts can't draw
    them. Accented letters a font lacks become the plain letter.
  - Top-bar titles are truncated with "…" so they clear the clock and battery icons.

## Offline and error behaviour

| Situation | Behaviour |
|---|---|
| No Wi-Fi, cached data exists | Open normally. The bottom bar shows "Offline · showing saved data". Pending proxy unlocks still show. |
| No Wi-Fi, no cache | Open on empty lists. The bottom bar shows "Offline · showing saved data"; Start syncs once online. A key typed during setup is saved unchecked. |
| Clock unset or incorrect, or TLS unavailable | Retry over HTTP automatically, without another screen or hint. Use RA's response time for app calculations; leave Spruce's clock and settings unchanged. The unencrypted API-key tradeoff is documented in Setup. |
| Key rejected (file typo, or reset on the site) | Stop sync. The bottom bar shows "API key rejected" and Start opens the keyboard; a key RA accepts is saved and synced at once. Cache stays usable. |
| RA down (5xx, timeouts) | Back off (3 tries). The bottom bar shows "RetroAchievements unavailable". |
| RA asks us to slow down (HTTP 429) | Pauses of up to 10 s are waited out. A longer one stops the sync: the bottom bar shows "RetroAchievements asked to wait N min" with no Retry hint, and no sync sends a Web API request before then. A credential-free HEAD may refresh app time. Cached data stays usable. |
| Power-off mid-sync | Resumes next run. Per-game commits mean the DB is never half-written for a game. |
| A game whose achievements were never downloaded | Opening it loads them: "Loading achievements…" (B backs out; the fetch still completes), about a second on a Mini. Offline, or when RA fails, it says the achievements aren't downloaded yet and why (Wi-Fi, key, RA's pause). |
| Proxy missing or unreadable | Hide the Settings status row and pending markers. |
| Theme lacks an asset we use | Fall back to our bundled icons (`cheevos/res/`) or generate it (button badges). |
| The app can't start (PyUI import, bootstrap, any crash) | `launch.sh` sees the non-zero exit, appends stderr to the app log (errors before logging starts only reach stderr), and shows "Cheevos couldn't start" with the log's path through `App/PyUI/launch.sh -msgDisplay` (PyUI's launcher sets up every platform's display). Verified on the Mini. |
| Unknown platform | `launch.sh` shows "Cheevos doesn't support this device yet" the same way. |
