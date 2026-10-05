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
    "Syncing 3/12 · Final Fantasy Tactics Advance · [START] Cancel", "Offline · showing saved
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
    (30% hardcore + 35% casual-only = 65%). Then RA's award dot (gold for Mastered/Completed,
    silver for Beaten; filled for hardcore, hollow for casual) and the percentage in the
    award's colour (never 100% before the end, never 0% after an unlock). All bars in a list
    share one length. Light rows get RA's light-mode darker gold. Where a theme's background
    fights these colours (a yellow theme), the bar falls back to the theme's text colour in
    three strengths, and the dots keep filled vs hollow.
  - **Details**: console, plus the award or the last activity ("7 h ago").
- **Filters** (Y menu): All · On this device · In progress · Mastered or beaten · Not started.
- **Sort** (Y menu): Recent activity (default, by `MostRecentAwardedDate`) · Title · Console ·
  Completion %.
- **On this device** is a best-effort match from existing Spruce data
  ([integration.md](integration.md), "On-device games"). Unmatched games are still listed under
  All.

## A game's achievements
- **Top bar**: the title and `unlocked/total`.
- **Row**:
  - badge: colour when unlocked, `_lock` variant when locked;
  - title, points, and a type tag (Progression / Win / Missable);
  - an unlock marker: Hardcore, Casual or Pending sync;
  - "screenshot" if an unlock screenshot exists.
- **View**: list or badge grid (Select).
- **Sort**: display order (default) · Unlocked first · Locked first · Points · Rarity.
- **Filter**: All · Locked · Unlocked · Missable · Progression and Win.

## Achievement card
- Large badge, title, points with RetroRatio (`TrueRatio`), and type.
- **Description**: the card's main text, in the title font behind an accent rule (the body
  font when the title font would overflow). The "Hide locked descriptions" setting can hide it
  for locked achievements; X reveals it once ("[X] Reveal" in the bottom bar). RA has no
  spoiler flag (its site shows every description), so "Story only" uses RA's type tags:
  locked Progression and Win condition achievements, the story beats and the ending. Sets
  without type tags (mostly pre-2023) hide nothing in that mode. An unlock waiting in
  RAOfflineProxy's queue counts as unlocked.
- **Unlock info**: "Hardcore · 2026-09-30 21:14", or "Casual · …", or "Pending sync · queued
  …", or "Locked".
- **Rarity**: `NumAwarded / NumDistinctPlayers` as a percentage, for both modes.
- **Screenshot**: a preview if one exists; A opens it full screen ("[A] Full screen" in the
  bottom bar): no bars, black around it, as large as the screen allows and still sharp (enlarged
  by the next whole factor with nearest-neighbour, then shrunk to fit).

## Recent unlocks
A feed of the latest 100 unlocks across games, newest first, built from the local DB with no
extra API calls. Pending proxy unlocks come first, marked. A row opens the achievement card.

## Awards wall
- A grid of game icons from `API_GetUserAwards` (`VisibleUserAwards` of type
  "Mastery/Completion" and "Game Beaten"; `AwardDataExtra` 1 = hardcore).
- One tile per game, with its highest award: Mastered > Completed > Beaten > Beaten (casual).
  A mastered game usually holds a Beaten award too.
- Tiles: the game icon framed in RA's colours. RA draws mastered icons with a 2 px gold border
  (`goldimage`); we extend that with its award-indicator colours. Mastered: thick gold.
  Completed: thin gold. Beaten: thick silver. Beaten (casual): thin silver. The caption is the
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
  average completion, a 30-day points chart, and every console in the table below. Only the
  recent points need a request (`API_GetAchievementsEarnedBetween`), made when X is pressed; the
  result is kept 10 minutes and stored for offline use.
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
| Badge downloads | On-device + recent | On-device + recent · All games · None (download while browsing online) |
| "Recent" window | 30 days | 7 · 30 · 90 days |
| Hide locked descriptions | Off | Off · Story only (Progression and Win condition tags) · All |
| RAOfflineProxy | — | Read-only status, shown when the proxy is installed |
| Auto-sync on open | On | On · Off |
| Actions | — | Sync now · Full re-sync · Re-enter API key · Clear image cache (shows size) |
| About | — | Version, license (MIT), credits: PyUI (Copyright (c) 2025 Christopher Jacobs; its license requires this user-facing credit), pixelarticons (MIT), RetroAchievements as the data source |

The file also remembers `game_list_details` (the games list view) and `untested_note` (the
one-time note on an untested device).

## Controls
These follow the conventions of Spruce's own menus (see [pyui.md](pyui.md), "Buttons"): X acts
on the highlighted item, Start is free in lists, Select switches the view.

| Button | Action |
|---|---|
| D-pad | Move |
| A | Open / confirm |
| B | Back |
| Start | Sync, or cancel the running sync, on every screen except popups and the keyboard |
| Y | Options popup: filter and sort (games); view, filter and sort (a game's achievements) |
| X | Reveal a hidden (spoiler) description on the achievement card (per-item, like PyUI); "See more" on the profile |
| Select | Games: progress bars ↔ details. A game's achievements: list ↔ grid (like PyUI's game lists) |
| L1 / R1 | Page up / down (PyUI default) |
| MENU (hold) | Reserved by Spruce (game switcher) |

Screen-specific buttons are hinted in the bottom bar ("[Y] Filter", "[SELECT] Details",
"[A] Full screen"); when space runs out, later hints go first. Themes ship X, Y and START badges;
missing ones (A, Select) are generated in the style of the theme's START badge.

## Visual style (a "gaming app" feel)
- **Themed throughout**: fonts, colours, backgrounds and top bar come from the active Spruce
  theme through PyUI.
- **RA pixel art carries the screens**:
  - game icons in game lists;
  - colour badges for unlocked achievements and RA's `_lock` badges for locked ones;
  - the player's avatar on the profile row and profile screen.
- **Menu and status icons**: pixelarticons (MIT), recoloured to the theme accent and
  pre-rendered at exact 2× and 3× of their 24 px grid (48 px up to 752 px wide screens, 72 px
  above), so pixels stay sharp. Every row gets an icon; a missing image falls back to a pixel
  icon, so columns stay aligned.
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
| No Wi-Fi, no cache | Setup screen: "Connect to Wi-Fi to set up". |
| Clock not synced | Skip sync and show a hint. Cached data still works. |
| Key rejected mid-use | Stop sync and prompt to re-enter the key. Cache stays usable. |
| Rate limited / RA down | Back off. The bottom bar shows "RetroAchievements unavailable". |
| Power-off mid-sync | Resumes next run. Per-game commits mean the DB is never half-written for a game. |
| Proxy missing or unreadable | Hide the Settings status row and pending markers. |
| Theme lacks an asset we use | Fall back to our bundled icons (`cheevos/res/`) or generate it (button badges). |
| The app can't start (PyUI import, bootstrap, any crash) | `launch.sh` sees the non-zero exit, appends stderr to the app log (errors before logging starts only reach stderr), and shows "Cheevos couldn't start" with the log's path through `App/PyUI/launch.sh -msgDisplay` (PyUI's launcher sets up every platform's display). Verified on the Mini. |
| Unknown platform | `launch.sh` shows "Cheevos doesn't support this device yet" the same way. |
| Untested device | A one-time note on first start asks for a report with the log's path ([device.md](device.md)). |
