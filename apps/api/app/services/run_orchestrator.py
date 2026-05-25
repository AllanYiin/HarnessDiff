from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.models.project import utc_now_iso
from app.models.run import RunDocument, RunStatus
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent
from app.services.analysis_builder import build_run_analysis
from app.services.chat_tool_runtime import ChatToolRuntime
from app.services.context_builder import build_instructions
from app.services.harnessable_control import HarnessableControlPlane
from app.services.skill_store import SkillStore
from app.services.subagent_runtime import SubagentToolRuntime
from app.services.tool_runtime import ToolAnythingRuntime
from app.storage.json_io import write_json_atomic
from app.storage.project_store import ProjectStore


logger = logging.getLogger(__name__)

NO_HARNESS_EXCLUDED_TOOL_NAMES: tuple[str, ...] = ("standard.shell.bash",)


class RunOrchestrator:
    def __init__(
        self,
        store: ProjectStore,
        provider: LLMProvider,
        tool_runtime: ToolAnythingRuntime | None = None,
        control_plane: HarnessableControlPlane | None = None,
        skill_store: SkillStore | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.tool_runtime = tool_runtime
        self.control_plane = control_plane or HarnessableControlPlane()
        self.skill_store = skill_store

    async def stream_run(self, run: RunDocument) -> AsyncIterator[dict[str, Any]]:
        self.store.update_run_status(run.project_id, run.id, RunStatus.running)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        profile_errors: list[dict[str, Any]] = []

        async def run_profile(profile) -> None:
            try:
                instructions = build_instructions(profile.label, profile.harness_modules)
                if run.turn_index == 0 and self.skill_store is not None:
                    skill_context = self.skill_store.context_manifest()
                    if skill_context:
                        instructions = f"{instructions}\n\n{skill_context}"
                conversation_messages = self.store.read_profile_conversation_messages(
                    run.project_id, profile.id, run.turn_index
                )
                has_full_tools = bool(profile.harness_modules.get("tool_policy", False))
                active_tool_runtime = (
                    ChatToolRuntime(
                        standard_runtime=self.tool_runtime,
                        subagent_runtime=SubagentToolRuntime(
                            provider=self.provider,
                            store=self.store,
                            run=run,
                            profile=profile,
                        ),
                        excluded_tool_names=()
                        if has_full_tools
                        else NO_HARNESS_EXCLUDED_TOOL_NAMES,
                        include_subagent=has_full_tools,
                        include_parallel=has_full_tools,
                    )
                    if self.tool_runtime is not None
                    else None
                )
                tool_names = (
                    active_tool_runtime.list_tool_names()
                    if active_tool_runtime is not None
                    else ()
                )
                self.store.prepare_profile_run(
                    run.project_id,
                    run.id,
                    profile.id,
                    profile.label,
                    run.prompt,
                    instructions,
                    profile.harness_modules,
                    conversation_messages,
                    tool_names,
                )
                gate = self.control_plane.evaluate_before_provider(run, profile, instructions)
                for sequence, decision in enumerate(gate.decisions):
                    self.store.append_harness_decision_event(
                        run.project_id, run.id, profile.id, sequence, decision
                    )
                if not gate.allowed:
                    blocking = gate.blocking_decision or {}
                    error_payload = {
                        "run_id": run.id,
                        "profile_id": profile.id,
                        "profile_label": profile.label,
                        "type": "error",
                        "message": "Harnessable blocked provider call.",
                        "retryable": False,
                        "sequence": 0,
                        "harness_decision": blocking,
                    }
                    self.store.append_error_event(run.project_id, run.id, profile.id, error_payload)
                    await queue.put(error_payload)
                    return
                request = LLMRequest(
                    profile_id=profile.id,
                    profile_label=profile.label,
                    model=run.model,
                    reasoning_effort=run.reasoning_effort,
                    instructions=instructions,
                    prompt=run.prompt,
                    conversation_messages=conversation_messages,
                    tools_enabled=active_tool_runtime is not None,
                    tool_context=active_tool_runtime,
                )
                async for event in self.provider.stream_text(request):
                    self.store.append_profile_event(run.project_id, run.id, profile.id, event)
                    if event.type == "delta":
                        self.store.append_profile_output_delta(
                            run.project_id, run.id, profile.id, event.text or ""
                        )
                    elif event.type == "error":
                        logger.error(
                            "Provider stream error for run %s profile %s: %s raw=%s",
                            run.id,
                            profile.id,
                            event.message or "no message",
                            event.raw,
                        )
                    elif event.type == "completed" and event.usage is not None:
                        self.store.write_profile_usage(
                            run.project_id, run.id, profile.id, profile.label, event.usage
                        )
                    await queue.put(_event_to_payload(run.id, event))
            except Exception as exc:  # Provider errors must not kill the other profiles.
                logger.exception(
                    "Provider execution failed for run %s profile %s",
                    run.id,
                    profile.id,
                )
                error_payload = {
                    "run_id": run.id,
                    "profile_id": profile.id,
                    "profile_label": profile.label,
                    "type": "error",
                    "message": str(exc),
                    "retryable": True,
                    "sequence": 0,
                }
                profile_errors.append(error_payload)
                self.store.append_error_event(run.project_id, run.id, profile.id, error_payload)
                await queue.put(error_payload)
            finally:
                await queue.put({"run_id": run.id, "profile_id": profile.id, "type": "profile_done"})

        tasks = [asyncio.create_task(run_profile(profile)) for profile in run.profiles]
        remaining = len(tasks)
        try:
            while remaining:
                payload = await queue.get()
                if payload["type"] == "profile_done":
                    remaining -= 1
                    continue
                yield payload
            await asyncio.gather(*tasks)
            if profile_errors:
                self.store.update_run_status(run.project_id, run.id, RunStatus.failed)
                yield {"run_id": run.id, "type": "run_failed", "errors": profile_errors}
                return
            self.store.update_run_status(run.project_id, run.id, RunStatus.completed)
            analysis = build_run_analysis(
                run,
                self.store.get_run_dir(run.project_id, run.id),
                self.store.list_run_dirs(run.project_id),
            )
            self.store.write_run_analysis(
                run.project_id, run.id, analysis.model_dump(mode="json")
            )
            yield {
                "run_id": run.id,
                "type": "analysis_ready",
                "analysis": analysis.model_dump(mode="json"),
            }
            yield {"run_id": run.id, "type": "run_completed"}
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            self.store.update_run_status(run.project_id, run.id, RunStatus.cancelled)
            raise


def sse_encode(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_to_payload(run_id: str, event: ProviderEvent) -> dict[str, Any]:
    payload = {
        "run_id": run_id,
        "profile_id": event.profile_id,
        "profile_label": event.profile_label,
        "type": event.type,
        "text": event.text,
        "message": event.message,
        "subagent_id": event.subagent_id,
        "subagent_label": event.subagent_label,
        "parent_profile_id": event.parent_profile_id,
        "sequence": event.sequence,
        "response_id": event.response_id,
        "usage": event.usage,
    }
    if event.type == "tool_call":
        payload["tool_call"] = event.raw
    return payload
