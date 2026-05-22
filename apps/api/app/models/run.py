from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import utc_now_iso


class PaneId(str, Enum):
    no_harness = "NoHarness"
    harness = "Harness"


class InputMode(str, Enum):
    integrated = "integrated"
    independent = "independent"


class RunStatus(str, Enum):
    submitted = "submitted"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class RunCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    prompt: str = Field(min_length=1)
    input_mode: InputMode = InputMode.integrated
    model: str = Field(default="gpt-5.4-mini", min_length=1)
    reasoning_effort: str = Field(default="medium", min_length=1)
    target_panes: list[PaneId] = Field(default_factory=lambda: [PaneId.no_harness, PaneId.harness])
    harness_modules: dict[str, bool] | None = None


class RunDocument(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str
    id: str
    project_id: str
    turn_index: int
    input_mode: InputMode
    model: str
    reasoning_effort: str
    target_panes: list[PaneId]
    harness_modules: dict[str, bool] = Field(default_factory=dict)
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
    harness_modules: dict[str, bool] | None = None,
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
        target_panes=payload.target_panes,
        harness_modules=harness_modules or {},
        prompt=payload.prompt,
        created_at=now,
        updated_at=now,
    )
