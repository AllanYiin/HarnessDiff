from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.services.subagent_definitions import DEFAULT_SUBAGENTS
from app.services.subagent_runtime import (
    SUBAGENT_OPENAI_NAME,
    SUBAGENT_TOOL_NAME,
    SubagentToolRuntime,
    subagent_openai_tool_for_definitions,
)
from app.services.container_code_runtime import CONTAINER_CODE_TOOL_NAME
from app.services.pdf_attachments import PdfAttachmentToolRuntime
from app.services.skill_routing_review import (
    SKILL_ROUTING_REVIEW_OPENAI_NAME,
    SKILL_ROUTING_REVIEW_TOOL_NAME,
    SkillRoutingReviewRuntime,
)
from app.services.skill_resource_runtime import (
    SKILL_RESOURCE_TOOL_NAMES,
    SkillResourceRuntime,
)
from app.services.tool_runtime import (
    ToolAnythingRuntime,
    _elapsed_ms,
    _estimated_tool_token_usage,
    _json_summary,
)


PARALLEL_TOOL_NAME = "multi_tool_use.parallel"
PARALLEL_OPENAI_NAME = "multi_tool_use_parallel"
TOOL_NAME_PRIORITY: tuple[str, ...] = ("standard.shell.bash", CONTAINER_CODE_TOOL_NAME)


@dataclass(frozen=True)
class ParallelToolInvocationRecord:
    ok: bool
    name: str
    openai_name: str
    arguments: dict[str, Any]
    elapsed_ms: int
    results: list[dict[str, Any]]
    error: dict[str, Any] | None = None

    def output_payload(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "tool_name": self.name, "results": self.results}
        return {"ok": False, "tool_name": self.name, "error": self.error or {}}

    def event_payload(self) -> dict[str, Any]:
        output_payload = self.output_payload()
        payload = {
            "ok": self.ok,
            "tool_name": self.name,
            "openai_name": self.openai_name,
            "arguments": self.arguments,
            "elapsed_ms": self.elapsed_ms,
            "token_usage": _estimated_tool_token_usage(self.arguments, output_payload),
        }
        if self.ok:
            payload["result_summary"] = _json_summary({"results": self.results})
        else:
            payload["error"] = self.error or {}
        return payload


