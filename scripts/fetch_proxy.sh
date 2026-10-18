#!/bin/sh
# Fetch the RAOfflineProxy bundle SpruceOS ships into .spruceos-proxy/ (git-ignored), for
# scripts/check_proxy_compat.py.
#
#   scripts/fetch_proxy.sh          the commit ROM identification was verified against
#                                   (proxy-tested-commit in pyproject.toml)
#   scripts/fetch_proxy.sh <ref>    any branch, tag or commit, e.g. origin/Development
#
# A sparse, blob-less clone: only App/RAOfflineProxy is checked out. CI does the same with
# actions/checkout.

set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/.spruceos-proxy"
URL="https://github.com/spruceUI/spruceOS.git"
PINNED="$(grep -E '^proxy-tested-commit' "$REPO/pyproject.toml" | cut -d'"' -f2)"
REF="${1:-$PINNED}"

if [ ! -d "$DEST/.git" ]; then
    git clone --quiet --filter=blob:none --no-checkout "$URL" "$DEST"
    git -C "$DEST" sparse-checkout set App/RAOfflineProxy
else
    git -C "$DEST" fetch --quiet origin
fi
git -C "$DEST" -c advice.detachedHead=false checkout --quiet "$REF"
echo "RAOfflineProxy from SpruceOS $(git -C "$DEST" rev-parse --short HEAD) in .spruceos-proxy/"
