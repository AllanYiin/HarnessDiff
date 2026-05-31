from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AnalysisComparison, TokenUsage


class AgentRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent"] = "agent"
    objective: str = Field(min_length=1)
    context: str = ""
    max_steps: int = Field(default=16, ge=1, le=64)
    allow_subagents: bool = True
    allow_container_tools: bool = True


class AgentStepEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    run_id: str
    profile_id: str
    profile_label: str = ""
    step_id: str
    sequence: int = Field(ge=0)
    type: str
    label: str
    status: Literal["running", "completed", "error", "cancelled", "skipped"] = "running"
    tool_name: str | None = None
    subagent_id: str | None = None
    subagent_label: str | None = None
    elapsed_ms: int | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AgentProfileAnalysis(BaseModel):
    profile_id: str
    profile_label: str
    current_turn_usage: TokenUsage = Field(default_factory=TokenUsage)
    output_characters: int = 0
    step_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    subagent_count: int = 0
    subagent_usage_total: TokenUsage = Field(default_factory=TokenUsage)
    harness_decision_count: int = 0
    error_count: int = 0


class AgentAnalysisDocument(BaseModel):
    schema_version: str
    project_id: str
    run_id: str
    turn_index: int
    generated_at: str
    profiles: dict[str, AgentProfileAnalysis]
    comparison: AnalysisComparison = Field(default_factory=AnalysisComparison)
    notes: list[str] = Field(default_factory=list)
    raw_sources: dict[str, Any] = Field(default_factory=dict)
