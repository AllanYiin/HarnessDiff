from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    source: str = "missing"


class ContextSection(BaseModel):
    key: str
    label: str
    status: str
    characters: int = 0
    estimated_tokens: int = 0
    notes: str = ""


class ProfileAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    profile_id: str
    profile_label: str
    current_turn_usage: TokenUsage = Field(default_factory=TokenUsage)
    cumulative_usage: TokenUsage = Field(default_factory=TokenUsage)
    context_sections: list[ContextSection] = Field(default_factory=list)
    output_characters: int = 0
    enabled_harness_modules: list[str] = Field(default_factory=list)
    harness_decisions: list[dict[str, Any]] = Field(default_factory=list)
    provider_context_keys: list[str] = Field(default_factory=list)
    subagent_count: int = 0
    subagent_usage_total: TokenUsage = Field(default_factory=TokenUsage)
    caller_usage_total: TokenUsage = Field(default_factory=TokenUsage)
    subagents: dict[str, "SubagentAnalysis"] = Field(default_factory=dict)


class SubagentAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    subagent_id: str
    subagent_label: str
    current_turn_usage: TokenUsage = Field(default_factory=TokenUsage)
    output_characters: int = 0
    event_counts: dict[str, int] = Field(default_factory=dict)
    context_sections: list[ContextSection] = Field(default_factory=list)
    provider_context_keys: list[str] = Field(default_factory=list)


class AnalysisComparison(BaseModel):
    total_token_delta: int = 0
    input_token_delta: int = 0
    output_token_delta: int = 0
    reasoning_token_delta: int = 0
    controlled_profile_extra_sections: list[str] = Field(default_factory=list)


class AnalysisDocument(BaseModel):
    schema_version: str
    project_id: str
    run_id: str
    turn_index: int
    generated_at: str
    profiles: dict[str, ProfileAnalysis]
    comparison: AnalysisComparison = Field(default_factory=AnalysisComparison)
    notes: list[str] = Field(default_factory=list)
    raw_sources: dict[str, Any] = Field(default_factory=dict)
