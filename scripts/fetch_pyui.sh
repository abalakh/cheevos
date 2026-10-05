#!/bin/sh
# Fetch PyUI and the default SPRUCE theme from SpruceOS into .spruceos/ (git-ignored).
#
#   scripts/fetch_pyui.sh          the commit the bridge was verified against
#                                  (pyui-tested-commit in pyproject.toml)
#   scripts/fetch_pyui.sh <ref>    any branch, tag or commit, e.g. origin/Development
#
# A sparse, blob-less clone: only App/PyUI and Themes/SPRUCE are checked out (a few MB).
# The desktop runner and the screen tests use it; CI does the same with actions/checkout.

set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/.spruceos"
URL="https://github.com/spruceUI/spruceOS.git"
PINNED="$(grep -E '^pyui-tested-commit' "$REPO/pyproject.toml" | cut -d'"' -f2)"
REF="${1:-$PINNED}"

if [ ! -d "$DEST/.git" ]; then
    git clone --quiet --filter=blob:none --no-checkout "$URL" "$DEST"
    git -C "$DEST" sparse-checkout set App/PyUI Themes/SPRUCE
else
    git -C "$DEST" fetch --quiet origin
fi
git -C "$DEST" -c advice.detachedHead=false checkout --quiet "$REF"
echo "PyUI at $(git -C "$DEST" rev-parse --short HEAD) in .spruceos/"
