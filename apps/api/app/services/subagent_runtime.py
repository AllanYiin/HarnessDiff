from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.models.run import ProfileConfig, RunDocument
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent
from app.services.subagent_definitions import (
    DEFAULT_SUBAGENTS,
    SubagentDefinition,
    enabled_subagents,
    subagent_by_id,
)
from app.services.tool_runtime import ToolInvocationRecord
from app.services.tool_runtime import _elapsed_ms, _json_summary, _truncate_jsonable
from app.services.tool_runtime import _estimated_tool_token_usage
from app.services.tool_runtime import ToolAnythingRuntime
from app.storage.project_store import ProjectStore

SUBAGENT_TOOL_NAME = "harness.subagent.run"
SUBAGENT_OPENAI_NAME = "harness_subagent_run"


@dataclass(frozen=True)
class SubagentToolInvocationRecord:
    ok: bool
    name: str
    openai_name: str
    arguments: dict[str, Any]
    elapsed_ms: int
    subagent_id: str | None = None
    subagent_label: str | None = None
    text: str = ""
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def output_payload(self) -> dict[str, Any]:
        if self.ok:
            return {
                "ok": True,
                "tool_name": self.name,
                "subagent_id": self.subagent_id,
                "subagent_label": self.subagent_label,
                "text": self.text,
                "usage": self.usage,
            }
        return {
            "ok": False,
            "tool_name": self.name,
            "subagent_id": self.subagent_id,
            "subagent_label": self.subagent_label,
            "error": self.error or {},
        }

    def event_payload(self) -> dict[str, Any]:
        output_payload = self.output_payload()
        payload = {
            "ok": self.ok,
            "tool_name": self.name,
            "openai_name": self.openai_name,
            "arguments": _truncate_jsonable(self.arguments),
            "elapsed_ms": self.elapsed_ms,
            "subagent_id": self.subagent_id,
            "subagent_label": self.subagent_label,
            "token_usage": _provider_or_estimated_usage(
                self.usage, self.arguments, output_payload
            ),
        }
        if self.ok:
            payload["result_summary"] = _json_summary(
                {"text": self.text, "usage": self.usage}
            )
        else:
            payload["error"] = self.error or {}
        return payload


