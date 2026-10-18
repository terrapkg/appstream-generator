#!/bin/bash
# Run terra-appstream locally in the toolchain image against ./repos.
# Workspace and export land in ./workspace and ./export so you can poke at them.
#
#   scripts/dev.sh            # run the pipeline
#   scripts/dev.sh bash       # shell in the same environment
#   scripts/dev.sh appstream-generator -w workspace info <pkid>
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE=${IMAGE:-asgen-proto:base}

if ! podman image exists "$IMAGE"; then
    podman build --target base -t "$IMAGE" .
fi

[ $# -gt 0 ] || set -- uv run terra-appstream

tty=()
[ -t 0 ] && tty=(-it)

exec podman run --rm "${tty[@]}" \
    -v "$PWD:/app:Z" \
    -v asgen-dev-uv-cache:/root/.cache/uv \
    -w /app \
    -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
    -e BASE_DIR=/app/repos \
    -e OUTPUT_DIR=/app/export \
    -e WORKSPACE_DIR=/app/workspace \
    "$IMAGE" "$@"
