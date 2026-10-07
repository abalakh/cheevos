# Code: architecture and conventions

How the code is laid out and the rules every change follows. `make check` enforces most of them;
`pyproject.toml` is the source of truth for tool settings. Commit and pull request style is in
[CONTRIBUTING.md](../CONTRIBUTING.md).

SpruceOS has no formal Python conventions (no linters, formatter config or contribution guide;
PyUI has hints on about 6% of its functions and modules up to 1.8k lines). Cheevos adopts its
consistent habits (snake_case and PascalCase, shell scripts that source `helperFunctions.sh`,
logs in `Saves/spruce/<app>-$PLATFORM.log`, `Area: imperative summary` commit subjects) and a
stricter modern baseline for the rest. Spruce enforces nothing, so stricter code is still welcome
in an upstream PR.

## Layers

```
┌─────────────────────────────────────────────────────────────┐
│ ui/        screens + view models  ──►  ui/pyui/ (bridge)  ──►  PyUI (runtime import)
├─────────────────────────────────────────────────────────────┤
│ core/      models · storage · ra_client · sync · settings ·
│            credentials · screenshots · proxy · local_games
├─────────────────────────────────────────────────────────────┤
│ platform/  paths · env detection · device bootstrap · desktop shim (dev only)
└─────────────────────────────────────────────────────────────┘
```

- `core` is pure Python (stdlib only). It never imports `ui`, PyUI or SDL. It holds almost all
  the logic and is fully unit-testable on a Mac.
- `ui/pyui/` is the **only** package allowed to import PyUI. It gives the rest of the code a
  small typed API, so when PyUI changes, the breakage stays in one place ([pyui.md](pyui.md)).
- `platform` resolves paths from a single root, `CHEEVOS_SDCARD_ROOT`, defaulting to
  `/mnt/SDCARD`. It also detects the device and initialises PyUI (or the desktop shim).

| Package | May import | Must not import |
|---|---|---|
| `cheevos.core` | stdlib, other `cheevos.core`, `cheevos.platform.paths` (pure path resolution) | `cheevos.ui`, `cheevos.platform.desktop`, PyUI, `sdl2` |
| `cheevos.ui.screens` | `cheevos.core`, `cheevos.ui.pyui` (bridge), `cheevos.ui.strings` | PyUI, `sdl2` |
| `cheevos.ui.pyui` | PyUI, `sdl2`, `cheevos.core.models` | `cheevos.ui.screens` |
| `cheevos.platform` | stdlib, `cheevos.core` | screens |
| `cheevos.platform.desktop` | PyUI, `sdl2` | — (dev only, excluded from the device package) |

## Package layout

```
src/cheevos/
  __main__.py            device entry point: python -m cheevos
  app.py                 composition root: credentials, caches, sync, media, then home
  core/
    models.py            dataclasses: UserProfile, GameProgress, Achievement, Award, Unlock, ...
    errors.py            CheevosError and its subclasses
    storage/             db.py (open/recreate), schema.py (DDL, version, row mapping),
                         data_cache.py, media_cache.py
    ra_client/           transport.py (HTTPS with HTTP fallback, fixtures), client.py, parse.py,
                         redact.py (key redaction in logs)
    sync/                engine.py, planner.py (what to fetch), progress.py, lazy_media.py,
                         session.py, __main__.py (sync without UI)
    stats.py             profile statistics, after RA's own rules
    settings.py          settings.json load/save with defaults and validation
    credentials.py       username from Spruce or RetroArch, apikey.txt
    screenshots.py       *-cheevo-<id>.png index
    proxy.py             RAOfflineProxy reader (read-only files)
    local_games.py       on-device matching sources
    net.py               connectivity check through the shared transport
    clock.py             shared RA Date + monotonic app clock (system clock unchanged)
  ui/
    pyui/                bridge: bootstrap, views (lists, grids, popups), primitives (drawing,
                         input), text (fitting, glyph fallbacks), status_bar, bar_layout, glyphs,
                         generated (PNG swatches, dots), row_bars, bar_colors, grid_frames,
                         texture_budget (bounded PyUI texture caches), title_bar (a game's
                         top-bar title and award dot)
    screens/             home, profile, page (scrolling pages), games, game_detail, achievement,
                         lists (recent unlocks), awards, settings, setup, status (bottom-bar sync
                         status), rows, common
    context.py           what screens share (AppContext)
    media.py             image resolver with pixel-icon fallbacks
    strings.py           every user-facing string (ready for PyUI Language later)
  platform/
    paths.py             every path, from CHEEVOS_SDCARD_ROOT (default /mnt/SDCARD)
    desktop/             dev only: device shim, keyboard/script controller, headless capture,
                         fixture/live environments, drills
  res/icons/             pixelarticons rendered at 24, 48 and 72 px
app/                     packaging: config.json, launch.sh, cheevos.png
assets/                  icon sources (SVG)
tests/                   unit and screen tests, fixtures/
scripts/                 check_conventions, record_fixtures, fetch_dev_media, fetch_pyui.sh,
                         build_package, release_notes, render_icons, make_synthetic_cache,
                         doc_screens, device.sh
docs/                    the user guide, published as the GitHub wiki (images/ from doc_screens)
.agents/                 docs for coding agents, by area (AGENTS.md is the entry point)
README.md, CONTRIBUTING.md, TESTING.md
```

