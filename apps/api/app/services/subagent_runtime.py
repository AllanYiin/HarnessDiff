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
from app.services.tool_runtime import _elapsed_ms, _json_summary, _truncate_jsonable
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
        payload = {
            "ok": self.ok,
            "tool_name": self.name,
            "openai_name": self.openai_name,
            "arguments": _truncate_jsonable(self.arguments),
            "elapsed_ms": self.elapsed_ms,
            "subagent_id": self.subagent_id,
            "subagent_label": self.subagent_label,
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
    ) -> None:
        self.provider = provider
        self.store = store
        self.run = run
        self.profile = profile
        self.definitions = definitions

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

        prompt = _subagent_prompt(task, context)
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
            tools_enabled=False,
            tool_context=None,
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


def _subagent_prompt(task: str, context: str) -> str:
    context_text = context if context else "(no additional context provided)"
    return (
        "Delegated task:\n"
        f"{task}\n\n"
        "Context supplied by manager:\n"
        f"{context_text}\n\n"
        "Return only the result the manager needs. Do not call tools."
    )


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


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
