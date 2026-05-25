from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.harness_modules import normalize_harness_modules
from app.models.project import utc_now_iso


class InputMode(str, Enum):
    integrated = "integrated"
    independent = "independent"


class RunStatus(str, Enum):
    submitted = "submitted"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ProfileConfig(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    harness_modules: dict[str, bool] = Field(default_factory=dict)

    @field_validator("harness_modules", mode="before")
    @classmethod
    def normalize_module_names(cls, value):
        return normalize_harness_modules(value if isinstance(value, dict) else {})


def default_profiles() -> list[ProfileConfig]:
    return [
        ProfileConfig(id="baseline", label="NoHarness", harness_modules={}),
        ProfileConfig(
            id="harness",
            label="Harness",
            harness_modules={
                "context_summary": True,
                "source_map": True,
                "guardrails": True,
                "output_contract": True,
                "planning_preamble": False,
                "tool_policy": True,
                "memory_selection": True,
                "post_answer_critique": True,
                "token_budgeter": True,
            },
        ),
    ]


class RunCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    prompt: str = Field(min_length=1)
    input_mode: InputMode = InputMode.integrated
    model: str = Field(default="gpt-5.4-mini", min_length=1)
    reasoning_effort: str = Field(default="medium", min_length=1)
    profiles: list[ProfileConfig] = Field(default_factory=default_profiles, min_length=1)


class RunDocument(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str
    id: str
    project_id: str
    turn_index: int
    input_mode: InputMode
    model: str
    reasoning_effort: str
    profiles: list[ProfileConfig]
    status: RunStatus = RunStatus.submitted
    prompt: str
    created_at: str
    updated_at: str


def new_run_document(
    *,
    schema_version: str,
    run_id: str,
    project_id: str,
    turn_index: int,
    payload: RunCreate,
    profiles: list[ProfileConfig] | None = None,
) -> RunDocument:
    now = utc_now_iso()
    return RunDocument(
        schema_version=schema_version,
        id=run_id,
        project_id=project_id,
        turn_index=turn_index,
        input_mode=payload.input_mode,
        model=payload.model,
        reasoning_effort=payload.reasoning_effort,
        profiles=profiles or payload.profiles,
        prompt=payload.prompt,
        created_at=now,
        updated_at=now,
    )
