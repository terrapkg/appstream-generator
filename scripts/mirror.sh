#!/bin/bash
# Mirror a handful of packages from a Terra repo into ./repos/<repo>/ for
# local testing, then generate repodata for them.
#
#   scripts/mirror.sh [REPO] [PACKAGE...]
#
# ARCHES selects which builds to fetch (default: "x86_64 noarch").
set -euo pipefail

cd "$(dirname "$0")/.."

REPO=${1:-terra44}
shift || true
# ghostty is in the default set because asgen drops it (hardlinked icons)
if [ $# -gt 0 ]; then
    PACKAGES=("$@")
else
    PACKAGES=(ghostty mission-center komikku prismlauncher)
fi
ARCHES=${ARCHES:-x86_64 noarch}
BASE_URL=${BASE_URL:-https://repos.fyralabs.com}
IMAGE=${IMAGE:-asgen-proto:base}

dest="repos/$REPO"
mkdir -p "$dest"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

primary=$(curl -sfL "$BASE_URL/$REPO/repodata/repomd.xml" |
    grep -o 'href="[^"]*-primary\.xml[^"]*"' | cut -d'"' -f2)
curl -sfL -o "$tmp/$(basename "$primary")" "$BASE_URL/$REPO/$primary"
case "$primary" in
*.zst) zstd -dc "$tmp/$(basename "$primary")" >"$tmp/primary.xml" ;;
*.gz) gzip -dc "$tmp/$(basename "$primary")" >"$tmp/primary.xml" ;;
*) cp "$tmp/$(basename "$primary")" "$tmp/primary.xml" ;;
esac
grep -o '<location href="[^"]*"' "$tmp/primary.xml" | cut -d'"' -f2 >"$tmp/hrefs"

find_hrefs() {
    PKG="$1" ARCH="${2:-}" awk '
        BEGIN { prefix = ENVIRON["PKG"] "-"; suffix = "." ENVIRON["ARCH"] ".rpm" }
        {
            f = $0
            sub(/.*\//, "", f)
            if (substr(f, 1, length(prefix)) != prefix) next
            if (substr(f, length(prefix) + 1) !~ /^[0-9]+:/) next
            if (ENVIRON["ARCH"] != "" && substr(f, length(f) - length(suffix) + 1) != suffix) next
            print
        }' "$tmp/hrefs"
}

for pkg in "${PACKAGES[@]}"; do
    if [ -z "$(find_hrefs "$pkg")" ]; then
        echo "warning: $pkg not found in $REPO" >&2
        continue
    fi
    for arch in $ARCHES; do
        # take the newest
        href=$(find_hrefs "$pkg" "$arch" | sort -V | tail -1)
        [ -n "$href" ] || continue
        if [ -f "$dest/$(basename "$href")" ]; then
            echo "have $(basename "$href")"
        else
            echo "fetch $(basename "$href")"
            curl -sfL -o "$dest/$(basename "$href")" "$BASE_URL/$REPO/$href"
        fi
    done
done

if command -v createrepo_c >/dev/null; then
    createrepo_c -q --update "$dest"
else
    podman run --rm -v "$PWD/repos:/repos:Z" "$IMAGE" createrepo_c -q --update "/repos/$REPO"
fi
echo "repodata written to $dest/repodata"
