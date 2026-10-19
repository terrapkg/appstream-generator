#!/bin/bash
# Run terra-appstream in the toolchain image against ./repos, writing
# ./workspace and ./output. TERRA=1 uses the live bucket (rclone remote
# terra:repos, mounted read-only) with ./workspace-terra and ./output-terra.
#
#   scripts/dev.sh [command...]
#   TERRA=1 REPOS=terra44,terra44-extras scripts/dev.sh
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE=${IMAGE:-asgen-proto:base}

if ! podman image exists "$IMAGE"; then
    podman build --target base -t "$IMAGE" .
fi

[ $# -gt 0 ] || set -- uv run terra-appstream

tty=()
[ -t 0 ] && tty=(-it)

# :z (shared) so the Caddy container can read it too
mounts=(-v "$PWD:/app:z")
base_dir=/app/repos
suffix=""

if [ -n "${TERRA:-}" ]; then
    # outside the repo, or the :z relabel would recurse into it
    mnt=${TERRA_MNT:-${XDG_RUNTIME_DIR:-/tmp}/terra-appstream/terra}
    # left behind if rclone was killed (e.g. the systemd unit was stopped)
    if ! stat "$mnt" >/dev/null 2>&1 && grep -q " $mnt fuse" /proc/mounts; then
        fusermount3 -uz "$mnt"
    fi
    mkdir -p "$mnt"
    if ! mountpoint -q "$mnt"; then
        rclone mount "${TERRA_REMOTE:-terra:repos}" "$mnt" \
            --read-only --daemon --dir-cache-time 10s
        trap 'fusermount3 -uz "$mnt"' EXIT
        trap 'exit 143' TERM
        trap 'exit 130' INT
    fi
    # FUSE mounts can't be relabelled
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
    -e OUTPUT_DIR="/app/output$suffix" \
    -e WORKSPACE_DIR="/app/workspace$suffix" \
    -e REPOS -e EXCLUDE_REPOS -e OLD_LIMIT \
    "$IMAGE" "$@"
