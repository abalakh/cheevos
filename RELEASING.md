# Releasing Cheevos

CI, device packages, GitHub releases, SpruceOS pull requests and wiki publication.
For local setup and validation, see [TESTING.md](TESTING.md).

## CI

- **CI** (`.github/workflows/ci.yml`): on pull request creation and updates, pushes to `master`
  and `v*` tags, checks out PyUI at `pyui-tested-commit`, then runs lint, type check and tests.
  Feature branch pushes don't run CI separately; their pull requests test the merge result.
  When a test fails, it uploads the screen tests' captures (`screen-test-captures`).
- **PyUI drift** (`.github/workflows/pyui-drift.yml`): weekly, the same tests and `make screens`
  against SpruceOS's latest `Development` branch, as an early warning when PyUI changes. It
  uploads the screens either way. After re-verifying against a newer SpruceOS, bump
  `pyui-tested-commit`.
- **SpruceOS PR** (the `spruceos` job in `ci.yml`): after a stable release and wiki publication
  succeed, mirrors the published device ZIP into SpruceOS's `App/Cheevos/` and opens an upstream
  PR. See the one-time setup below.
- CI has no `dev/media-host`, so badges, icons and avatars in CI screens are placeholders.

## Releases

`make package` builds `dist/App/Cheevos/` and `dist/Cheevos-<version>.zip`, which contains a
`Cheevos` folder to copy into `App` on the SD card. To publish a release:

1. Set the version in `pyproject.toml` and `src/cheevos/__init__.py` (a test checks that they
   match). Use PEP 440: `0.1.0b1` for a pre-release, `0.1.0` for a release. Run `uv lock`, since
   CI installs with `--locked`, then `make check`.
2. Commit, tag `v<version>` and push both: `git tag v0.1.0b1 && git push origin master v0.1.0b1`.
3. Once the checks pass, CI's `release` job publishes a GitHub release with the zip. Versions
   with `a`, `b`, `rc` or `dev` in them are marked as pre-releases. A tag that doesn't match
   the version fails the job. After a stable release, the `wiki` job publishes that release's
   user guide; pre-releases leave the wiki as it is. Pre-release notes cover changes since the
   previous version tag; stable-release notes cover changes since the previous stable tag,
   including all intervening pre-releases. If there is no tag of the relevant kind yet, notes
   cover the whole history.
   The description links each merged PR title once and links direct commit titles.
4. After the release and wiki jobs succeed, the `spruceos` job prepares a PR against
   `spruceUI/spruceOS`'s `Development` branch using the exact published ZIP. Alpha, beta, RC and
   dev releases do not run this job. SpruceOS maintainers review and merge the PR.

GitHub adds its own "Source code" archives to every release; they can't be removed. Testers
need only the `Cheevos-<version>.zip`.

## Mirroring releases to SpruceOS

The `spruceos` job replaces only `App/Cheevos/` in an upstream checkout, removing files that
are no longer in the device package. It preserves the launcher's executable bit and includes
Cheevos's MIT license. Source docs, tests and the desktop runner are not part of the package.
The PR links the Cheevos release and records the checks that passed.

**One-time setup** in the Cheevos repository:

1. Fork [spruceUI/spruceOS](https://github.com/spruceUI/spruceOS) into the account that will
   open the PRs. The default is `abalakh/spruceOS`.
   To use a different fork, set the Actions variable `SPRUCEOS_FORK` to
   its full `owner/repo` name. The job checks that it belongs to SpruceOS's fork network.
2. Create a **classic personal access token** for that account with `public_repo` and
   `workflow` scopes, and store it as the Actions secret **`SPRUCEOS_PR_TOKEN`**. The account
   needs write access to the fork and permission to open public PRs; it does not need write
   access to SpruceOS. `workflow` allows pushing the new branch when its upstream history
   contains workflow changes. The built-in `GITHUB_TOKEN` only covers Cheevos, and a single
   fine-grained token cannot cover this fork and the upstream repository under different
   owners. See [GitHub's token limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens-limitations)
   and the [PR action's fork setup](https://github.com/peter-evans/create-pull-request/blob/main/docs/concepts-guidelines.md#push-pull-request-branches-to-a-fork).
3. The target branch defaults to `Development`. Set the Actions variable
   `SPRUCEOS_BASE_BRANCH` only if the SpruceOS maintainers request another target.

Each stable tag has its own branch, `cheevos/v<version>`, in the fork. Rerunning a failed
`spruceos` job reuses that release's PR instead of duplicating it, and does not republish the
release or wiki. If the app already matches the target branch, there is no new PR. If several
stable releases are waiting for review, each has a separate PR. The job writes the upstream
PR link to its Actions summary. Missing credentials or a missing fork fail this job with the
published release left available.

## Publishing the wiki

The [user guide](docs/Home.md) in `docs/` works when browsing the repository on GitHub or
locally. Keep links between guide pages relative, with the `.md` extension (for example,
`[Installation](Installation.md)`).

The GitHub wiki is a separate repository (`<repo>.wiki.git`). To prepare its pages:

1. Regenerate the screenshots with `make doc-screens` when screens have changed.
2. Run `make wiki`. This copies the pages and `images/` into `build/wiki/`, converting guide
   page links to the wiki's extensionless targets. Edit the sources in `docs/`, not the export.
3. Copy the contents of `build/wiki/` into a clone of the wiki repository, then commit and push
   there.

CI does this automatically after each successful stable release, using the tagged commit's
docs and checked-in screenshots. It doesn't regenerate screenshots: keep running
`make doc-screens` when changing the UI and include the images in the release commit.

**One-time setup:** enable **Wikis** in the repository settings and create an initial page
in GitHub's Wiki tab. This creates the wiki Git repository so Actions can check it out.
The job uses the built-in `GITHUB_TOKEN` with `contents: write`; no extra secret is needed.

The published wiki mirrors the guide: deleted pages and images are removed too. Make changes
in `docs/`; edits made directly in the wiki are replaced on the next stable release. Unchanged
docs produce no wiki commit. If publishing fails after the release succeeds, rerun just the
failed `wiki` job from Actions.
