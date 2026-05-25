from __future__ import annotations

from pydantic import BaseModel, Field


class SkillSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = ""
    path: str


class SkillListResponse(BaseModel):
    home_dir: str
    skills_dir: str
    skills: list[SkillSummary]


class SkillImportFile(BaseModel):
    relative_path: str = Field(min_length=1, max_length=500)
    data_base64: str = Field(min_length=1)


class SkillImportRequest(BaseModel):
    mode: str = Field(pattern=r"^(zip|skill|folder)$")
    filename: str = Field(min_length=1, max_length=240)
    data_base64: str | None = None
    files: list[SkillImportFile] = Field(default_factory=list)


class SkillImportResponse(BaseModel):
    skill: SkillSummary

