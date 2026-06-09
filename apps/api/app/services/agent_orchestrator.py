from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.core.settings import settings
from app.models.agent import AgentStepEvent
from app.models.project import utc_now_iso
from app.models.run import RunDocument, RunStatus
from app.providers.base import LLMImageAttachment, LLMRequest, ProviderEvent
from app.services.chat_tool_runtime import ChatToolRuntime, PARALLEL_TOOL_NAME
from app.services.container_code_runtime import CONTAINER_CODE_TOOL_NAME
from app.services.context_builder import build_instructions
from app.services.execution_policy import (
    apply_execution_policy_instructions,
    build_code_execution_policy,
    execution_policy_task_text,
)
from app.services.agent_analysis_builder import build_agent_run_analysis
from app.services.pdf_attachments import PdfAttachmentToolRuntime, build_pdf_context_prompt
from app.services.run_orchestrator import (
    NO_HARNESS_EXCLUDED_TOOL_NAMES,
    RunOrchestrator,
    _event_to_payload,
    _profile_has_harness_context,
    _prompt_cache_key,
    _skill_selection_policy_for_profile,
    _tool_definition_token_estimate,
)
from app.services.subagent_definitions import DEFAULT_SUBAGENTS
from app.services.subagent_runtime import SUBAGENT_TOOL_NAME, SubagentToolRuntime
from app.services.skill_store import SKILL_METADATA_BUDGET_CHARS
from app.services.skill_routing_review import (
    SKILL_ROUTING_REVIEW_TOOL_NAME,
    SkillRoutingReviewRuntime,
)
from app.services.skill_resource_runtime import SkillResourceRuntime


logger = logging.getLogger(__name__)

AGENT_BASELINE_EXCLUDED_TOOL_NAMES: tuple[str, ...] = (
    *NO_HARNESS_EXCLUDED_TOOL_NAMES,
    "harness.subagent.run",
    "multi_tool_use.parallel",
)


