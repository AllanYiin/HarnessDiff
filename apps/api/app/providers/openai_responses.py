from __future__ import annotations

import os
import json
from collections.abc import AsyncIterator
from typing import Any

from app.providers.base import LLMProvider, LLMRequest, ProviderConfigurationError, ProviderEvent

DEFAULT_MAX_TOOL_ROUNDS = 16
WEB_TOOL_NAMES = {
    "standard.web.search",
    "standard.web.fetch",
    "standard.web.extract_text",
    "standard.web.extract_links",
}


class OpenAIResponsesProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client_factory: Any | None = None,
        max_tool_rounds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.client_factory = client_factory
        self.max_tool_rounds = (
            max_tool_rounds
            if max_tool_rounds is not None
            else _max_tool_rounds_from_env()
        )

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        if not self.api_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is required for OpenAI streaming.")

        client = self._build_client()
        sequence = 0
        input_override = _initial_input_items(request) if request.tools_enabled else None
        previous_response_id: str | None = None
        tool_round = 0

        while True:
            tools = (
                request.tool_context.list_openai_tools()
                if request.tools_enabled and request.tool_context is not None
                else None
            )
            create_kwargs = _build_stream_kwargs(
                request,
                input_override=input_override,
                tools=tools,
                previous_response_id=previous_response_id,
            )
            completed_event: Any | None = None
            completed_response: Any | None = None

            async with client.responses.stream(**create_kwargs) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", "")
                    if event_type == "response.created":
                        response = getattr(event, "response", None)
                        yield ProviderEvent(
                            type="created",
                            profile_id=request.profile_id,
                            profile_label=request.profile_label,
                            sequence=sequence,
                            subagent_id=request.subagent_id,
                            subagent_label=request.subagent_label,
                            parent_profile_id=request.parent_profile_id,
                            response_id=getattr(response, "id", None),
                            raw=_to_dict(event),
                        )
                    elif event_type == "response.output_text.delta":
                        sequence += 1
                        yield ProviderEvent(
                            type="delta",
                            profile_id=request.profile_id,
                            profile_label=request.profile_label,
                            sequence=sequence,
                            text=getattr(event, "delta", ""),
                            subagent_id=request.subagent_id,
                            subagent_label=request.subagent_label,
                            parent_profile_id=request.parent_profile_id,
                            raw=_to_dict(event),
                        )
                    elif event_type == "response.completed":
                        completed_event = event
                        completed_response = getattr(event, "response", None)
                    elif event_type == "error":
                        raw = _to_dict(event)
                        yield ProviderEvent(
                            type="error",
                            profile_id=request.profile_id,
                            profile_label=request.profile_label,
                            sequence=sequence + 1,
                            message=_error_message_from_event(raw),
                            subagent_id=request.subagent_id,
                            subagent_label=request.subagent_label,
                            parent_profile_id=request.parent_profile_id,
                            raw=raw,
                        )

            function_calls = _function_calls(completed_response)
            if (
                not request.tools_enabled
                or request.tool_context is None
                or not function_calls
            ):
                if completed_event is not None:
                    yield ProviderEvent(
                        type="completed",
                        profile_id=request.profile_id,
                        profile_label=request.profile_label,
                        sequence=sequence + 1,
                        subagent_id=request.subagent_id,
                        subagent_label=request.subagent_label,
                        parent_profile_id=request.parent_profile_id,
                        response_id=getattr(completed_response, "id", None),
                        usage=_extract_usage(completed_response),
                        raw=_to_dict(completed_event),
                    )
                return

            if tool_round >= self.max_tool_rounds:
                message = (
                    "工具迴圈超過上限：模型仍持續要求呼叫工具，"
                    f"已在 {self.max_tool_rounds} 輪後停止。"
                )
                yield ProviderEvent(
                    type="error",
                    profile_id=request.profile_id,
                    profile_label=request.profile_label,
                    sequence=sequence + 1,
                    message=message,
                    subagent_id=request.subagent_id,
                    subagent_label=request.subagent_label,
                    parent_profile_id=request.parent_profile_id,
                    raw={
                        "type": "tool_round_limit_exceeded",
                        "max_tool_rounds": self.max_tool_rounds,
                        "message": message,
                    },
                )
                if completed_event is not None:
                    yield ProviderEvent(
                        type="completed",
                        profile_id=request.profile_id,
                        profile_label=request.profile_label,
                        sequence=sequence + 1,
                        subagent_id=request.subagent_id,
                        subagent_label=request.subagent_label,
                        parent_profile_id=request.parent_profile_id,
                        response_id=getattr(completed_response, "id", None),
                        usage=_extract_usage(completed_response),
                        raw=_to_dict(completed_event),
                    )
                return

            tool_round += 1
            previous_response_id = getattr(completed_response, "id", None)
            next_input: list[dict[str, Any]] = []
            for call in function_calls:
                invocation = await request.tool_context.invoke_openai_tool(
                    call["name"],
                    call["arguments"],
                )
                yield ProviderEvent(
                    type="tool_call",
                    profile_id=request.profile_id,
                    profile_label=request.profile_label,
                    sequence=sequence + 1,
                    subagent_id=request.subagent_id,
                    subagent_label=request.subagent_label,
                    parent_profile_id=request.parent_profile_id,
                    raw=invocation.event_payload(),
                )
                next_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(
                            _function_call_output_payload(invocation),
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
            input_override = next_input

    def _build_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory()
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ProviderConfigurationError("The openai package is required.") from exc
        return AsyncOpenAI(api_key=self.api_key)


def _max_tool_rounds_from_env(default: int = DEFAULT_MAX_TOOL_ROUNDS) -> int:
    raw = os.environ.get("HARNESSDIFF_MAX_TOOL_ROUNDS")
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _build_stream_kwargs(
    request: LLMRequest,
    *,
    input_override: Any | None = None,
    tools: list[dict[str, Any]] | None = None,
    previous_response_id: str | None = None,
) -> dict[str, Any]:
    input_payload: Any
    if input_override is not None:
        input_payload = input_override
    elif request.conversation_messages:
        input_payload = [
            *request.conversation_messages,
            {"role": "user", "content": request.prompt},
        ]
    else:
        input_payload = request.prompt
    create_kwargs: dict[str, Any] = {
        "model": request.model,
        "instructions": request.instructions,
        "input": input_payload,
    }
    if request.reasoning_effort:
        create_kwargs["reasoning"] = {"effort": request.reasoning_effort}
    if tools:
        create_kwargs["tools"] = tools
    if previous_response_id:
        create_kwargs["previous_response_id"] = previous_response_id
    return create_kwargs


def _initial_input_items(request: LLMRequest) -> list[dict[str, Any]]:
    if request.conversation_messages:
        return [*request.conversation_messages, {"role": "user", "content": request.prompt}]
    return [{"role": "user", "content": request.prompt}]


def _function_call_output_payload(invocation: Any) -> dict[str, Any]:
    payload = invocation.output_payload()
    if not isinstance(payload, dict) or not payload.get("ok"):
        return payload

    tool_name = str(payload.get("tool_name") or getattr(invocation, "name", ""))
    if tool_name not in WEB_TOOL_NAMES:
        return payload

    sources = _citation_sources_from_tool_payload(payload)
    if not sources:
        return payload

    enriched = dict(payload)
    enriched["citation_sources"] = sources
    enriched["citation_guidance"] = {
        "required": True,
        "style": (
            "Cite web-supported claims with inline Markdown links and include a short "
            "'Sources' section with the cited titles and URLs."
        ),
        "source_scope": "Only cite URLs present in citation_sources or the tool result.",
    }
    return enriched


def _citation_sources_from_tool_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []

    tool_name = str(payload.get("tool_name") or "")
    sources: list[dict[str, Any]] = []
    if tool_name == "standard.web.search":
        results = result.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    _append_citation_source(sources, item)
    else:
        _append_citation_source(sources, result)
    return sources


def _append_citation_source(
    sources: list[dict[str, Any]],
    item: dict[str, Any],
) -> None:
    url = str(item.get("final_url") or item.get("url") or "").strip()
    if not url or any(source["url"] == url for source in sources):
        return
    source = {
        "url": url,
        "title": str(item.get("title") or item.get("source") or url).strip(),
    }
    for key in ("final_url", "source", "published_at", "rank"):
        value = item.get(key)
        if value not in (None, ""):
            source[key] = value
    sources.append(source)


def _function_calls(response: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in _response_output_items(response):
        if item.get("type") != "function_call":
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        calls.append(
            {
                "name": name,
                "call_id": str(item.get("call_id") or item.get("id") or name),
                "arguments": _decode_arguments(item.get("arguments")),
            }
        )
    return calls


def _response_output_items(response: Any) -> list[dict[str, Any]]:
    output = _get_value(response, "output") or []
    if not isinstance(output, list):
        return []
    items: list[dict[str, Any]] = []
    for item in output:
        data = _to_dict(item)
        if "repr" in data and isinstance(item, dict):
            data = dict(item)
        if data:
            items.append(data)
    return items


def _decode_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return _jsonable(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
            if isinstance(dumped, dict):
                return _jsonable(dumped)
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            dumped = value.to_dict()
            if isinstance(dumped, dict):
                return _jsonable(dumped)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        data = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        if data:
            return _jsonable(data)
    return {"repr": repr(value)}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            key: _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)


def _error_message_from_event(raw: dict[str, Any]) -> str:
    error = raw.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message
    message = raw.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return "OpenAI Responses stream returned an error event."


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

    input_details = raw.get("input_tokens_details") or {}
    output_details = raw.get("output_tokens_details") or {}
    return {
        "input_tokens": _as_int(raw.get("input_tokens")),
        "cached_tokens": _as_int(input_details.get("cached_tokens")),
        "output_tokens": _as_int(raw.get("output_tokens")),
        "reasoning_tokens": _as_int(output_details.get("reasoning_tokens")),
        "total_tokens": _as_int(raw.get("total_tokens")),
        "provider_raw_usage": raw,
    }


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
