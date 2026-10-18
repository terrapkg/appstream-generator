import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_dir: str
    out_dir: str
    # Holds asgen's LMDB cache, so it must persist between runs
    workspace_dir: str
    # Public URLs the exported data is served from (optional)
    media_base_url: str | None
    html_base_url: str | None
    asgen: str
    # Dated composes to keep per repo; readers may still hold older `latest` targets
    old_limit: int

    @classmethod
    def from_env(cls) -> "Settings":
        # note: this is for DX, not really needed
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
        )
