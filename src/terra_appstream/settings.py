import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_dir: str
    out_dir: str
    # asgen's cache; must persist between runs
    workspace_dir: str
    media_base_url: str | None
    html_base_url: str | None
    asgen: str
    # dated composes kept per repo
    old_limit: int
    # glob patterns on repo names
    repos: tuple[str, ...]
    exclude_repos: tuple[str, ...]
    # repo of icon theme RPMs (Adwaita, Breeze, ...) used as every suite's baseSuite
    icon_themes_dir: str | None = None

    @property
    def export_dir(self) -> str:
        """asgen's own export, including the HTML report."""
        return os.path.join(self.workspace_dir, "export")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        required = ["BASE_DIR", "OUTPUT_DIR", "WORKSPACE_DIR"]
        missing = [var for var in required if var not in os.environ]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )

        return cls(
            base_dir=os.path.abspath(os.environ["BASE_DIR"]),
            out_dir=os.path.abspath(os.environ["OUTPUT_DIR"]),
            workspace_dir=os.path.abspath(os.environ["WORKSPACE_DIR"]),
            media_base_url=os.environ.get("MEDIA_BASE_URL"),
            html_base_url=os.environ.get("HTML_BASE_URL"),
            asgen=os.environ.get("ASGEN", "appstream-generator"),
            old_limit=max(1, int(os.environ.get("OLD_LIMIT", 5))),
            repos=_patterns(os.environ.get("REPOS", "*")),
            # SRPMs never contain AppStream data
            exclude_repos=_patterns(os.environ.get("EXCLUDE_REPOS", "*-source")),
            icon_themes_dir=os.environ.get("ICON_THEMES_DIR"),
        )


def _patterns(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())
