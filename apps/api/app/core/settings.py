from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "HarnessDiff API"
    schema_version: str = "2026-05-22.1"
    data_dir: Path = Path(os.environ.get("HARNESSDIFF_DATA_DIR", "./data")).resolve()
    harnessdiff_home: Path = Path(
        os.environ.get("HARNESSDIFF_HOME", Path.home() / ".harnessdiff")
    ).expanduser().resolve()

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