class SubagentToolRuntime:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        store: ProjectStore,
        run: RunDocument,
        profile: ProfileConfig,
        definitions: tuple[SubagentDefinition, ...] = DEFAULT_SUBAGENTS,
        standard_runtime: ToolAnythingRuntime | None = None,
        excluded_tool_names: tuple[str, ...] = (),
    ) -> None:
        self.provider = provider
        self.store = store
        self.run = run
        self.profile = profile
        self.definitions = definitions
        self.standard_runtime = standard_runtime
        self.excluded_tool_names = set(excluded_tool_names)

    async def invoke(
        self, openai_name: str, arguments: dict[str, Any]
    ) -> SubagentToolInvocationRecord:
        started = time.perf_counter()
        subagent_id = str(arguments.get("subagent_id") or "").strip()
        task = str(arguments.get("task") or "").strip()
        context = str(arguments.get("context") or "").strip()
        definition = subagent_by_id(subagent_id, self.definitions)
        if definition is None:
            return self._error(
                started,
                openai_name,
                arguments,
                subagent_id=subagent_id or None,
                error_type="subagent_not_allowed",
                message=f"Subagent is not enabled for HarnessDiff: {subagent_id}",
            )
        if not task:
            return self._error(
                started,
                openai_name,
                arguments,
                subagent_id=definition.id,
                subagent_label=definition.label,
                error_type="invalid_subagent_task",
                message="Subagent task is required.",
            )

        tool_context = self._tool_context_for(definition)
        prompt = _subagent_prompt(
            task,
            context,
            definition,
            tools_enabled=tool_context is not None,
        )
        self.store.prepare_subagent_run(
            self.run.project_id,
            self.run.id,
            self.profile.id,
            self.profile.label,
            definition.id,
            definition.label,
            prompt,
            definition.instructions,
            definition.model,
            definition.reasoning_effort,
        )
        request = LLMRequest(
            profile_id=self.profile.id,
            profile_label=self.profile.label,
            model=definition.model,
            reasoning_effort=definition.reasoning_effort,
            instructions=definition.instructions,
            prompt=prompt,
            tools_enabled=tool_context is not None,
            tool_context=tool_context,
            subagent_id=definition.id,
            subagent_label=definition.label,
            parent_profile_id=self.profile.id,
        )
        text_parts: list[str] = []
        usage: dict[str, Any] | None = None
        error_event: ProviderEvent | None = None
        try:
            async for event in self.provider.stream_text(request):
                event = _with_subagent_identity(event, definition, self.profile)
                self.store.append_subagent_event(
                    self.run.project_id, self.run.id, self.profile.id, definition.id, event
                )
                if event.type == "delta":
                    delta = event.text or ""
                    text_parts.append(delta)
                    self.store.append_subagent_output_delta(
                        self.run.project_id,
                        self.run.id,
                        self.profile.id,
                        definition.id,
                        delta,
                    )
                elif event.type == "completed" and event.usage is not None:
                    usage = event.usage
                    self.store.write_subagent_usage(
                        self.run.project_id,
                        self.run.id,
                        self.profile.id,
                        definition.id,
                        definition.label,
                        event.usage,
                    )
                elif event.type == "error":
                    error_event = event
        except Exception as exc:
            error_payload = {
                "type": "error",
                "profile_id": self.profile.id,
                "profile_label": self.profile.label,
                "subagent_id": definition.id,
                "subagent_label": definition.label,
                "parent_profile_id": self.profile.id,
                "message": str(exc),
                "retryable": True,
                "sequence": 0,
            }
            self.store.append_subagent_error_event(
                self.run.project_id,
                self.run.id,
                self.profile.id,
                definition.id,
                error_payload,
            )
            return self._error(
                started,
                openai_name,
                arguments,
                subagent_id=definition.id,
                subagent_label=definition.label,
                error_type=exc.__class__.__name__,
                message=str(exc),
            )

        if error_event is not None:
            return self._error(
                started,
                openai_name,
                arguments,
                subagent_id=definition.id,
                subagent_label=definition.label,
                error_type=str(error_event.raw.get("type") or "subagent_provider_error"),
                message=error_event.message or "Subagent provider returned an error event.",
            )

        return SubagentToolInvocationRecord(
            ok=True,
            name=SUBAGENT_TOOL_NAME,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            subagent_id=definition.id,
            subagent_label=definition.label,
            text=_truncate_text("".join(text_parts), definition.max_output_chars),
            usage=usage,
        )

    def _error(
        self,
        started: float,
        openai_name: str,
        arguments: dict[str, Any],
        *,
        subagent_id: str | None = None,
        subagent_label: str | None = None,
        error_type: str,
        message: str,
    ) -> SubagentToolInvocationRecord:
        return SubagentToolInvocationRecord(
            ok=False,
            name=SUBAGENT_TOOL_NAME,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            subagent_id=subagent_id,
            subagent_label=subagent_label,
            error={"type": error_type, "message": message},
        )

    def _tool_context_for(self, definition: SubagentDefinition) -> "SubagentToolContext | None":
        if self.standard_runtime is None or not definition.tools:
            return None
        allowed = tuple(
            tool_name
            for tool_name in definition.tools
            if tool_name in self.standard_runtime.list_tool_names()
            and tool_name not in self.excluded_tool_names
        )
        if not allowed:
            return None
        return SubagentToolContext(
            standard_runtime=self.standard_runtime,
            allowed_tool_names=allowed,
        )


class SubagentToolContext:
    def __init__(
        self,
        *,
        standard_runtime: ToolAnythingRuntime,
        allowed_tool_names: tuple[str, ...],
    ) -> None:
        self.standard_runtime = standard_runtime
        self.allowed_tool_names = tuple(dict.fromkeys(allowed_tool_names))

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return [
            tool
            for tool in self.standard_runtime.list_openai_tools()
            if self.standard_runtime.from_openai_name(str(tool.get("name") or ""))
            in self.allowed_tool_names
        ]

    def list_tool_names(self) -> tuple[str, ...]:
        return self.allowed_tool_names

    async def invoke_openai_tool(self, openai_name: str, arguments: dict[str, Any]) -> Any:
        original_name = self.standard_runtime.from_openai_name(openai_name)
        if original_name not in self.allowed_tool_names:
            return _subagent_tool_not_allowed(openai_name, original_name, arguments)
        return await self.standard_runtime.invoke_openai_tool(openai_name, arguments)


