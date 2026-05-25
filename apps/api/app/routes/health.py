from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

from app.core.settings import settings
from app.services.chat_tool_runtime import PARALLEL_TOOL_NAME
from app.services.subagent_runtime import SUBAGENT_TOOL_NAME

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    data_root = request.app.state.project_store.ensure_dirs()
    skill_store = getattr(request.app.state, "skill_store", None)
    skill_home = skill_store.ensure_dirs() if skill_store is not None else None
    tool_runtime = getattr(request.app.state, "tool_runtime", None)
    tool_names = (
        list(tool_runtime.list_tool_names())
        if tool_runtime is not None and hasattr(tool_runtime, "list_tool_names")
        else []
    )
    if tool_names and SUBAGENT_TOOL_NAME not in tool_names:
        tool_names.append(SUBAGENT_TOOL_NAME)
    if tool_names and PARALLEL_TOOL_NAME not in tool_names:
        tool_names.append(PARALLEL_TOOL_NAME)
    return {
        "status": "ok",
        "app": settings.app_name,
        "schema_version": settings.schema_version,
        "data_dir": str(data_root),
        "harnessdiff_home": str(skill_home) if skill_home is not None else "",
        "tools": {
            "enabled": bool(tool_names),
            "count": len(tool_names),
            "names": tool_names,
            "web_search_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
        },
    }
