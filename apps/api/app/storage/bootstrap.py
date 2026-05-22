from __future__ import annotations

from pathlib import Path

from app.core.settings import settings


def ensure_storage_dirs(data_dir: Path | None = None) -> Path:
    root = (data_dir or settings.data_dir).resolve()
    (root / "projects").mkdir(parents=True, exist_ok=True)
    return root

