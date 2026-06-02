from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.skill import (
    SubagentCreateRequest,
    SubagentCreateResponse,
    SubagentListResponse,
    SubagentSummary,
    SubagentUpdateRequest,
)
from app.services.skill_store import SkillStore, SubagentDefinitionError

router = APIRouter(prefix="/subagents", tags=["subagents"])


def get_skill_store(request: Request) -> SkillStore:
    return request.app.state.skill_store


@router.get("", response_model=SubagentListResponse)
async def list_subagents(request: Request) -> SubagentListResponse:
    store = get_skill_store(request)
    store.ensure_dirs()
    return SubagentListResponse(
        agents_dir=str(store.agents_dir),
        subagents=store.list_subagents(),
    )


@router.post("", response_model=SubagentCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_subagent(
    request: Request, payload: SubagentCreateRequest
) -> SubagentCreateResponse:
    store = get_skill_store(request)
    try:
        return SubagentCreateResponse(subagent=store.create_subagent(payload))
    except SubagentDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.patch("/{subagent_id}", response_model=SubagentSummary)
async def update_subagent(
    request: Request, subagent_id: str, payload: SubagentUpdateRequest
) -> SubagentSummary:
    try:
        return get_skill_store(request).update_subagent_enabled(subagent_id, payload.enabled)
    except SubagentDefinitionError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from None


@router.delete("/{subagent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subagent(request: Request, subagent_id: str) -> Response:
    try:
        get_skill_store(request).delete_subagent(subagent_id)
    except SubagentDefinitionError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
