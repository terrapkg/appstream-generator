import logging
import os
import sys

from logfmter import Logfmter

from terra_appstream import asgen, publish
from terra_appstream.repos import build_archive_tree, scan_repos
from terra_appstream.settings import Settings

logger = logging.getLogger("terra-appstream")

# What this does is:
# - Scan the base directory for flat RPM repos
# - Build a shadow tree in the workspace with the <suite>/<section>/<arch>/os
#   layout asgen's rpmmd backend expects, pointing at the repos
# - Generate asgen-config.json with one suite per repo
# - Run asgen per repo, exporting to OUTPUT_DIR/{data,hints,html,media}/<repo>/main/
# - Copy each repo's catalog and icons into OUTPUT_DIR/<repo>/<date>/appstream/
#   and swap OUTPUT_DIR/<repo>/latest to it, which is what Subatomic reads
# - Run asgen cleanup to drop superseded packages


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(
        Logfmter(keys=["level", "name"], mapping={"level": "levelname"})
    )
    logging.basicConfig(handlers=[handler], level=logging.DEBUG)


def main():
    setup_logging()
    settings = Settings.from_env()

    repos = list(
        scan_repos(
            settings.base_dir,
            exclude_paths=(settings.out_dir, settings.workspace_dir),
            include=settings.repos,
            exclude=settings.exclude_repos,
        )
    )
    if not repos:
        logger.error(f"No repos found in {settings.base_dir}")
        sys.exit(1)
    if clashes := sorted(publish.RESERVED_NAMES.intersection(repos)):
        logger.error(f"Repo names clash with asgen's export dirs: {clashes}")
        sys.exit(1)
    logger.info({"msg": "Found repos", "repo_count": len(repos), "repos": repos})

    os.makedirs(settings.workspace_dir, exist_ok=True)
    os.makedirs(settings.out_dir, exist_ok=True)
    archive_root = build_archive_tree(
        settings.base_dir, settings.workspace_dir, repos
    )
    asgen.write_config(settings, repos, archive_root)

    # asgen parallelises internally, so repos run one at a time
    failed = []
    for repo in repos:
        if asgen.run(settings, repo, "run", repo) != 0:
            # keep serving the previous compose
            failed.append(repo)
            continue
        try:
            publish.publish_compose(settings, repo)
        except OSError as e:
            logging.getLogger(repo).error(f"Failed to publish compose: {e}")
            failed.append(repo)

    if asgen.run(settings, "cleanup", "cleanup") != 0:
        failed.append("cleanup")

    if failed:
        logger.error({"msg": "Some steps failed", "failed": failed})
        sys.exit(1)
