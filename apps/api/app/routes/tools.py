from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.skill import ToolListResponse, ToolSummary, ToolUpdateRequest
from app.services.chat_tool_runtime import PARALLEL_TOOL_NAME
from app.services.skill_store import SkillStore, ToolManagementError
from app.services.subagent_runtime import SUBAGENT_TOOL_NAME
from app.services.tool_runtime import ALLOWED_TOOL_NAMES

router = APIRouter(prefix="/tools", tags=["tools"])


def get_skill_store(request: Request) -> SkillStore:
    return request.app.state.skill_store


def available_tool_names(request: Request) -> tuple[str, ...]:
    tool_runtime = getattr(request.app.state, "tool_runtime", None)
    names = (
        tuple(tool_runtime.list_tool_names())
        if tool_runtime is not None and hasattr(tool_runtime, "list_tool_names")
        else ALLOWED_TOOL_NAMES
    )
    return tuple(dict.fromkeys((*names, SUBAGENT_TOOL_NAME, PARALLEL_TOOL_NAME)))


@router.get("", response_model=ToolListResponse)
async def list_tools(request: Request) -> ToolListResponse:
    store = get_skill_store(request)
    return ToolListResponse(tools=store.list_tools(available_tool_names(request)))


@router.patch("/{tool_id:path}", response_model=ToolSummary)
async def update_tool(
    request: Request, tool_id: str, payload: ToolUpdateRequest
) -> ToolSummary:
    try:
        return get_skill_store(request).update_tool_enabled(
            tool_id,
            payload.enabled,
            available_tool_names(request),
        )
    except ToolManagementError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from None


@router.delete("/{tool_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(request: Request, tool_id: str) -> Response:
    try:
        get_skill_store(request).delete_tool(tool_id, available_tool_names(request))
    except ToolManagementError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
