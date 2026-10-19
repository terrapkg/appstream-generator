import json
import logging
import os
import re
import subprocess
from importlib.resources import files

from terra_appstream.repos import ARCH, Repo
from terra_appstream.settings import Settings

logger = logging.getLogger(__name__)

# asgen (quill) lines look like: 2026-10-18 10:07:47.784 I engine: message
LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ (?P<level>\w+) (?P<name>[^:\s]+): (?P<msg>.*)$"
)
LEVELS = {
    "T1": logging.DEBUG,
    "T2": logging.DEBUG,
    "T3": logging.DEBUG,
    "D": logging.DEBUG,
    "I": logging.INFO,
    "N": logging.INFO,
    "W": logging.WARNING,
    "E": logging.ERROR,
    "C": logging.CRITICAL,
}


def write_config(settings: Settings, repos: list[Repo], archive_root: str) -> str:
    """Fill in the asgen-config.json template and write it to the workspace."""
    config = json.loads(
        files("terra_appstream").joinpath("asgen-config.json").read_text()
    )

    config["ArchiveRoot"] = archive_root
    if settings.media_base_url:
        config["MediaBaseUrl"] = settings.media_base_url
    if settings.html_base_url:
        config["HtmlBaseUrl"] = settings.html_base_url
    suites = {}
    for repo in repos:
        suite = suites.setdefault(repo.suite, {"sections": [], "architectures": [ARCH]})
        suite["sections"].append(repo.section)
    config["Suites"] = suites

    config_path = os.path.join(settings.workspace_dir, "asgen-config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
    logger.info(f"Wrote {config_path}")
    return config_path


def run(settings: Settings, log_name: str, *args: str) -> int:
    """Run an asgen subcommand, re-logging its output under log_name."""
    log = logging.getLogger(log_name)
    # exports to <workspace>/export (Settings.export_dir)
    cmd = [settings.asgen, "-w", settings.workspace_dir, *args]
    log.info(f"Running {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None

    # unprefixed lines inherit the last level
    level = logging.INFO
    for line in process.stdout:
        line = line.rstrip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if match:
            level = LEVELS.get(match["level"], logging.INFO)
            log.log(level, match["msg"], extra={"component": match["name"]})
        else:
            log.log(level, line)

    returncode = process.wait()
    if returncode != 0:
        log.error(f"{settings.asgen} exited with code {returncode}")
    return returncode
