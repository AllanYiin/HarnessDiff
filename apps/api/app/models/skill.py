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


class SubagentSummary(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    label: str
    description: str = ""
    model: str = "gpt-5.4-mini"
    reasoning_effort: str = "medium"
    max_output_chars: int = 4000
    tools: list[str] = Field(default_factory=list)
    enabled: bool = True
    path: str


class SubagentListResponse(BaseModel):
    agents_dir: str
    subagents: list[SubagentSummary]


class SubagentCreateRequest(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    instructions: str = Field(min_length=1, max_length=12000)
    model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=120)
    reasoning_effort: str = Field(default="medium", pattern=r"^(low|medium|high|xhigh)$")
    max_output_chars: int = Field(default=4000, ge=256, le=20000)
    tools: list[str] = Field(default_factory=list, max_length=8)
    enabled: bool = True


class SubagentCreateResponse(BaseModel):
    subagent: SubagentSummary
