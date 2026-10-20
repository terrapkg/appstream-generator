import logging
import os
from fnmatch import fnmatchcase
import shutil
from collections.abc import Iterator
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Label only: rpmmd ignores arch, and Terra repos mix arches.
ARCH = "x86_64"
# asgen looks for icon themes only in packages, so Fedora's theme RPMs are
# provided as a base suite of every Terra suite
ICON_THEMES_SUITE = "icon-themes"


class Repo(NamedTuple):
    """A repo as an asgen suite/section: terra44-extras is terra44/extras."""

    name: str
    suite: str
    section: str

    @classmethod
    def from_name(cls, name: str) -> "Repo":
        suite, _, section = name.partition("-")
        return cls(name, suite, section or "main")

    def logger(self, name: str) -> logging.LoggerAdapter:
        """A logger that adds repo, suite and section to every line."""
        context = {"repo": self.name, "suite": self.suite, "section": self.section}
        return logging.LoggerAdapter(logging.getLogger(name), context, merge_extra=True)


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


def build_archive_tree(
    base_dir: str, workspace_dir: str, repos: list[Repo], icon_themes_dir: str | None = None
) -> str:
    """Symlink <workspace>/archive/<suite>/<section>/<arch>/os -> <base_dir>/<repo>.

    asgen's rpmmd backend hardcodes that layout; Terra repos are flat.
    Returns the root, for ArchiveRoot.
    """
    archive_root = os.path.join(workspace_dir, "archive")
    # symlinks only; rmtree doesn't follow them
    if os.path.lexists(archive_root):
        logger.debug(f"Removing old archive tree {archive_root}")
        shutil.rmtree(archive_root)

    for repo in repos:
        logger.debug(f"Creating archive tree for {repo.name}")
        arch_dir = os.path.join(archive_root, repo.suite, repo.section, ARCH)
        os.makedirs(arch_dir)
        logger.debug(f"Symlinking {os.path.join(base_dir, repo.name)} -> {os.path.join(arch_dir, 'os')}")
        os.symlink(os.path.join(base_dir, repo.name), os.path.join(arch_dir, "os"))

    if icon_themes_dir:
        # asgen reads a base suite under the section it is processing (and main),
        # so the theme repo is linked in as every section in use
        for section in sorted({repo.section for repo in repos} | {"main"}):
            arch_dir = os.path.join(archive_root, ICON_THEMES_SUITE, section, ARCH)
            os.makedirs(arch_dir)
            os.symlink(os.path.abspath(icon_themes_dir), os.path.join(arch_dir, "os"))

    return archive_root
