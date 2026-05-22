from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from app.providers.base import LLMProvider, LLMRequest, ProviderConfigurationError, ProviderEvent


class OpenAIResponsesProvider(LLMProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is required for OpenAI streaming.")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ProviderConfigurationError("The openai package is required.") from exc

        client = AsyncOpenAI(api_key=self.api_key)
        sequence = 0
        create_kwargs = _build_stream_kwargs(request)
        async with client.responses.stream(**create_kwargs) as stream:
            async for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    yield ProviderEvent(
                        type="created",
                        pane=request.pane,
                        sequence=sequence,
                        response_id=getattr(response, "id", None),
                        raw=_to_dict(event),
                    )
                elif event_type == "response.output_text.delta":
                    sequence += 1
                    yield ProviderEvent(
                        type="delta",
                        pane=request.pane,
                        sequence=sequence,
                        text=getattr(event, "delta", ""),
                        raw=_to_dict(event),
                    )
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    yield ProviderEvent(
                        type="completed",
                        pane=request.pane,
                        sequence=sequence + 1,
                        response_id=getattr(response, "id", None),
                        usage=_extract_usage(response),
                        raw=_to_dict(event),
                    )
                elif event_type == "error":
                    yield ProviderEvent(
                        type="error",
                        pane=request.pane,
                        sequence=sequence + 1,
                        raw=_to_dict(event),
                    )


def _build_stream_kwargs(request: LLMRequest) -> dict[str, Any]:
    create_kwargs: dict[str, Any] = {
        "model": request.model,
        "instructions": request.instructions,
        "input": request.prompt,
    }
    if request.reasoning_effort:
        create_kwargs["reasoning"] = {"effort": request.reasoning_effort}
    return create_kwargs


def _to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            dumped = value.to_dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {"repr": repr(value)}


def _extract_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump(mode="json")
    elif isinstance(usage, dict):
        raw = usage
    else:
        raw = {"raw": repr(usage)}

    output_details = raw.get("output_tokens_details") or {}
    return {
        "input_tokens": raw.get("input_tokens"),
        "output_tokens": raw.get("output_tokens"),
        "reasoning_tokens": output_details.get("reasoning_tokens"),
        "total_tokens": raw.get("total_tokens"),
        "provider_raw_usage": raw,
    }
