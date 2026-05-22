from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> None:
    load_env_file(ROOT / ".env")
    sys.path.insert(0, str(API_ROOT))
    host = os.environ.get("BACKEND_HOST") or os.environ.get("APP_BACKEND_HOST") or "127.0.0.1"
    port_text = os.environ.get("BACKEND_PORT") or os.environ.get("APP_BACKEND_PORT") or "8000"
    try:
        port = int(port_text)
    except ValueError:
        port = 8000
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
