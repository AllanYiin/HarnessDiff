from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.project import ProjectCreate, ProjectDocument, ProjectListResponse, ProjectUpdate
from app.storage.errors import InvalidProjectIdError, ProjectNotFoundError, StorageCorruptionError
from app.storage.project_store import ProjectStore

router = APIRouter(prefix="/projects", tags=["projects"])


def get_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


@router.get("", response_model=ProjectListResponse)
async def list_projects(request: Request) -> ProjectListResponse:
    return ProjectListResponse(projects=get_store(request).list_projects())


@router.post("", response_model=ProjectDocument, status_code=status.HTTP_201_CREATED)
async def create_project(request: Request, payload: ProjectCreate) -> ProjectDocument:
    return get_store(request).create_project(payload)


@router.get("/{project_id}", response_model=ProjectDocument)
async def get_project(request: Request, project_id: str) -> ProjectDocument:
    try:
        return get_store(request).get_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid project id") from None
    except StorageCorruptionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Project storage is corrupt",
                "repair_report": str(exc.report_path),
            },
        ) from None


@router.get("/{project_id}/transcript")
async def get_project_transcript(request: Request, project_id: str) -> dict:
    try:
        store = get_store(request)
        project = store.get_project(project_id)
        runs = []
        for run in store.list_run_documents(project_id):
            profiles = []
            for profile in run.profiles:
                profiles.append(
                    {
                        **profile.model_dump(mode="json"),
                        "output_text": store.read_profile_output_text(
                            project_id, run.id, profile.id
                        ),
                        "steps": store.read_agent_steps(project_id, run.id, profile.id)
                        if project.surface_type == "agent"
                        else [],
                        "tool_calls": store.read_profile_tool_calls(
                            project_id, run.id, profile.id
                        ),
                        "skill_invocations": store.read_profile_skill_invocations(
                            project_id, run.id, profile.id
                        ),
                    }
                )
            runs.append({**run.model_dump(mode="json", exclude_none=True), "profiles": profiles})
        return {"project": project.model_dump(mode="json"), "runs": runs}
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid project id") from None


@router.patch("/{project_id}", response_model=ProjectDocument)
async def update_project(
    request: Request, project_id: str, payload: ProjectUpdate
) -> ProjectDocument:
    try:
        return get_store(request).update_project(project_id, payload)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid project id") from None
    except StorageCorruptionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Project storage is corrupt",
                "repair_report": str(exc.report_path),
            },
        ) from None


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(request: Request, project_id: str) -> Response:
    try:
        get_store(request).delete_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except InvalidProjectIdError:
        raise HTTPException(status_code=400, detail="Invalid project id") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
