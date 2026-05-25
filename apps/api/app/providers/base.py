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
class LLMRequest:
    profile_id: str
    profile_label: str
    model: str
    reasoning_effort: str
    instructions: str
    prompt: str
    conversation_messages: tuple[dict[str, str], ...] = ()
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


class ProviderConfigurationError(RuntimeError):
    pass
