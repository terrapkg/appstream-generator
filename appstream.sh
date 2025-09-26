#!/bin/bash

# don't actually use this script in prod, this is more of a dev scratchpad
# for appstream scripts
#
. .env

BASENAME="terra42/latest"

OUTPUT="${OUTPUT_DIR}/${BASENAME}"

appstream-builder \
    --add-cache-id \
    --output-dir="$OUTPUT/appstream" \
    --origin="Terra" \
    --temp-dir=tmp \
    --icons-dir="$OUTPUT/icons" \
    --cache-dir="$OUTPUT/cache" \
    --basename=terra-42 \
    --log-dir="$OUTPUT/logs" \
    --include-failed \
    --packages-dir="$T42_DIR" \
    --veto-ignore=missing-parents
