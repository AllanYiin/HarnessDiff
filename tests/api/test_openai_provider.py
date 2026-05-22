from __future__ import annotations

import asyncio

import pytest

from app.providers.base import LLMRequest, ProviderConfigurationError
from app.providers.openai_responses import OpenAIResponsesProvider, _build_stream_kwargs, _to_dict


def test_openai_provider_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIResponsesProvider(api_key=None)
    request = LLMRequest(
        pane="Harness",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        instructions="test",
        prompt="hello",
    )

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(_drain_provider(provider, request))


def test_openai_stream_kwargs_match_sdk_stream_helper() -> None:
    request = LLMRequest(
        pane="Harness",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        instructions="test",
        prompt="hello",
    )

    kwargs = _build_stream_kwargs(request)

    assert kwargs["model"] == "gpt-5.4-mini"
    assert kwargs["input"] == "hello"
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert "stream" not in kwargs


def test_to_dict_falls_back_when_sdk_model_dump_fails() -> None:
    class UnserializableEvent:
        def model_dump(self, mode: str) -> dict[str, str]:
            raise TypeError("serializer unavailable")

    assert "repr" in _to_dict(UnserializableEvent())


async def _drain_provider(provider: OpenAIResponsesProvider, request: LLMRequest) -> None:
    async for _ in provider.stream_text(request):
        pass
