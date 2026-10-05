# Cheevos — Roadmap

What's left to do. How the app works is in the other files here (index in
[AGENTS.md](../AGENTS.md)), what it does for players in the wiki pages in [docs/](../docs/Home.md),
tools in [TESTING.md](../TESTING.md).

## Next
1. **Unlock screenshots, end to end, on a device:** earn an achievement with RetroArch's
   Automatic Screenshot on, then open Cheevos. Only that game should be re-fetched, and the
   screenshot should appear on the achievement.
2. **The awards wall with real awards on a device.** So far it has been checked with the
   `showcase` and `awards` drills only.
3. **Release (v1):**
   - [ ] Publish the wiki: copy `docs/` into the `<repo>.wiki.git` repository.
   - [ ] Fixtures: `tests/fixtures/ra/` holds a real account's recorded responses. Re-record
         them with a public account, or scrub the username, before the repo goes public.
   - [ ] `make package` → `Cheevos-<version>.zip` that extracts to the SD card root, and a CI
         release workflow triggered by tags.
   - [ ] Testing on other devices (A30, Flip, Brick, Smart Pro, RG XX) at their resolutions.
         Cheevos shows up on every device; testers just install the release. Add each device
         that works to `TESTED_DEVICES` in `src/cheevos/app.py`, which drops its "untested
         device" note. Fix `app/launch.sh` for any that don't.
   - [ ] Talk to the Spruce maintainers before submitting: Game Nursery packaging, or an
         upstream PR. Ask whether they'd want RetroArch's Automatic Screenshot exposed in
         Spruce's RA settings. Send the PyUI author a courtesy notice, as its license asks.

## Ideas
- Show the list-building progress in the bottom bar instead of a "Loading…" frame for slow
  lists.
- Remove stale `_lock` badge blobs after an unlock (harmless today).
- Read the proxy's `achievementsets:` cache as a fallback for pending-award titles.
- Settings has "Sync now" next to Start; drop it if it proves redundant.
- A progress bar in a game's header (hardcore/casual completion).
- Match on-device games beyond what Spruce identified: hash a chosen system on demand with the
  proxy's `libraproxy_rchash.so` (rcheevos `rc_hash` through ctypes), or match by title and
  console.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| PyUI internals change and break the bridge | High (it changes weekly) | One bridge package; `pyui-tested-commit`; weekly drift CI; the desktop shim stubs PyUI's abstract methods automatically |
| RA rate limits during a big first sync | Medium | Serial API calls ≥ 300 ms apart, `Retry-After`, resumable per-game commits |
| FAT32 + SQLite corruption on power loss | Low | `journal_mode=DELETE`, short transactions; the caches are rebuildable ("Full re-sync") |
| RAOfflineProxy changes its storage (alpha) | Medium | Read-only file access with schema checks; the feature hides itself on mismatch |
| Unlock screenshots off for most players | High | The wiki explains how to turn them on; ask the maintainers about a Spruce setting |
| Untested devices behave differently | Medium | A one-time note there asks for reports with the log; if Cheevos can't start, `launch.sh` says so on screen instead of silently returning to the menu |

## Open questions
- When to contact the Spruce maintainers: before the first public release, to agree on the
  packaging (Game Nursery or upstream), or with it.
