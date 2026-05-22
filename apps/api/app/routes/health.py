from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    data_root = request.app.state.project_store.ensure_dirs()
    return {
        "status": "ok",
        "app": settings.app_name,
        "schema_version": settings.schema_version,
        "data_dir": str(data_root),
    }

