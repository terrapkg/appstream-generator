"""Run the generator on a directory of RPMs and report what it would do.

    terra-appstream-lint [--fail-on error|warning|never] [--report-dir OUT] DIR

Builds a throwaway repo from the RPMs under DIR, runs asgen on it with the
same config as the pipeline, and reports components and hints. Inside GitHub
Actions, hints become annotations and a table goes to the job summary.
"""

import argparse
import gzip
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from terra_appstream import asgen
from terra_appstream.cli import setup_logging
from terra_appstream.repos import ARCH, Repo, build_archive_tree
from terra_appstream.settings import Settings

logger = logging.getLogger("terra-appstream-lint")

REPO = Repo.from_name("lint")
ANNOTATIONS = {"error": "error", "warning": "warning"}  # everything else: notice
FAILS_ON = {"error": {"error"}, "warning": {"error", "warning"}, "never": set()}


def render(template: str, variables: dict) -> str:
    """Fill a hint-definitions.json template and drop its HTML tags."""
    text = re.sub(
        r"\{\{\s*(\w+)\s*\}\}", lambda m: str(variables.get(m[1], m[0])), template
    )
    text = re.sub(r"<br\s*/?>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def read_json_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def collect(export: Path) -> tuple[list[dict], list[dict]]:
    """Return (components, hints) from asgen's export of the lint repo."""
    data = export / "data" / REPO.suite / REPO.section
    hints_dir = export / "hints" / REPO.suite

    components = []
    catalog = data / f"Components-{ARCH}.xml.gz"
    if catalog.is_file():
        with gzip.open(catalog) as f:
            for cpt in ET.parse(f).getroot().findall("component"):
                components.append(
                    {"id": cpt.findtext("id"), "package": cpt.findtext("pkgname")}
                )

    hints = []
    hints_file = hints_dir / REPO.section / f"Hints-{ARCH}.json.gz"
    definitions_file = hints_dir / "hint-definitions.json"
    if hints_file.is_file():
        definitions = json.loads(definitions_file.read_text())
        for entry in read_json_gz(hints_file):
            for cid, cpt_hints in entry["hints"].items():
                for hint in cpt_hints:
                    definition = definitions.get(hint["tag"], {})
                    hints.append(
                        {
                            "package": entry["package"],
                            "component": cid,
                            "tag": hint["tag"],
                            "severity": definition.get("severity", "info"),
                            "message": render(
                                definition.get("text", hint["tag"]), hint.get("vars", {})
                            ),
                        }
                    )
    return components, hints


def escape_annotation(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(components: list[dict], hints: list[dict]):
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for cpt in components:
        print(f"component {cpt['id']} (package {cpt['package']})")
    for h in hints:
        if in_actions:
            level = ANNOTATIONS.get(h["severity"], "notice")
            title = escape_annotation(f"{h['package']}: {h['tag']}")
            print(f"::{level} title={title}::{escape_annotation(h['component'] + ': ' + h['message'])}")
        else:
            print(f"{h['severity']:9} {h['package']} {h['component']} {h['tag']}: {h['message']}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(summary_markdown(components, hints))


# GitHub drops a step summary over 1 MiB entirely
SUMMARY_LIMIT = 900 * 1024
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2, "pedantic": 3}


URL_RE = re.compile(r"https?://[^\s<>'\"|]+")


def text_cell(text: str) -> str:
    """Plain text for a GFM table cell: no HTML, no Markdown, no column breaks."""

    def escape(part: str) -> str:
        part = html.escape(part, quote=False)  # e.g. <url/>, which GitHub would drop
        return re.sub(r"([\\`*_~\[\]])", r"\\\1", part)

    # GitHub autolinks bare URLs and keeps escapes in them literally, so URLs go in
    # raw (URL_RE stops at anything that could break the table or start HTML)
    parts, pos = [], 0
    for match in URL_RE.finditer(text):
        parts += [escape(text[pos : match.start()]), match[0]]
        pos = match.end()
    parts.append(escape(text[pos:]))
    return "".join(parts).replace("|", "\\|").replace("\n", "<br>")


def code_cell(text: str) -> str:
    # escapes inside a code span show literally; only | must go (table syntax)
    return "`" + text.replace("|", "\\|") + "`"


def summary_markdown(components: list[dict], hints: list[dict]) -> str:
    lines = ["## AppStream lint", ""]
    if components:
        lines += ["| Component | Package |", "| --- | --- |"]
        lines += [f"| {code_cell(c['id'])} | {text_cell(c['package'])} |" for c in components]
    else:
        lines.append("No components would be published.")
    lines.append("")
    if not hints:
        lines.append("No hints.")
        return "\n".join(lines) + "\n\n"

    lines += ["| Severity | Package | Component | Hint | Message |", "| --- | --- | --- | --- | --- |"]
    size = len("\n".join(lines).encode())
    ordered = sorted(hints, key=lambda h: SEVERITY_ORDER.get(h["severity"], 9))
    for shown, h in enumerate(ordered):
        row = (
            f"| {h['severity']} | {text_cell(h['package'])} | {code_cell(h['component'])} "
            f"| {code_cell(h['tag'])} | {text_cell(h['message'])} |"
        )
        size += len(row.encode()) + 1
        if size > SUMMARY_LIMIT:
            lines += ["", f"{len(ordered) - shown} more hints left out to stay under GitHub's summary size limit; see the annotations or the log."]
            break
        lines.append(row)
    return "\n".join(lines) + "\n\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, help="directory with the RPMs (searched recursively)")
    parser.add_argument("--fail-on", choices=FAILS_ON, default="error")
    parser.add_argument("--report-dir", type=Path, help="copy asgen's export directory here, unchanged")
    args = parser.parse_args()
    setup_logging()

    rpms = sorted(p for p in args.path.rglob("*.rpm") if not p.name.endswith(".src.rpm"))
    if not rpms:
        logger.error(f"No binary RPMs found under {args.path}")
        sys.exit(2)

    with tempfile.TemporaryDirectory(prefix="terra-appstream-lint-") as tmp:
        settings = Settings(
            base_dir=os.path.join(tmp, "base"),
            out_dir=os.path.join(tmp, "out"),
            workspace_dir=os.path.join(tmp, "workspace"),
            media_base_url=None,
            html_base_url=None,
            asgen=os.environ.get("ASGEN", "appstream-generator"),
            old_limit=1,
            repos=("*",),
            exclude_repos=(),
        )
        repo_dir = Path(settings.base_dir, REPO.name)
        repo_dir.mkdir(parents=True)
        for rpm in rpms:
            (repo_dir / rpm.name).symlink_to(rpm.resolve())
        subprocess.run(["createrepo_c", "-q", str(repo_dir)], check=True)

        os.makedirs(settings.workspace_dir)
        archive_root = build_archive_tree(settings.base_dir, settings.workspace_dir, [REPO])
        asgen.write_config(settings, [REPO], archive_root)
        if asgen.run(settings, REPO.logger("asgen"), "run", REPO.suite, REPO.section) != 0:
            sys.exit(2)

        components, hints = collect(Path(settings.export_dir))
        if args.report_dir:
            shutil.copytree(settings.export_dir, args.report_dir, dirs_exist_ok=True)

    report(components, hints)
    severities = {h["severity"] for h in hints}
    if severities & FAILS_ON[args.fail_on]:
        sys.exit(1)
