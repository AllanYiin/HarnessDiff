from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.providers.base import LLMRequest, ProviderConfigurationError
from app.providers.openai_responses import (
    DEFAULT_MAX_TOOL_ROUNDS,
    OpenAIResponsesProvider,
    _build_stream_kwargs,
    _extract_usage,
    _to_dict,
)


def test_openai_provider_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIResponsesProvider(api_key=None)
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        instructions="test",
        prompt="hello",
    )

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(_drain_provider(provider, request))


def test_openai_provider_reads_tool_round_limit_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESSDIFF_MAX_TOOL_ROUNDS", "9")

    provider = OpenAIResponsesProvider(api_key="test")

    assert provider.max_tool_rounds == 9


def test_openai_provider_uses_default_tool_round_limit_for_bad_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESSDIFF_MAX_TOOL_ROUNDS", "bad")

    provider = OpenAIResponsesProvider(api_key="test")

    assert provider.max_tool_rounds == DEFAULT_MAX_TOOL_ROUNDS


def test_openai_stream_kwargs_match_sdk_stream_helper() -> None:
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
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


def test_openai_stream_kwargs_replays_profile_local_conversation_messages() -> None:
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        instructions="test",
        prompt="second",
        conversation_messages=(
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "first answer"},
        ),
    )

    kwargs = _build_stream_kwargs(request)

    assert kwargs["input"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second"},
    ]


def test_openai_stream_kwargs_can_include_tools() -> None:
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        instructions="test",
        prompt="hello",
    )
    tools = [{"type": "function", "name": "standard_fs_read", "parameters": {"type": "object"}}]

    kwargs = _build_stream_kwargs(request, tools=tools)

    assert kwargs["tools"] == tools


def test_to_dict_falls_back_when_sdk_model_dump_fails() -> None:
    class UnserializableEvent:
        def model_dump(self, mode: str) -> dict[str, str]:
            raise TypeError("serializer unavailable")

    assert "repr" in _to_dict(UnserializableEvent())


def test_openai_error_event_exposes_message() -> None:
    client = FakeOpenAIClient(
        [
            [
                SimpleNamespace(
                    type="error",
                    error={"message": "Rate limit reached."},
                )
            ]
        ]
    )
    provider = OpenAIResponsesProvider(api_key="test", client_factory=lambda: client)
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="fake-model",
        reasoning_effort="medium",
        instructions="test",
        prompt="hello",
    )

    events = asyncio.run(_collect_provider_events(provider, request))

    assert any(
        event.type == "error" and event.message == "Rate limit reached."
        for event in events
    )


def test_extract_usage_includes_cached_input_tokens() -> None:
    class Usage:
        def model_dump(self, mode: str) -> dict:
            return {
                "input_tokens": 30,
                "input_tokens_details": {"cached_tokens": 12},
                "output_tokens": 15,
                "output_tokens_details": {"reasoning_tokens": 4},
                "total_tokens": 45,
            }

    class Response:
        usage = Usage()

    assert _extract_usage(Response()) == {
        "input_tokens": 30,
        "cached_tokens": 12,
        "output_tokens": 15,
        "reasoning_tokens": 4,
        "total_tokens": 45,
        "provider_raw_usage": {
            "input_tokens": 30,
            "input_tokens_details": {"cached_tokens": 12},
            "output_tokens": 15,
            "output_tokens_details": {"reasoning_tokens": 4},
            "total_tokens": 45,
        },
    }


def test_extract_usage_normalizes_missing_token_details_to_zero() -> None:
    class Response:
        usage = {
            "input_tokens": 148,
            "output_tokens": 1685,
            "output_tokens_details": {"reasoning_tokens": 911},
            "total_tokens": 1833,
        }

    usage = _extract_usage(Response())

    assert usage is not None
    assert usage["input_tokens"] == 148
    assert usage["cached_tokens"] == 0
    assert usage["output_tokens"] == 1685
    assert usage["reasoning_tokens"] == 911
    assert usage["total_tokens"] == 1833


async def _drain_provider(provider: OpenAIResponsesProvider, request: LLMRequest) -> None:
    async for _ in provider.stream_text(request):
        pass


def test_openai_provider_executes_function_call_and_resumes_with_tool_output() -> None:
    runtime = FakeToolRuntime()
    client = FakeOpenAIClient(
        [
            [
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="resp_tool",
                        output=[
                            {
                                "type": "reasoning",
                                "id": "rs_1",
                                "summary": [],
                                "status": "completed",
                            },
                            {
                                "type": "function_call",
                                "name": "standard_fs_read",
                                "call_id": "call_1",
                                "arguments": '{"relative_path":"README.md"}',
                                "status": "completed",
                            }
                        ],
                    ),
                )
            ],
            [
                SimpleNamespace(type="response.created", response=SimpleNamespace(id="resp_final")),
                SimpleNamespace(type="response.output_text.delta", delta="done"),
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(id="resp_final", output=[]),
                ),
            ],
        ]
    )
    provider = OpenAIResponsesProvider(
        api_key="test",
        client_factory=lambda: client,
    )
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="fake-model",
        reasoning_effort="medium",
        instructions="test",
        prompt="read",
        tools_enabled=True,
        tool_context=runtime,
    )

    events = asyncio.run(_collect_provider_events(provider, request))

    assert runtime.calls == [("standard_fs_read", {"relative_path": "README.md"})]
    assert any(event.type == "tool_call" for event in events)
    assert any(event.type == "delta" and event.text == "done" for event in events)
    assert client.calls[0]["tools"] == runtime.list_openai_tools()
    assert client.calls[1]["previous_response_id"] == "resp_tool"
    assert client.calls[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": client.calls[1]["input"][0]["output"],
        }
    ]
    assert "status" not in client.calls[1]["input"][0]
    assert '"ok": true' in client.calls[1]["input"][0]["output"]