class ChatToolRuntime:
    def __init__(
        self,
        *,
        standard_runtime: ToolAnythingRuntime,
        subagent_runtime: SubagentToolRuntime,
        excluded_tool_names: tuple[str, ...] = (),
        include_subagent: bool = True,
        include_parallel: bool = True,
        pdf_runtime: PdfAttachmentToolRuntime | None = None,
        skill_routing_review_runtime: SkillRoutingReviewRuntime | None = None,
        skill_resource_runtime: SkillResourceRuntime | None = None,
    ) -> None:
        self.standard_runtime = standard_runtime
        self.subagent_runtime = subagent_runtime
        self.excluded_tool_names = set(excluded_tool_names)
        self.include_subagent = include_subagent
        self.include_parallel = include_parallel
        self.pdf_runtime = pdf_runtime
        self.skill_routing_review_runtime = skill_routing_review_runtime
        self.skill_resource_runtime = skill_resource_runtime

    def list_openai_tools(self) -> list[dict[str, Any]]:
        tools = _prioritize_openai_tools(
            [
                tool
                for tool in self.standard_runtime.list_openai_tools()
                if self.standard_runtime.from_openai_name(str(tool.get("name") or ""))
                not in self.excluded_tool_names
            ],
            self.standard_runtime,
        )
        if self.pdf_runtime is not None:
            tools.extend(self.pdf_runtime.list_openai_tools())
        if self.include_subagent:
            definitions = getattr(self.subagent_runtime, "definitions", DEFAULT_SUBAGENTS)
            tools.append(subagent_openai_tool_for_definitions(definitions))
        if self.include_parallel:
            tools.append(parallel_openai_tool())
        if self.skill_routing_review_runtime is not None:
            tools.extend(self.skill_routing_review_runtime.list_openai_tools())
        if self.skill_resource_runtime is not None:
            tools.extend(self.skill_resource_runtime.list_openai_tools())
        return tools

    def list_tool_names(self) -> tuple[str, ...]:
        names = _prioritize_tool_names(
            [
                name
                for name in self.standard_runtime.list_tool_names()
                if name not in self.excluded_tool_names
            ]
        )
        if self.pdf_runtime is not None:
            names.extend(self.pdf_runtime.list_tool_names())
        if self.include_subagent:
            names.append(SUBAGENT_TOOL_NAME)
        if self.include_parallel:
            names.append(PARALLEL_TOOL_NAME)
        if self.skill_routing_review_runtime is not None:
            names.extend(self.skill_routing_review_runtime.list_tool_names())
        if self.skill_resource_runtime is not None:
            names.extend(self.skill_resource_runtime.list_tool_names())
        return tuple(names)

    async def invoke_openai_tool(self, openai_name: str, arguments: dict[str, Any]) -> Any:
        if (
            self.skill_resource_runtime is not None
            and self.skill_resource_runtime.from_openai_name(openai_name)
            in SKILL_RESOURCE_TOOL_NAMES
        ):
            return await self.skill_resource_runtime.invoke_openai_tool(openai_name, arguments)
        if openai_name in {SKILL_ROUTING_REVIEW_OPENAI_NAME, SKILL_ROUTING_REVIEW_TOOL_NAME}:
            if self.skill_routing_review_runtime is None:
                return _tool_not_allowed(
                    openai_name, SKILL_ROUTING_REVIEW_TOOL_NAME, arguments
                )
            return await self.skill_routing_review_runtime.invoke_openai_tool(
                openai_name, arguments
            )
        if openai_name in {PARALLEL_OPENAI_NAME, PARALLEL_TOOL_NAME}:
            return await self._invoke_parallel(arguments)
        if openai_name in {SUBAGENT_OPENAI_NAME, SUBAGENT_TOOL_NAME}:
            if not self.include_subagent:
                return _tool_not_allowed(openai_name, SUBAGENT_TOOL_NAME, arguments)
            return await self.subagent_runtime.invoke(openai_name, arguments)
        if self.pdf_runtime is not None and self.pdf_runtime.from_openai_name(openai_name):
            return await self.pdf_runtime.invoke_openai_tool(openai_name, arguments)
        original_name = self.standard_runtime.from_openai_name(openai_name)
        if original_name in self.excluded_tool_names:
            return _tool_not_allowed(openai_name, original_name, arguments)
        return await self.standard_runtime.invoke_openai_tool(openai_name, arguments)

    async def _invoke_parallel(self, arguments: dict[str, Any]) -> ParallelToolInvocationRecord:
        started = time.perf_counter()
        if not self.include_parallel:
            return ParallelToolInvocationRecord(
                ok=False,
                name=PARALLEL_TOOL_NAME,
                openai_name=PARALLEL_OPENAI_NAME,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                results=[],
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool is not enabled for HarnessDiff: {PARALLEL_TOOL_NAME}",
                },
            )
        tool_uses = arguments.get("tool_uses")
        if not isinstance(tool_uses, list) or not tool_uses:
            return ParallelToolInvocationRecord(
                ok=False,
                name=PARALLEL_TOOL_NAME,
                openai_name=PARALLEL_OPENAI_NAME,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                results=[],
                error={
                    "type": "invalid_arguments",
                    "message": "tool_uses must be a non-empty list.",
                },
            )
        tasks = [
            self._invoke_parallel_item(index, item)
            for index, item in enumerate(tool_uses[:8])
        ]
        return ParallelToolInvocationRecord(
            ok=True,
            name=PARALLEL_TOOL_NAME,
            openai_name=PARALLEL_OPENAI_NAME,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            results=await asyncio.gather(*tasks),
        )

    async def _invoke_parallel_item(self, index: int, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {
                "index": index,
                "ok": False,
                "error": {"type": "invalid_tool_use", "message": "tool use must be an object."},
            }
        recipient_name = str(
            item.get("recipient_name")
            or item.get("openai_name")
            or item.get("tool_name")
            or ""
        )
        if recipient_name in {PARALLEL_OPENAI_NAME, PARALLEL_TOOL_NAME}:
            return {
                "index": index,
                "recipient_name": recipient_name,
                "ok": False,
                "error": {
                    "type": "tool_not_allowed",
                    "message": "multi_tool_use.parallel cannot call itself.",
                },
            }
        parameters = item.get("parameters", item.get("arguments", {}))
        if not isinstance(parameters, dict):
            parameters = {}
        invocation = await self.invoke_openai_tool(recipient_name, parameters)
        payload = invocation.output_payload()
        payload["index"] = index
        payload["recipient_name"] = recipient_name
        return payload


def parallel_openai_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PARALLEL_OPENAI_NAME,
        "description": (
            "Call multiple currently allowed HarnessDiff tools concurrently. Use this "
            "only when the requested tool calls are independent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_uses": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "recipient_name": {
                                "type": "string",
                                "description": (
                                    "OpenAI function name such as standard_fs_grep, "
                                    "or canonical tool name such as standard.fs.grep."
                                ),
                            },
                            "parameters": {
                                "type": "object",
                                "description": "Arguments for the target tool.",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["recipient_name", "parameters"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["tool_uses"],
            "additionalProperties": False,
        },
    }


def _tool_not_allowed(openai_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    return ParallelToolInvocationRecord(
        ok=False,
        name=tool_name,
        openai_name=openai_name,
        arguments=arguments,
        elapsed_ms=0,
        results=[],
        error={
            "type": "tool_not_allowed",
            "message": f"Tool is not enabled for HarnessDiff: {tool_name}",
        },
    )


def _prioritize_openai_tools(
    tools: list[dict[str, Any]], standard_runtime: ToolAnythingRuntime
) -> list[dict[str, Any]]:
    return [
        tool
        for _, tool in sorted(
            enumerate(tools),
            key=lambda item: _tool_sort_key(
                item[0],
                standard_runtime.from_openai_name(str(item[1].get("name") or "")),
            ),
        )
    ]


def _prioritize_tool_names(names: list[str]) -> list[str]:
    return [
        name
        for _, name in sorted(
            enumerate(names),
            key=lambda item: _tool_sort_key(item[0], item[1]),
        )
    ]


def _tool_sort_key(index: int, tool_name: str) -> tuple[int, int, int]:
    try:
        priority = TOOL_NAME_PRIORITY.index(tool_name)
    except ValueError:
        priority = len(TOOL_NAME_PRIORITY)
    return (priority, 0 if priority < len(TOOL_NAME_PRIORITY) else 1, index)