On the device, everything is assembled into `/mnt/SDCARD/App/Cheevos/` ([device.md](device.md)).

## Python version and dependencies
- **Target: Python 3.10.** The device runs CPython 3.10.18. Develop locally on 3.10 too
  (`uv python install 3.10`; `.python-version` pins it).
- **Don't use 3.11+ features**:
  - modules and builtins: `tomllib`, `typing.Self`, `ExceptionGroup` / `except*`,
    `asyncio.TaskGroup`, `enum.StrEnum`;
  - typing: `typing.override`, PEP 695 generics and `type X = ...` aliases;
  - regex: `re` atomic groups.
  - ruff's `target-version = "py310"` and ty's `python-version = "3.10"` catch most of these.
- **Runtime: standard library only.** Anything else would have to be vendored as pure Python and
  needs a written justification in the PR. PySDL2 reaches us only through PyUI.
- **Dev dependencies** are managed by `uv`, in the `dev` group: ruff, ty, pytest, pytest-cov,
  pysdl2 0.9.17 and pysdl2-dll (for the desktop runner).

## Tooling

| Tool | Purpose | Gate |
|---|---|---|
| `ruff format` | Formatting | CI fails on diff |
| `ruff check` | Lint (a wide rule set, Google docstrings, complexity limits) | CI fails on any error |
| `ty check` | Type checking | CI fails on any error |
| `pytest` | Tests | CI fails; core coverage ≥ 85% |
| `scripts/check_conventions.py` | Rules ruff can't express (below) | CI fails |
| `shellcheck` | `app/launch.sh`, `scripts/*.sh` (POSIX sh: devices run busybox ash) | CI fails |

`make check` runs all of these locally; `make fmt` formats and auto-fixes. Per-file ignores worth
knowing about:
- `PLC0415` (import outside top level) is allowed in `cheevos/ui/pyui/**` and the desktop
  `__main__`, because PyUI is importable only after `add_pyui_to_path()`.
- `T20` (print) is allowed in `scripts/`.
- Tests skip docstrings and annotations, and allow `assert`, magic numbers, subprocesses, many
  arguments and boolean flags.

`scripts/check_conventions.py` is a small AST-based checker:
1. **Module size**: soft cap of **500 lines**. Over 500 fails unless the module's first lines
   contain `# conventions: allow-long-module — <reason>`. **800** is a hard cap, with no
   exceptions. Split modules rather than adding allow markers.
2. **Docstrings on private members too.** pydocstyle skips `_private` functions, methods and
   classes (nested ones included); this check covers them. Tests are exempt.
3. **Layering**: checks `import` and `from … import` of PyUI top-level modules (`display`,
   `views`, `themes`, `controller`, `devices`, `menus`, `utils`, `apps`, `games`, `audio`) and of
   `cheevos.ui` from inside `cheevos.core`.

Tooling gotchas:
- **Formatter vs. regex edits:** `ruff format` re-wraps long calls, so a regex edit of
  `logger.debug(` can silently miss. Re-grep after scripted edits.
- **Test lambdas:** ruff E731 flags lambdas assigned to names in tests; use small `def`s.

## Style
- **Line length 100**, formatted by `ruff format` (double quotes, trailing commas).
- **Docstrings: Google style, on every module, class, function and method**, public or private.
  Tests are exempt. Rules:
  - The summary line is imperative and ends with a period.
  - Include `Args:`, `Returns:` and `Raises:` when they aren't obvious from the signature.
  - Document `__init__` parameters in the class docstring.

  ```python
  def plan_detail_fetches(games: list[Game], *, full: bool, budget: int) -> list[int]:
      """Pick the game IDs whose achievement details must be re-fetched.

      Args:
          games: Games from the latest completion-progress pass, with stored fingerprints.
          full: Re-fetch every game regardless of fingerprints.
          budget: Maximum number of "stale but unchanged" games to refresh this run.

      Returns:
          Game IDs in fetch order: never-fetched first, then changed, then stale.
      """
  ```