def test_openai_provider_enriches_web_tool_output_with_citation_sources() -> None:
    runtime = FakeWebToolRuntime()
    client = FakeOpenAIClient(
        [
            [
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="resp_tool",
                        output=[
                            {
                                "type": "function_call",
                                "name": "standard_web_search",
                                "call_id": "call_search",
                                "arguments": '{"query":"HarnessDiff"}',
                            }
                        ],
                    ),
                )
            ],
            [
                SimpleNamespace(type="response.created", response=SimpleNamespace(id="resp_final")),
                SimpleNamespace(type="response.output_text.delta", delta="done"),
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(id="resp_final", output=[]),
                ),
            ],
        ]
    )
    provider = OpenAIResponsesProvider(api_key="test", client_factory=lambda: client)
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="fake-model",
        reasoning_effort="medium",
        instructions="test",
        prompt="search",
        tools_enabled=True,
        tool_context=runtime,
    )

    asyncio.run(_collect_provider_events(provider, request))

    output = json.loads(client.calls[1]["input"][0]["output"])
    assert output["citation_sources"] == [
        {
            "url": "https://example.test/source",
            "title": "Example Source",
            "source": "Example",
            "rank": 1,
        }
    ]
    assert output["citation_guidance"]["required"] is True
    assert "Sources" in output["citation_guidance"]["style"]


def test_openai_provider_stops_when_tool_round_limit_is_exceeded() -> None:
    runtime = FakeToolRuntime()
    client = FakeOpenAIClient(
        [
            [
                SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(
                        id="resp_tool",
                        output=[
                            {
                                "type": "function_call",
                                "name": "standard_fs_read",
                                "call_id": "call_1",
                                "arguments": "{}",
                            }
                        ],
                    ),
                )
            ]
        ]
    )
    provider = OpenAIResponsesProvider(
        api_key="test",
        client_factory=lambda: client,
        max_tool_rounds=0,
    )
    request = LLMRequest(
        profile_id="harness",
        profile_label="Harness",
        model="fake-model",
        reasoning_effort="medium",
        instructions="test",
        prompt="read",
        tools_enabled=True,
        tool_context=runtime,
    )

    events = asyncio.run(_collect_provider_events(provider, request))

    assert runtime.calls == []
    assert any(
        event.type == "error"
        and event.raw["type"] == "tool_round_limit_exceeded"
        and "工具迴圈超過上限" in (event.message or "")
        for event in events
    )


async def _collect_provider_events(
    provider: OpenAIResponsesProvider, request: LLMRequest
):
    events = []
    async for event in provider.stream_text(request):
        events.append(event)
    return events


class FakeInvocation:
    def __init__(self, name: str, arguments: dict) -> None:
        self.name = name
        self.arguments = arguments

    def event_payload(self) -> dict:
        return {
            "ok": True,
            "tool_name": self.name,
            "openai_name": self.name,
            "arguments": self.arguments,
            "elapsed_ms": 1,
            "result_summary": '{"text":"file content"}',
        }

    def output_payload(self) -> dict:
        return {"ok": True, "tool_name": self.name, "result": {"text": "file content"}}


class FakeToolRuntime:
    def __init__(self) -> None:
        self.calls = []

    def list_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "standard_fs_read",
                "description": "Read file",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

    def list_tool_names(self) -> tuple[str, ...]:
        return ("standard.fs.read",)

    async def invoke_openai_tool(self, openai_name: str, arguments: dict) -> FakeInvocation:
        self.calls.append((openai_name, arguments))
        return FakeInvocation(openai_name, arguments)


class FakeWebInvocation:
    def event_payload(self) -> dict:
        return {
            "ok": True,
            "tool_name": "standard.web.search",
            "openai_name": "standard_web_search",
            "arguments": {"query": "HarnessDiff"},
            "elapsed_ms": 1,
            "result_summary": '{"results":[{"url":"https://example.test/source"}]}',
        }

    def output_payload(self) -> dict:
        return {
            "ok": True,
            "tool_name": "standard.web.search",
            "result": {
                "query": "HarnessDiff",
                "results": [
                    {
                        "title": "Example Source",
                        "url": "https://example.test/source",
                        "snippet": "A sourced result.",
                        "source": "Example",
                        "rank": 1,
                    }
                ],
            },
        }


class FakeWebToolRuntime:
    def list_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "standard_web_search",
                "description": "Search web",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

    def list_tool_names(self) -> tuple[str, ...]:
        return ("standard.web.search",)

    async def invoke_openai_tool(self, openai_name: str, arguments: dict) -> FakeWebInvocation:
        return FakeWebInvocation()


class FakeOpenAIClient:
    def __init__(self, streams: list[list[object]]) -> None:
        self.calls = []
        self.responses = FakeResponses(self, streams)


class FakeResponses:
    def __init__(self, client: FakeOpenAIClient, streams: list[list[object]]) -> None:
        self.client = client
        self.streams = streams

    def stream(self, **kwargs):
        self.client.calls.append(kwargs)
        return FakeStream(self.streams.pop(0))


class FakeStream:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def __aiter__(self):
        self._iter = iter(self.events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc
