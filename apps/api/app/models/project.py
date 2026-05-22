from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SurfaceType(str, Enum):
    chat = "chat"
    workflow = "workflow"
    agent = "agent"
    multi_agents = "multi_agents"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectDocument(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str
    id: str
    name: str
    surface_type: SurfaceType = SurfaceType.chat
    config_profile: str = "harness.default"
    created_at: str
    updated_at: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    surface_type: SurfaceType = SurfaceType.chat
    config_profile: str = Field(default="harness.default", min_length=1, max_length=120)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    surface_type: SurfaceType | None = None
    config_profile: str | None = Field(default=None, min_length=1, max_length=120)


class ProjectListResponse(BaseModel):
    projects: list[ProjectDocument]

