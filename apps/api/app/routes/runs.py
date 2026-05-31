from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.models.analysis import AnalysisDocument
from app.models.project import SurfaceType
from app.models.run import RunCreate, RunDocument
from app.services.agent_orchestrator import AgentRunOrchestrator
from app.services.agent_analysis_builder import build_agent_run_analysis
from app.services.analysis_builder import build_run_analysis
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

    project = get_store(request).get_project(run.project_id)
    orchestrator_class = AgentRunOrchestrator if project.surface_type == SurfaceType.agent else RunOrchestrator
    orchestrator = orchestrator_class(
        get_store(request),
        request.app.state.llm_provider,
        request.app.state.tool_runtime,
        skill_store=request.app.state.skill_store,
    )

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


@router.get("/runs/{run_id}/analysis", response_model=AnalysisDocument)
async def get_run_analysis(request: Request, run_id: str) -> AnalysisDocument:
    try:
        run = get_store(request).get_run(run_id)
        project = get_store(request).get_project(run.project_id)
        if project.surface_type == SurfaceType.agent:
            try:
                return AnalysisDocument.model_validate(
                    get_store(request).read_agent_analysis(run.project_id, run.id)
                )
            except ProjectNotFoundError:
                analysis = build_agent_run_analysis(
                    run,
                    get_store(request).get_run_dir(run.project_id, run.id),
                )
                get_store(request).write_agent_analysis(
                    run.project_id, run.id, analysis.model_dump(mode="json")
                )
                return analysis
        try:
            return AnalysisDocument.model_validate(
                get_store(request).read_run_analysis(run.project_id, run.id)
            )
        except ProjectNotFoundError:
            analysis = build_run_analysis(
                run,
                get_store(request).get_run_dir(run.project_id, run.id),
                get_store(request).list_run_dirs(run.project_id),
            )
            get_store(request).write_run_analysis(
                run.project_id, run.id, analysis.model_dump(mode="json")
            )
            return analysis
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid run id") from None
