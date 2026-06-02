from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.skill import (
    SkillImportRequest,
    SkillImportResponse,
    SkillListResponse,
    SkillSummary,
    SkillUpdateRequest,
)
from app.services.skill_store import SkillImportError, SkillStore

router = APIRouter(prefix="/skills", tags=["skills"])


def get_skill_store(request: Request) -> SkillStore:
    return request.app.state.skill_store


@router.get("", response_model=SkillListResponse)
async def list_skills(request: Request) -> SkillListResponse:
    store = get_skill_store(request)
    store.ensure_dirs()
    return SkillListResponse(
        home_dir=str(store.home_dir),
        skills_dir=str(store.skills_dir),
        skills=store.list_skills(include_disabled=True),
    )


@router.get("/{skill_id}")
async def get_skill(request: Request, skill_id: str) -> dict[str, str]:
    try:
        return get_skill_store(request).read_skill(skill_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Skill not found") from None


@router.post("/import", response_model=SkillImportResponse, status_code=status.HTTP_201_CREATED)
async def import_skill(request: Request, payload: SkillImportRequest) -> SkillImportResponse:
    store = get_skill_store(request)
    try:
        if payload.mode == "zip":
            if not payload.data_base64:
                raise SkillImportError("Zip import requires data_base64.")
            skill = store.import_zip(payload.filename, payload.data_base64)
        elif payload.mode == "skill":
            if not payload.data_base64:
                raise SkillImportError("Skill file import requires data_base64.")
            skill = store.import_skill_file(payload.filename, payload.data_base64)
        else:
            skill = store.import_folder(payload.files, payload.filename)
        return SkillImportResponse(skill=skill)
    except SkillImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.patch("/{skill_id}", response_model=SkillSummary)
async def update_skill(
    request: Request, skill_id: str, payload: SkillUpdateRequest
) -> SkillSummary:
    try:
        return get_skill_store(request).update_skill_enabled(skill_id, payload.enabled)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Skill not found") from None
    except SkillImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(request: Request, skill_id: str) -> Response:
    try:
        get_skill_store(request).delete_skill(skill_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Skill not found") from None
    except SkillImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
