from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.project import utc_now_iso
from app.models.run import RunDocument, RunStatus
from app.providers.base import (
    LLMImageAttachment,
    LLMProvider,
    LLMRequest,
    ProviderEvent,
    SkillSelectionRequest,
)
from app.services.analysis_builder import build_run_analysis
from app.services.chat_tool_runtime import ChatToolRuntime
from app.services.chat_tool_runtime import PARALLEL_TOOL_NAME
from app.services.container_code_runtime import CONTAINER_CODE_TOOL_NAME
from app.services.context_builder import build_instructions
from app.services.harnessable_control import HarnessableControlPlane
from app.services.pdf_attachments import PdfAttachmentToolRuntime, build_pdf_context_prompt
from app.services.skill_store import REQUESTED_SKILL_DETAILS_MARKER, SkillStore
from app.services.subagent_definitions import DEFAULT_SUBAGENTS
from app.services.subagent_runtime import SUBAGENT_TOOL_NAME, SubagentToolRuntime
from app.services.tool_runtime import _estimate_text_tokens
from app.services.tool_runtime import ToolAnythingRuntime
from app.storage.json_io import write_json_atomic
from app.storage.project_store import ProjectStore


logger = logging.getLogger(__name__)

NO_HARNESS_EXCLUDED_TOOL_NAMES: tuple[str, ...] = (
    "standard.shell.bash",
    CONTAINER_CODE_TOOL_NAME,
)


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
        selected_skills = await self._select_skills_for_run(run)
        selected_skill_ids = tuple(skill.skill_id for skill in selected_skills)
        selected_skill_metadata = {skill.skill_id: skill.event_metadata() for skill in selected_skills}
        skill_token_usage = self._skill_token_usage(selected_skill_ids)
        run_dir = self.store.get_run_dir(run.project_id, run.id)

        async def run_profile(profile) -> None:
            try:
                instructions = build_instructions(profile.label, profile.harness_modules)
                has_harness_context = any(
                    bool(enabled) for enabled in profile.harness_modules.values()
                )
                pdf_context = build_pdf_context_prompt(
                    attachments=tuple(run.attachments),
                    run_dir=run_dir,
                    harness_mode=has_harness_context,
                )
                profile_prompt = f"{run.prompt}{pdf_context}".strip()
                if self.skill_store is not None:
                    if has_harness_context:
                        agents_context = self.skill_store.agents_context()
                        if agents_context:
                            instructions = f"{instructions}\n\n{agents_context}"
                    skill_context = self.skill_store.context_manifest()
                    if skill_context:
                        instructions = f"{instructions}\n\n{skill_context}"
                    auto_skill_context = self.skill_store.auto_skill_context(
                        run.prompt,
                        skill_ids=selected_skill_ids,
                    )
                    if auto_skill_context:
                        instructions = f"{instructions}\n\n{auto_skill_context}"
                conversation_messages = self.store.read_profile_conversation_messages(
                    run.project_id, profile.id, run.turn_index
                )
                has_full_tools = bool(profile.harness_modules.get("tool_policy", False))
                globally_excluded_tools = (
                    self.skill_store.disabled_or_deleted_tool_names()
                    if self.skill_store is not None
                    else ()
                )
                profile_excluded_tools = tuple(
                    dict.fromkeys(
                        (
                            *globally_excluded_tools,
                            *(() if has_full_tools else NO_HARNESS_EXCLUDED_TOOL_NAMES),
                        )
                    )
                )
                subagent_definitions = (
                    self.skill_store.subagent_definitions()
                    if self.skill_store is not None
                    else DEFAULT_SUBAGENTS
                )
                active_tool_runtime = (
                    ChatToolRuntime(
                        standard_runtime=self.tool_runtime,
                        subagent_runtime=SubagentToolRuntime(
                            provider=self.provider,
                            store=self.store,
                            run=run,
                            profile=profile,
                            definitions=subagent_definitions,
                            standard_runtime=self.tool_runtime,
                            excluded_tool_names=profile_excluded_tools,
                        ),
                        excluded_tool_names=profile_excluded_tools,
                        include_subagent=has_full_tools
                        and SUBAGENT_TOOL_NAME not in globally_excluded_tools,
                        include_parallel=has_full_tools
                        and PARALLEL_TOOL_NAME not in globally_excluded_tools,
                        pdf_runtime=PdfAttachmentToolRuntime(
                            run_dir=run_dir,
                            attachments=tuple(run.attachments),
                            mode="harness" if has_harness_context else "grep",
                        ),
                    )
                    if self.tool_runtime is not None
                    else None
                )
                tool_names = (
                    active_tool_runtime.list_tool_names()
                    if active_tool_runtime is not None
                    else ()
                )
                prompt_cache_key = _prompt_cache_key(run.project_id, profile.id)
                image_attachments = tuple(
                    LLMImageAttachment(
                        name=attachment.name,
                        mime_type=attachment.mime_type,
                        size_bytes=attachment.size_bytes,
                        image_url=attachment.image_url,
                        detail=attachment.detail,
                    )
                    for attachment in run.attachments
                    if attachment.kind == "image"
                )
                self.store.prepare_profile_run(
                    run.project_id,
                    run.id,
                    profile.id,
                    profile.label,
                    profile_prompt,
                    instructions,
                    profile.harness_modules,
                    conversation_messages,
                    tool_names,
                    image_attachments,
                    prompt_cache_key,
                )
                for sequence, skill_id in enumerate(selected_skill_ids):
                    token_usage = skill_token_usage.get(skill_id, {})
                    metadata = dict(selected_skill_metadata.get(skill_id, {}))
                    if metadata.get("required_tools"):
                        available_tools = set(tool_names)
                        missing_tools = [
                            tool
                            for tool in metadata["required_tools"]
                            if tool not in available_tools
                        ]
                        metadata["missing_required_tools"] = missing_tools
                    self.store.append_skill_invocation_event(
                        run.project_id,
                        run.id,
                        profile.id,
                        sequence,
                        skill_id,
                        token_usage=token_usage,
                        metadata=metadata,
                    )
                    await queue.put(
                        {
                            "run_id": run.id,
                            "profile_id": profile.id,
                            "profile_label": profile.label,
                            "type": "skill_invocation",
                            "sequence": sequence,
                            "skill_id": skill_id,
                            "status": "loaded",
                            "token_usage": token_usage,
                            "metadata": metadata,
                        }
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
                    prompt=profile_prompt,
                    image_attachments=image_attachments,
                    conversation_messages=conversation_messages,
                    prompt_cache_key=prompt_cache_key,
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

    async def _select_skills_for_run(self, run: RunDocument) -> tuple["SelectedSkill", ...]:
        if self.skill_store is None:
            return ()
        if REQUESTED_SKILL_DETAILS_MARKER in run.prompt:
            return ()
        candidates = self.skill_store.skill_selection_candidates()
        if not candidates:
            return ()
        explicit_ids = self.skill_store.explicit_skill_ids_for_prompt(run.prompt)
        fallback_activations = self.skill_store.select_skills_for_prompt(run.prompt)
        fallback_ids = tuple(activation.id for activation in fallback_activations)
        selection = await self.provider.select_skills(
            SkillSelectionRequest(
                model=run.model,
                prompt=run.prompt,
                skills=candidates,
                max_selected=3,
            )
        )
        if selection.source == "llm":
            selected_ids = _merge_selected_skill_ids(
                explicit_ids,
                selection.selected_skill_ids,
                fallback_ids,
                max_selected=3,
            )
            return self._selected_skill_metadata(
                selected_ids,
                explicit_ids=explicit_ids,
                llm_ids=selection.selected_skill_ids,
                fallback_activations=fallback_activations,
            )
        selected_ids = _merge_selected_skill_ids(explicit_ids, fallback_ids, max_selected=3)
        return self._selected_skill_metadata(
            selected_ids,
            explicit_ids=explicit_ids,
            llm_ids=(),
            fallback_activations=fallback_activations,
        )

    def _selected_skill_metadata(
        self,
        selected_ids: tuple[str, ...],
        *,
        explicit_ids: tuple[str, ...],
        llm_ids: tuple[str, ...],
        fallback_activations,
    ) -> tuple["SelectedSkill", ...]:
        if self.skill_store is None:
            return ()
        fallback_by_id = {activation.id: activation for activation in fallback_activations}
        selected: list[SelectedSkill] = []
        for skill_id in selected_ids:
            base_metadata = self.skill_store.skill_activation_metadata(skill_id)
            source = "selected"
            reason = ""
            score = 100
            if skill_id in explicit_ids:
                source = "explicit"
                reason = "user invoked the skill with $skill-id or /skill-id"
            elif skill_id in llm_ids:
                source = "llm"
                reason = "provider skill selector matched the current prompt"
            elif skill_id in fallback_by_id:
                activation = fallback_by_id[skill_id]
                source = activation.source
                reason = activation.reason
                score = activation.score
            selected.append(
                SelectedSkill(
                    skill_id=skill_id,
                    source=source,
                    reason=reason,
                    score=score,
                    load_policy=str(base_metadata.get("load_policy") or "auto"),
                    required_tools=tuple(base_metadata.get("required_tools") or ()),
                    allowed_tools=tuple(base_metadata.get("allowed_tools") or ()),
                    priority=int(base_metadata.get("priority") or 0),
                )
            )
        return tuple(selected)

    def _skill_token_usage(self, skill_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        if self.skill_store is None or not skill_ids:
            return {}
        usage: dict[str, dict[str, Any]] = {}
        for activation in self.skill_store.activations_for_skill_ids(skill_ids):
            input_tokens = _estimate_text_tokens(activation.content)
            usage[activation.id] = {
                "source": "estimated",
                "basis": "skill_md_characters_div_4",
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "total_tokens": input_tokens,
            }
        return usage


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


def _prompt_cache_key(project_id: str, profile_id: str) -> str:
    return f"harnessdiff:project:{project_id}:profile:{profile_id}"


@dataclass(frozen=True)
class SelectedSkill:
    skill_id: str
    source: str
    reason: str
    score: int
    load_policy: str
    required_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    priority: int

    def event_metadata(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reason": self.reason,
            "score": self.score,
            "load_policy": self.load_policy,
            "required_tools": list(self.required_tools),
            "allowed_tools": list(self.allowed_tools),
            "priority": self.priority,
        }


def _merge_selected_skill_ids(
    *skill_id_groups: tuple[str, ...],
    max_selected: int,
) -> tuple[str, ...]:
    selected: list[str] = []
    for skill_ids in skill_id_groups:
        for skill_id in skill_ids:
            if skill_id in selected:
                continue
            selected.append(skill_id)
            if len(selected) >= max_selected:
                return tuple(selected)
    return tuple(selected)
