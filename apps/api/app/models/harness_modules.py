from __future__ import annotations

from collections.abc import Mapping
from typing import Any


HARNESS_MODULE_ALIASES = {
    "context_manifest": "context_summary",
}


def normalize_harness_modules(modules: Mapping[str, Any] | None) -> dict[str, bool]:
    if not modules:
        return {}
    normalized: dict[str, bool] = {}
    for name, enabled in modules.items():
        canonical_name = HARNESS_MODULE_ALIASES.get(name, name)
        if name in HARNESS_MODULE_ALIASES and canonical_name in modules:
            continue
        normalized[canonical_name] = bool(enabled)
    return normalized
