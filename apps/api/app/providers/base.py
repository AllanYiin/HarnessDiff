from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRequest:
    pane: str
    model: str
    reasoning_effort: str
    instructions: str
    prompt: str


@dataclass(frozen=True)
class ProviderEvent:
    type: str
    pane: str
    sequence: int
    text: str | None = None
    response_id: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider:
    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        raise NotImplementedError


class ProviderConfigurationError(RuntimeError):
    pass

