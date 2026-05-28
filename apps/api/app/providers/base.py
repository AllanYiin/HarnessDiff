from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class ToolRuntime(Protocol):
    def list_openai_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_tool_names(self) -> tuple[str, ...]:
        raise NotImplementedError

    async def invoke_openai_tool(
        self, openai_name: str, arguments: dict[str, Any]
    ) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class LLMImageAttachment:
    name: str
    mime_type: str
    size_bytes: int
    image_url: str
    detail: str = "auto"


@dataclass(frozen=True)
class SkillSelectionRequest:
    model: str
    prompt: str
    skills: tuple[dict[str, str], ...]
    max_selected: int = 3


@dataclass(frozen=True)
class SkillSelectionResult:
    selected_skill_ids: tuple[str, ...] = ()
    source: str = "none"
    error: str = ""


@dataclass(frozen=True)
class LLMRequest:
    profile_id: str
    profile_label: str
    model: str
    reasoning_effort: str
    instructions: str
    prompt: str
    image_attachments: tuple[LLMImageAttachment, ...] = ()
    conversation_messages: tuple[dict[str, str], ...] = ()
    prompt_cache_key: str = ""
    tools_enabled: bool = False
    tool_context: ToolRuntime | None = None
    subagent_id: str | None = None
    subagent_label: str | None = None
    parent_profile_id: str | None = None


@dataclass(frozen=True)
class ProviderEvent:
    type: str
    profile_id: str
    profile_label: str
    sequence: int
    text: str | None = None
    message: str | None = None
    subagent_id: str | None = None
    subagent_label: str | None = None
    parent_profile_id: str | None = None
    response_id: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider:
    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        raise NotImplementedError

    async def select_skills(self, request: SkillSelectionRequest) -> SkillSelectionResult:
        return SkillSelectionResult(source="not_supported")


class ProviderConfigurationError(RuntimeError):
    pass
