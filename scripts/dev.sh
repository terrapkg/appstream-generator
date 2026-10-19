#!/bin/bash
# Run terra-appstream locally in the toolchain image against ./repos.
# Workspace and export land in ./workspace and ./export so you can poke at them.
#
#   scripts/dev.sh            # run the pipeline
#   scripts/dev.sh bash       # shell in the same environment
#   scripts/dev.sh appstream-generator -w workspace info <pkid>
#
# Set TERRA=1 to run against the live bucket instead: it is mounted read-only
#
#   TERRA=1 scripts/dev.sh
#   TERRA=1 REPOS=terra44,terra44-extras scripts/dev.sh
#
# REPOS, EXCLUDE_REPOS and OLD_LIMIT are passed through to the container.
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE=${IMAGE:-asgen-proto:base}

if ! podman image exists "$IMAGE"; then
    podman build --target base -t "$IMAGE" .
fi

[ $# -gt 0 ] || set -- uv run terra-appstream

tty=()
[ -t 0 ] && tty=(-it)

# shared label (:z) so the Caddy container can read export-terra at the same time
mounts=(-v "$PWD:/app:z")
base_dir=/app/repos
suffix=""

if [ -n "${TERRA:-}" ]; then
    # outside the repo: the :z relabel of /app would recurse into the mount
    mnt=${TERRA_MNT:-${XDG_RUNTIME_DIR:-/tmp}/terra-appstream/terra}
    mkdir -p "$mnt"
    if ! mountpoint -q "$mnt"; then
        rclone mount "${TERRA_REMOTE:-terra:repos}" "$mnt" \
            --read-only --daemon --dir-cache-time 1h
        trap 'fusermount3 -u "$mnt" 2>/dev/null || fusermount -u "$mnt"' EXIT
    fi
    # a FUSE mount can't be relabelled, so it goes in without :z
    mounts+=(-v "$mnt:/terra:ro" --security-opt label=disable)
    base_dir=/terra
    suffix=-terra
fi

podman run --rm "${tty[@]}" \
    "${mounts[@]}" \
    -v asgen-dev-uv-cache:/root/.cache/uv \
    -w /app \
    -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
    -e BASE_DIR="$base_dir" \
    -e OUTPUT_DIR="/app/export$suffix" \
    -e WORKSPACE_DIR="/app/workspace$suffix" \
    -e REPOS -e EXCLUDE_REPOS -e OLD_LIMIT \
    "$IMAGE" "$@"
