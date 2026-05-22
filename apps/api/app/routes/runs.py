from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.models.run import RunCreate, RunDocument
from app.services.run_orchestrator import RunOrchestrator, sse_encode
from app.storage.errors import InvalidProjectIdError, ProjectNotFoundError
from app.storage.project_store import ProjectStore

router = APIRouter(tags=["runs"])


def get_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(request: Request, project_id: str, payload: RunCreate) -> RunDocument:
    try:
        return get_store(request).create_run(project_id, payload)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid project or run id") from None


@router.get("/runs/{run_id}/stream")
async def stream_run(request: Request, run_id: str) -> StreamingResponse:
    try:
        run = get_store(request).get_run(run_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid run id") from None

    orchestrator = RunOrchestrator(get_store(request), request.app.state.llm_provider)

    async def event_source():
        async for payload in orchestrator.stream_run(run):
            yield sse_encode(payload)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

