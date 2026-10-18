"""Publish asgen's export in the layout Subatomic (v0) reads.

Subatomic's modifyRepoAppStream picks up, for each repo:

    $SUBATOMIC_APPSTREAM_DIR/<repo>/latest/appstream/<repo>.xml.gz
    $SUBATOMIC_APPSTREAM_DIR/<repo>/latest/appstream/<repo>-icons-64x64.tar.gz

It drops the repo's appstream entries on every publish and re-adds only the
files it finds, so `latest` must never be missing or half-written. Each run
therefore writes a fresh dated compose and swaps the `latest` symlink to it
with a rename, as the appstream-builder pipeline did.
"""

import logging
import os
import shutil
from datetime import datetime

from terra_appstream.repos import ARCH, SECTION
from terra_appstream.settings import Settings

logger = logging.getLogger(__name__)

# asgen's export dirs, which share OUTPUT_DIR with the per-repo composes
RESERVED_NAMES = {"data", "hints", "html", "media"}

# @2 tarballs are left out: libappstream guesses the size by substring and
# files *-64x64@2.tar.gz under 64x64/
ICON_SIZES = ["64x64", "128x128"]


def compose_files(settings: Settings, repo: str) -> dict[str, str]:
    """Map compose file names to their source in asgen's export."""
    data_dir = os.path.join(settings.out_dir, "data", repo, SECTION)
    files = {f"{repo}.xml.gz": os.path.join(data_dir, f"Components-{ARCH}.xml.gz")}
    for size in ICON_SIZES:
        files[f"{repo}-icons-{size}.tar.gz"] = os.path.join(
            data_dir, f"icons-{size}.tar.gz"
        )
    return files


def publish_compose(settings: Settings, repo: str) -> str:
    """Write OUTPUT_DIR/<repo>/<timestamp>/appstream/ and point `latest` at it."""
    log = logging.getLogger(repo)
    repo_dir = os.path.join(settings.out_dir, repo)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")

    files = compose_files(settings, repo)
    catalog = next(iter(files.values()))
    if not os.path.isfile(catalog):
        raise FileNotFoundError(f"asgen produced no catalog at {catalog}")

    # build under a dot-name so a half-written compose never looks valid
    staging = os.path.join(repo_dir, f".{stamp}")
    if os.path.lexists(staging):
        shutil.rmtree(staging)
    os.makedirs(os.path.join(staging, "appstream"))
    for name, src in files.items():
        if not os.path.isfile(src):
            log.warning(f"Missing {src}, leaving {name} out of the compose")
            continue
        # copy, not link: asgen rewrites its export on the next run
        shutil.copyfile(src, os.path.join(staging, "appstream", name))

    compose = os.path.join(repo_dir, stamp)
    os.rename(staging, compose)

    # atomic `ln -sfn`: rename a fresh symlink over the old one
    latest = os.path.join(repo_dir, "latest")
    tmp_link = os.path.join(repo_dir, ".latest")
    if os.path.lexists(tmp_link):
        os.remove(tmp_link)
    os.symlink(stamp, tmp_link)
    os.replace(tmp_link, latest)
    log.info(f"Published {compose}, latest -> {stamp}")

    prune_composes(repo_dir, settings.old_limit, keep=stamp)
    return compose


def prune_composes(repo_dir: str, limit: int, keep: str):
    """Keep the `limit` newest dated composes, never removing `keep`."""
    composes = sorted(
        (
            entry.name
            for entry in os.scandir(repo_dir)
            if entry.name.isdigit() and entry.is_dir(follow_symlinks=False)
        ),
        reverse=True,
    )
    for name in composes[limit:]:
        if name == keep:
            continue
        path = os.path.join(repo_dir, name)
        logger.info(
            {"msg": "Removing old compose", "operation": "cleanup", "path": path}
        )
        shutil.rmtree(path)
