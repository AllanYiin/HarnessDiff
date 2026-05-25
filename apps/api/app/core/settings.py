from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


def resolve_harnessdiff_home(raw_home: str | os.PathLike[str] | None = None) -> Path:
    default_home = Path.home() / ".harnessdiff"
    configured_home = raw_home if raw_home is not None else os.environ.get("HARNESSDIFF_HOME")
    if configured_home is None or not str(configured_home).strip():
        return default_home.expanduser().resolve()

    resolved_home = Path(configured_home).expanduser().resolve()
    legacy_project_homes = {
        REPO_ROOT.resolve(),
        (REPO_ROOT / ".harnessdiff").resolve(),
    }
    if resolved_home in legacy_project_homes:
        return default_home.expanduser().resolve()
    return resolved_home


@dataclass(frozen=True)
class Settings:
    app_name: str = "HarnessDiff API"
    schema_version: str = "2026-05-22.1"
    data_dir: Path = Path(os.environ.get("HARNESSDIFF_DATA_DIR", "./data")).resolve()
    harnessdiff_home: Path = resolve_harnessdiff_home()

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
