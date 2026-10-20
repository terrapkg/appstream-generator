import logging
import os
import sys
from collections import Counter

from logfmter import Logfmter

from terra_appstream import asgen, publish
from terra_appstream.repos import Repo, build_archive_tree, scan_repos
from terra_appstream.settings import Settings

logger = logging.getLogger("terra-appstream")

# Scan BASE_DIR for repos, run asgen on each (as <suite>/<section>), publish the
# results to OUTPUT_DIR, then let asgen clean up superseded packages.


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(
        Logfmter(keys=["level", "name"], mapping={"level": "levelname"})
    )
    logging.basicConfig(handlers=[handler], level=logging.DEBUG)


def main():
    setup_logging()
    settings = Settings.from_env()

    names = scan_repos(
        settings.base_dir,
        exclude_paths=(settings.out_dir, settings.workspace_dir),
        include=settings.repos,
        exclude=settings.exclude_repos,
    )
    repos = [Repo.from_name(name) for name in names]
    if not repos:
        logger.error(f"No repos found in {settings.base_dir}")
        sys.exit(1)
    # e.g. terra44-main and terra44 would both be terra44/main
    counts = Counter((r.suite, r.section) for r in repos)
    clashes = [key for key, n in counts.items() if n > 1]
    if clashes:
        logger.error(f"Repos map to the same suite/section: {clashes}")
        sys.exit(1)
    logger.info(
        {"msg": "Found repos", "repo_count": len(repos), "repos": [r.name for r in repos]}
    )

    os.makedirs(settings.workspace_dir, exist_ok=True)
    os.makedirs(settings.out_dir, exist_ok=True)
    archive_root = build_archive_tree(
        settings.base_dir, settings.workspace_dir, repos, settings.icon_themes_dir
    )
    asgen.write_config(settings, repos, archive_root)

    # asgen parallelises internally, so repos run one at a time
    failed = []
    for repo in repos:
        if asgen.run(settings, repo.logger("asgen"), "run", repo.suite, repo.section) != 0:
            failed.append(repo.name)
            continue
        try:
            publish.publish_compose(settings, repo)
        except OSError as e:
            repo.logger(logger.name).error(f"Failed to publish compose: {e}")
            failed.append(repo.name)

    if asgen.run(settings, logging.getLogger("asgen"), "cleanup") != 0:
        failed.append("cleanup")

    if failed:
        logger.error({"msg": "Some steps failed", "failed": failed})
        sys.exit(1)