- **Comments citing the design** name the `.agents/` file, e.g. `(.agents/integration.md)`.
- **Types**: annotate every signature (ruff `ANN`).
  - Prefer `dataclass(frozen=True, slots=True)` for models. `slots=True` works on 3.10.
  - Use `X | None` syntax.
  - Every `# type: ignore[...]` needs a reason comment.
  - PyUI is untyped; ty treats it as `Any` and the bridge keeps that inside ([pyui.md](pyui.md)).
- **Size**:
  - modules: soft cap 500 lines, hard cap 800;
  - functions: 50 statements, complexity 10, 6 arguments, 12 branches, 6 returns. Use
    keyword-only arguments (`*`) for flags (ruff `FBT`).
- **Naming**:
  - `snake_case` for functions, variables and modules; `PascalCase` for classes;
    `UPPER_SNAKE` for constants.
  - Avoid generic module names that collide with PyUI's top-level packages (`utils`, `display`,
    `views`, …) in places where both could be imported.
- **No `print`** (ruff `T20`). Use `logging`: one `logger = logging.getLogger(__name__)` per
  module, with %-style arguments (ruff `G`), never f-strings in log calls.
- **Secrets**: never log or format the API key or full API URLs
  ([retroachievements.md](retroachievements.md), "Secrets").
- **Time**:
  - Store UTC epoch seconds in the DB.
  - Use `core.clock.network_clock.now` for app dates, cache freshness and retry deadlines:
    it follows RA's Date after the first response, even when the device clock is incorrect.
  - Use timezone-aware `datetime`s (ruff `DTZ`).
  - Convert to local time only for display, via `zoneinfo` and the TZ from
    `Saves/spruce/shared-system.json`.
  - Use `time.monotonic()` for durations, as PyUI does: the device clock can jump at NTP sync.
- **Errors**:
  - Every exception we raise derives from `CheevosError` (`core/errors.py`): `AuthError`,
    `NetworkError`, `RateLimitedError`, `ApiPayloadError`, `ConfigError`.
  - Never use a bare `except` (ruff `BLE`).
  - The top-level loop catches, logs and shows a friendly message rather than dumping a
    traceback on screen.
- **Paths**:
  - Use `pathlib` (ruff `PTH`).
  - Every SD-card path comes from `cheevos.platform.paths`, rooted at `CHEEVOS_SDCARD_ROOT`
    (default `/mnt/SDCARD`).
  - Never hard-code `/mnt/SDCARD` anywhere else.
- **User-facing strings** live in `cheevos/ui/strings.py`, keyed, so they can map to PyUI's
  `Language.label()` later.

## Tests
- **Layout**: `tests/unit/` mirrors `src/cheevos/core/`, `tests/screens/` holds headless render
  tests, and `tests/fixtures/` holds recorded RA JSON (`ra/`, and `ra-empty/` for a new account).
- **No network in tests.** An autouse fixture makes `socket.socket` raise. HTTP goes through
  `FixtureTransport`.
- **Fixtures**: recorded with `scripts/record_fixtures.py`, which strips `y=` before saving. A
  public repo needs a public RA account for recordings, or scrubbed usernames.
- **Determinism**: inject clocks (`now: Callable[[], float]`) and sleep functions. No real
  `time.sleep` in tests.
- **Sync engine tests** cover interrupted runs resuming, fingerprint planning, 429 back-off, an
  expired key mid-sync, and badge-scope selection.
- **Screen tests** render the app headless at 640×480, 752×560 and 1280×720 and walk through
  the drills; `make screens` writes the standard walk-through to `build/screens/`. Review the
  images by eye. They are not pixel-golden gated, because font rendering differs between SDL
  builds. Fixture mode must not depend on git-ignored `dev/` data to navigate: CI lacks it, and
  a press that does nothing there shifts every later step.

How to run all of this: [TESTING.md](../TESTING.md).

## Shell (`launch.sh`, scripts)
- POSIX `sh`, compatible with busybox ash, checked with `shellcheck -s sh`.
- Start by sourcing `/mnt/SDCARD/spruce/scripts/helperFunctions.sh` and `appEnv.sh`. Read only
  `SPRUCE_*` / `PLATFORM` variables from them.
- Quote every expansion. No bashisms.
- `.spruceos/`, `build/`, `dist/` and `dev/` are git-ignored.
