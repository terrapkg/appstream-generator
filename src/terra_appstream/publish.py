"""Publish asgen's export as <repo>/latest/appstream/, which Subatomic (v0) reads.

OUTPUT_DIR is the bucket through a FUSE mount, so only plain file writes:
no symlinks, and no rename-over (it races the mount's upload and loses files).
"""

import gzip
import logging
import os
import shutil
from datetime import datetime

from terra_appstream.repos import ARCH, Repo
from terra_appstream.settings import Settings

logger = logging.getLogger(__name__)

# @2 tarballs are left out: libappstream guesses the size by substring and
# files *-64x64@2.tar.gz under 64x64/
ICON_SIZES = ["64x64", "128x128"]

EMPTY_CATALOG = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<components version="1.0" origin="{origin}"/>\n'
)


def compose_files(settings: Settings, repo: Repo) -> dict[str, str]:
    """Map compose file names to their source in asgen's export."""
    data_dir = os.path.join(settings.export_dir, "data", repo.suite, repo.section)
    files = {f"{repo.name}.xml.gz": os.path.join(data_dir, f"Components-{ARCH}.xml.gz")}
    for size in ICON_SIZES:
        files[f"{repo.name}-icons-{size}.tar.gz"] = os.path.join(
            data_dir, f"icons-{size}.tar.gz"
        )
    return files


def publish_compose(settings: Settings, repo: Repo) -> str:
    """Write OUTPUT_DIR/<repo>/<timestamp>/appstream/ and update `latest` from it."""
    log = logging.getLogger(repo.name)
    catalog = f"{repo.name}.xml.gz"
    repo_dir = os.path.join(settings.out_dir, repo.name)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")

    sources = compose_files(settings, repo)
    files = {}
    # asgen writes nothing for sections without apps (drivers, libraries)
    has_apps = os.path.isfile(sources[catalog])
    if has_apps:
        for name, src in sources.items():
            if os.path.isfile(src):
                files[name] = src
            else:
                log.warning(f"Missing {src}, leaving {name} out")

    # history only; nothing reads it
    compose = os.path.join(repo_dir, stamp, "appstream")
    os.makedirs(compose, exist_ok=True)
    for name, src in files.items():
        shutil.copyfile(src, os.path.join(compose, name))
    if not has_apps:
        log.info("No apps, publishing an empty catalog")
        origin = f"terra-{repo.suite}-{repo.section}"
        with gzip.open(os.path.join(compose, catalog), "wt", encoding="utf-8") as f:
            f.write(EMPTY_CATALOG.format(origin=origin))
        files[catalog] = None

    latest = os.path.join(repo_dir, "latest")
    if os.path.islink(latest):
        # from the old symlink layout
        os.remove(latest)
    latest_dir = os.path.join(latest, "appstream")
    os.makedirs(latest_dir, exist_ok=True)
    # catalog last, so it never references missing icons
    for name in sorted(files, key=lambda n: n == catalog):
        shutil.copyfile(os.path.join(compose, name), os.path.join(latest_dir, name))
    # drop files this compose no longer has
    for entry in os.scandir(latest_dir):
        if entry.name not in files:
            os.remove(entry.path)
    log.info(f"Published {compose}, updated {latest_dir}")

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