def subagent_openai_tool() -> dict[str, Any]:
    return subagent_openai_tool_for_definitions(DEFAULT_SUBAGENTS)


def subagent_openai_tool_for_definitions(
    definitions: tuple[SubagentDefinition, ...]
) -> dict[str, Any]:
    ids = [definition.id for definition in enabled_subagents(definitions)]
    id_text = ", ".join(ids) if ids else "(none)"
    return {
        "type": "function",
        "name": SUBAGENT_OPENAI_NAME,
        "description": (
            "Delegate one focused task to a fixed HarnessDiff subagent and return "
            "the subagent's concise result to the manager."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subagent_id": {
                    "type": "string",
                    "description": f"One of: {id_text}.",
                },
                "task": {
                    "type": "string",
                    "description": "The specific task the subagent should answer.",
                },
                "context": {
                    "type": "string",
                    "description": "Relevant context for the delegated task.",
                },
            },
            "required": ["subagent_id", "task", "context"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _subagent_prompt(
    task: str,
    context: str,
    definition: SubagentDefinition,
    *,
    tools_enabled: bool,
) -> str:
    context_text = context if context else "(no additional context provided)"
    tool_text = _subagent_tool_prompt(definition) if tools_enabled else "Do not call tools."
    return (
        "Delegated task:\n"
        f"{task}\n\n"
        "Context supplied by manager:\n"
        f"{context_text}\n\n"
        f"{tool_text}\n\n"
        "Return only the result the manager needs."
    )


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _provider_or_estimated_usage(
    usage: dict[str, Any] | None,
    arguments: dict[str, Any],
    output_payload: dict[str, Any],
) -> dict[str, Any]:
    if usage:
        return {
            "source": "provider_reported",
            "input_tokens": _as_int(usage.get("input_tokens")),
            "cached_tokens": _as_int(usage.get("cached_tokens")),
            "output_tokens": _as_int(usage.get("output_tokens")),
            "reasoning_tokens": _as_int(usage.get("reasoning_tokens")),
            "total_tokens": _as_int(usage.get("total_tokens")),
        }
    return _estimated_tool_token_usage(arguments, output_payload)


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _subagent_tool_prompt(definition: SubagentDefinition) -> str:
    if "standard.web.search" in definition.tools:
        return (
            "Use the delegated web tools directly. Workflow:\n"
            "1. Derive exactly 5 distinct search query principles for the delegated task.\n"
            "2. Run one web search for each query principle.\n"
            "3. Merge and deduplicate candidate URLs before opening pages.\n"
            "4. Fetch only the unique, relevant URLs needed to answer the task.\n"
            "5. Produce concise notes grounded only in fetched/search result sources, with source URLs.\n"
            "Do not return raw search results, full page text, or long quotes."
        )
    return "Use only the delegated tools needed for this task."


def _subagent_tool_not_allowed(
    openai_name: str, tool_name: str, arguments: dict[str, Any]
) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        ok=False,
        name=tool_name,
        openai_name=openai_name,
        arguments=arguments,
        elapsed_ms=0,
        error={
            "type": "tool_not_allowed",
            "message": f"Tool is not enabled for this subagent: {tool_name}",
        },
    )


def _with_subagent_identity(
    event: ProviderEvent, definition: SubagentDefinition, profile: ProfileConfig
) -> ProviderEvent:
    if (
        event.subagent_id == definition.id
        and event.subagent_label == definition.label
        and event.parent_profile_id == profile.id
    ):
        return event
    return ProviderEvent(
        type=event.type,
        profile_id=event.profile_id,
        profile_label=event.profile_label,
        sequence=event.sequence,
        text=event.text,
        message=event.message,
        subagent_id=definition.id,
        subagent_label=definition.label,
        parent_profile_id=profile.id,
        response_id=event.response_id,
        usage=event.usage,
        raw=event.raw,
    )