class AgentRunOrchestrator(RunOrchestrator):
    async def stream_run(self, run: RunDocument) -> AsyncIterator[dict[str, Any]]:
        self.store.update_run_status(run.project_id, run.id, RunStatus.running)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        profile_errors: list[dict[str, Any]] = []
        run_dir = self.store.get_run_dir(run.project_id, run.id)
        profiles_ready_to_stream = asyncio.Event()

        async def run_profile(profile) -> None:
            profile_started = time.perf_counter()
            profile_prepared = False
            try:
                await self._record_step(
                    queue,
                    run,
                    profile,
                    sequence=0,
                    step_id="step_0000",
                    event_type="agent_step_started",
                    label="Prepare agent task",
                    status="running",
                )
                instructions = _agent_instructions(
                    build_instructions(profile.label, profile.harness_modules),
                    run,
                    profile.label,
                )
                has_harness_context = _profile_has_harness_context(profile)
                selected_skills = await self._select_skills_for_profile(run, profile)
                selected_skill_ids = tuple(skill.skill_id for skill in selected_skills)
                selected_skill_metadata = {
                    skill.skill_id: skill.event_metadata() for skill in selected_skills
                }
                skill_context_gate = self.control_plane.evaluate_skill_context_assembly(
                    run,
                    profile,
                    selection_policy=_skill_selection_policy_for_profile(profile),
                    candidate_count=len(self.skill_store.skill_selection_candidates())
                    if self.skill_store is not None
                    else 0,
                    selected_skills=selected_skills,
                    metadata_budget_chars=SKILL_METADATA_BUDGET_CHARS,
                )
                skill_token_usage = self._skill_token_usage(selected_skill_ids)
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
                            *(() if has_full_tools else AGENT_BASELINE_EXCLUDED_TOOL_NAMES),
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
                        skill_routing_review_runtime=(
                            SkillRoutingReviewRuntime(
                                skill_store=self.skill_store,
                                task_text=run.prompt,
                                selected_skill_ids=selected_skill_ids,
                            )
                            if has_full_tools
                            and self.skill_store is not None
                            and SKILL_ROUTING_REVIEW_TOOL_NAME not in globally_excluded_tools
                            else None
                        ),
                        skill_resource_runtime=(
                            SkillResourceRuntime(
                                skill_store=self.skill_store,
                                selected_skill_ids=selected_skill_ids,
                            )
                            if self.skill_store is not None and selected_skill_ids
                            else None
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
                tool_definition_tokens = _tool_definition_token_estimate(active_tool_runtime)
                execution_policy = build_code_execution_policy(
                    task_text=execution_policy_task_text(run.prompt, conversation_messages),
                    harness_modules=profile.harness_modules,
                    tool_names=tool_names,
                    surface="agent",
                )
                instructions = apply_execution_policy_instructions(
                    instructions, execution_policy
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
                    execution_policy,
                    tool_definition_tokens=tool_definition_tokens,
                )
                await self._record_step(
                    queue,
                    run,
                    profile,
                    sequence=1,
                    step_id="step_0000",
                    event_type="agent_step_completed",
                    label="Prepare agent task",
                    status="completed",
                    elapsed_ms=_elapsed_ms(profile_started),
                )
                decision_sequence = 0
                for sequence, decision in enumerate(skill_context_gate.decisions):
                    self.store.append_harness_decision_event(
                        run.project_id, run.id, profile.id, sequence, decision
                    )
                    decision_sequence = sequence + 1
                for sequence, skill_id in enumerate(selected_skill_ids):
                    token_usage = skill_token_usage.get(skill_id, {})
                    metadata = dict(selected_skill_metadata.get(skill_id, {}))
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

                await queue.put({"run_id": run.id, "profile_id": profile.id, "type": "profile_prepared"})
                profile_prepared = True
                await profiles_ready_to_stream.wait()

                gate = self.control_plane.evaluate_before_provider(run, profile, instructions)
                for sequence, decision in enumerate(gate.decisions):
                    self.store.append_harness_decision_event(
                        run.project_id, run.id, profile.id, decision_sequence + sequence, decision
                    )
                if not gate.allowed:
                    blocking = gate.blocking_decision or {}
                    error_payload = {
                        "run_id": run.id,
                        "profile_id": profile.id,
                        "profile_label": profile.label,
                        "type": "error",
                        "message": "Harnessable blocked agent provider call.",
                        "retryable": False,
                        "sequence": 0,
                        "harness_decision": blocking,
                    }
                    profile_errors.append(error_payload)
                    self.store.append_error_event(run.project_id, run.id, profile.id, error_payload)
                    await self._record_step(
                        queue,
                        run,
                        profile,
                        sequence=2,
                        step_id="step_0001",
                        event_type="agent_step_error",
                        label="Harness preflight blocked",
                        status="error",
                    )
                    await queue.put(error_payload)
                    return

                await self._record_step(
                    queue,
                    run,
                    profile,
                    sequence=2,
                    step_id="step_0001",
                    event_type="agent_step_started",
                    label="Run agent stream",
                    status="running",
                )
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
                    execution_policy=execution_policy,
                )
                async for event in self.provider.stream_text(request):
                    self.store.append_profile_event(run.project_id, run.id, profile.id, event)
                    if event.type == "delta":
                        self.store.append_profile_output_delta(
                            run.project_id, run.id, profile.id, event.text or ""
                        )
                    elif event.type == "tool_call":
                        await self._record_tool_step(queue, run, profile, event)
                    elif event.type == "error":
                        logger.error(
                            "Agent provider stream error for run %s profile %s: %s raw=%s",
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
                await self._record_step(
                    queue,
                    run,
                    profile,
                    sequence=9999,
                    step_id="step_0001",
                    event_type="agent_step_completed",
                    label="Run agent stream",
                    status="completed",
                    elapsed_ms=_elapsed_ms(profile_started),
                )
            except Exception as exc:
                logger.exception("Agent execution failed for run %s profile %s", run.id, profile.id)
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
                if not profile_prepared:
                    await queue.put({"run_id": run.id, "profile_id": profile.id, "type": "profile_prepared"})
                await queue.put({"run_id": run.id, "profile_id": profile.id, "type": "profile_done"})

        tasks = [asyncio.create_task(run_profile(profile)) for profile in run.profiles]
        remaining = len(tasks)
        prepared = 0
        early_analysis_sent = False
        try:
            while remaining:
                payload = await queue.get()
                if payload["type"] == "profile_prepared":
                    prepared += 1
                    if prepared == len(tasks):
                        if not early_analysis_sent and not profile_errors:
                            analysis = build_agent_run_analysis(
                                run, self.store.get_run_dir(run.project_id, run.id)
                            )
                            self.store.write_agent_analysis(
                                run.project_id, run.id, analysis.model_dump(mode="json")
                            )
                            early_analysis_sent = True
                            yield {
                                "run_id": run.id,
                                "type": "analysis_ready",
                                "analysis": analysis.model_dump(mode="json"),
                            }
                        profiles_ready_to_stream.set()
                    continue
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
            analysis = build_agent_run_analysis(run, self.store.get_run_dir(run.project_id, run.id))
            self.store.write_agent_analysis(
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

    async def _record_tool_step(
        self, queue: asyncio.Queue[dict[str, Any]], run: RunDocument, profile, event: ProviderEvent
    ) -> None:
        raw = event.raw if isinstance(event.raw, dict) else {}
        tool_name = str(raw.get("tool_name") or raw.get("openai_name") or "tool_call")
        await self._record_step(
            queue,
            run,
            profile,
            sequence=event.sequence,
            step_id=f"tool_{event.sequence:04d}",
            event_type="agent_step_completed",
            label=f"Tool: {tool_name}",
            status="error" if raw.get("ok") is False else "completed",
            tool_name=tool_name,
            subagent_id=raw.get("subagent_id"),
            subagent_label=raw.get("subagent_label"),
            elapsed_ms=raw.get("elapsed_ms") if isinstance(raw.get("elapsed_ms"), int) else None,
            token_usage=raw.get("token_usage") if isinstance(raw.get("token_usage"), dict) else {},
        )

    async def _record_step(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        run: RunDocument,
        profile,
        *,
        sequence: int,
        step_id: str,
        event_type: str,
        label: str,
        status: str,
        tool_name: str | None = None,
        subagent_id: str | None = None,
        subagent_label: str | None = None,
        elapsed_ms: int | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> None:
        event = AgentStepEvent(
            schema_version=settings.schema_version,
            run_id=run.id,
            profile_id=profile.id,
            profile_label=profile.label,
            step_id=step_id,
            sequence=sequence,
            type=event_type,
            label=label,
            status=status,
            tool_name=tool_name,
            subagent_id=subagent_id,
            subagent_label=subagent_label,
            elapsed_ms=elapsed_ms,
            token_usage=token_usage or {},
            created_at=utc_now_iso(),
        )
        self.store.append_agent_step_event(run.project_id, run.id, profile.id, event)
        await queue.put(
            {
                "run_id": run.id,
                "profile_id": profile.id,
                "profile_label": profile.label,
                "type": event_type,
                "agent_step": event.model_dump(mode="json"),
            }
        )


def _agent_instructions(base_instructions: str, run: RunDocument, profile_label: str) -> str:
    config = run.surface_payload
    context = config.context.strip() if config is not None else ""
    max_steps = config.max_steps if config is not None else 16
    context_block = f"\n\nAdditional task context:\n{context}" if context else ""
    return (
        f"{base_instructions}\n\n"
        "You are running inside HarnessDiff Agent mode. Treat the user prompt as one task "
        f"for {profile_label}. Work step by step, use only allowed tools, keep outputs concise, "
        "and make tool-relevant progress visible through streaming text. "
        f"Stop after at most {max_steps} meaningful steps unless the task is already complete."
        f"{context_block}"
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
