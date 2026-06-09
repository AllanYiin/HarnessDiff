from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.project import utc_now_iso

ArtifactKind = Literal["plain_text", "markdown", "single_page_html", "svg"]
ArtifactIncludeMode = Literal["summary", "full"]


class ArtifactDocument(BaseModel):
    schema_version: str
    id: str
    project_id: str
    profile_id: str
    kind: ArtifactKind
    title: str
    content: str
    version: int = Field(ge=1)
    source_run_id: str | None = None
    created_at: str
    updated_at: str


class ArtifactCreate(BaseModel):
    profile_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    kind: ArtifactKind = "plain_text"
    title: str = Field(default="Untitled canvas", min_length=1, max_length=160)
    content: str = ""
    source_run_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class ArtifactPatch(BaseModel):
    base_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    kind: ArtifactKind | None = None
    content: str | None = None
    source_run_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def require_update(self) -> "ArtifactPatch":
        if self.title is None and self.kind is None and self.content is None and self.source_run_id is None:
            raise ValueError("Artifact patch must include at least one updated field.")
        return self


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactDocument]


def new_artifact_document(
    *,
    schema_version: str,
    artifact_id: str,
    project_id: str,
    payload: ArtifactCreate,
) -> ArtifactDocument:
    now = utc_now_iso()
    return ArtifactDocument(
        schema_version=schema_version,
        id=artifact_id,
        project_id=project_id,
        profile_id=payload.profile_id,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        version=1,
        source_run_id=payload.source_run_id,
        created_at=now,
        updated_at=now,
    )
