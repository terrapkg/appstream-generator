import logging
import os
from fnmatch import fnmatchcase
import shutil
from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Labels only: rpmmd ignores arch, and Terra repos mix arches.
SECTION = "main"
ARCH = "x86_64"


def scan_repos(
    base_dir: str,
    exclude_paths: tuple[str, ...] = (),
    include: tuple[str, ...] = ("*",),
    exclude: tuple[str, ...] = (),
) -> Iterator[str]:
    """Yield names of repos under base_dir, filtered by include/exclude globs."""
    for entry in sorted(os.scandir(base_dir), key=lambda e: e.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.path in exclude_paths:
            continue
        if not any(fnmatchcase(entry.name, p) for p in include):
            continue
        if any(fnmatchcase(entry.name, p) for p in exclude):
            logger.debug(f"Skipping {entry.path}, excluded")
            continue
        if not os.path.isfile(os.path.join(entry.path, "repodata", "repomd.xml")):
            logger.debug(f"Skipping {entry.path}, no repodata/repomd.xml")
            continue
        yield entry.name


def build_archive_tree(base_dir: str, workspace_dir: str, repos: list[str]) -> str:
    """Symlink <workspace>/archive/<repo>/main/<arch>/os -> <base_dir>/<repo>.

    asgen's rpmmd backend hardcodes that layout; Terra repos are flat.
    Returns the root, for ArchiveRoot.
    """
    archive_root = os.path.join(workspace_dir, "archive")
    # symlinks only; rmtree doesn't follow them
    if os.path.lexists(archive_root):
        logger.debug(f"Removing old archive tree {archive_root}")
        shutil.rmtree(archive_root)

    for repo in repos:
        logger.debug(f"Creating archive tree for {repo}")
        arch_dir = os.path.join(archive_root, repo, SECTION, ARCH)
        os.makedirs(arch_dir)
        logger.debug(f"Symlinking {os.path.join(base_dir, repo)} -> {os.path.join(arch_dir, 'os')}")
        os.symlink(os.path.join(base_dir, repo), os.path.join(arch_dir, "os"))

    return archive_root
