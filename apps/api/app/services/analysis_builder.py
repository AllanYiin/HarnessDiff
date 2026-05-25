from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.models.analysis import (
    AnalysisComparison,
    AnalysisDocument,
    ContextSection,
    ProfileAnalysis,
    SubagentAnalysis,
    TokenUsage,
)
from app.models.harness_modules import normalize_harness_modules
from app.models.project import utc_now_iso
from app.models.run import RunDocument
from app.storage.json_io import read_json

def build_run_analysis(run: RunDocument, run_dir: Path, project_runs: list[Path]) -> AnalysisDocument:
    profiles = {
        profile.id: _build_profile_analysis(run, run_dir, project_runs, profile.id, profile.label)
        for profile in run.profiles
    }
    comparison = _build_comparison(profiles)
    notes = [
        "Token usage is provider-reported when usage.json exists.",
        "Context section tokens are deterministic estimates from saved characters.",
        "Conversation history is replayed per profile from local artifacts when prior completed turns exist.",
    ]
    return AnalysisDocument(
        schema_version=settings.schema_version,
        project_id=run.project_id,
        run_id=run.id,
        turn_index=run.turn_index,
        generated_at=utc_now_iso(),
        profiles=profiles,
        comparison=comparison,
        notes=notes,
        raw_sources={
            "run_json": str(run_dir / "run.json"),
            "analysis_basis": "local_json_artifacts",
        },
    )


def _build_profile_analysis(
    run: RunDocument,
    run_dir: Path,
    project_runs: list[Path],
    profile_id: str,
    profile_label: str,
) -> ProfileAnalysis:
    profile_dir = run_dir / profile_id
    input_doc = _read_optional_json(profile_dir / "input.json")
    output_doc = _read_optional_json(profile_dir / "output.json")
    usage_doc = _read_optional_json(profile_dir / "usage.json")
    usage = _usage_from_doc(usage_doc)
    cumulative = _cumulative_usage(project_runs, run.turn_index, profile_id)
    harness_modules = normalize_harness_modules(input_doc.get("harness_modules", {}))
    enabled_modules = [name for name, enabled in harness_modules.items() if enabled]
    harness_decisions = _harness_decisions(profile_dir / "events.jsonl")
    context_sections = _context_sections(run, project_runs, profile_id, input_doc)
    provider_context_keys = ["instructions", "prompt"]
    if input_doc.get("tool_names"):
        provider_context_keys.append("tools")
    subagents = _subagent_analyses(profile_dir)
    subagent_usage_total = _sum_usage(
        subagent.current_turn_usage for subagent in subagents.values()
    )
    return ProfileAnalysis(
        profile_id=profile_id,
        profile_label=profile_label,
        current_turn_usage=usage,
        cumulative_usage=cumulative,
        context_sections=context_sections,
        output_characters=len(str(output_doc.get("text", ""))),
        enabled_harness_modules=enabled_modules,
        harness_decisions=harness_decisions,
        provider_context_keys=provider_context_keys,
        subagent_count=len(subagents),
        subagent_usage_total=subagent_usage_total,
        caller_usage_total=_sum_usage([usage, subagent_usage_total]),
        subagents=subagents,
    )


def _context_sections(
    run: RunDocument, project_runs: list[Path], profile_id: str, input_doc: dict[str, Any]
) -> list[ContextSection]:
    instructions = str(input_doc.get("instructions", ""))
    prompt = str(input_doc.get("prompt", run.prompt))
    harness_modules = normalize_harness_modules(input_doc.get("harness_modules", {}))
    prior_history = _prior_history_characters(project_runs, run.turn_index, profile_id)
    conversation_messages = input_doc.get("conversation_messages", [])
    tool_names = input_doc.get("tool_names", [])
    history_characters = _conversation_messages_characters(conversation_messages)
    enabled_module_names = ", ".join(name for name, enabled in harness_modules.items() if enabled)
    tool_text = ", ".join(str(name) for name in tool_names) if isinstance(tool_names, list) else ""
    return [
        _section(
            "system_prompt",
            "System prompt / instructions",
            "sent",
            instructions,
            "Final profile instructions sent to the provider.",
        ),
        _section(
            "tool_definitions",
            "Tool definitions",
            "sent" if tool_text else "not_configured",
            tool_text,
            "Tool definitions were sent to the provider for this profile."
            if tool_text
            else "Tool definitions were not available for this profile.",
        ),
        _section(
            "behavior_preferences",
            "Behavior preferences",
            "sent" if enabled_module_names else "not_configured",
            enabled_module_names,
            "Harness modules become behavior preferences for this profile.",
        ),
        _section(
            "harness_control_plane",
            "Harnessable control plane",
            "evaluated" if any(harness_modules.values()) else "not_configured",
            "Harnessable decisions are recorded before provider execution."
            if any(harness_modules.values())
            else "",
            "Harness profile events can be gated and traced before provider execution.",
        ),
        _section(
            "personal_memory",
            "Personal memory",
            "not_configured",
            "",
            "Personal memory storage is reserved for a later stage.",
        ),
        _section(
            "current_user_turn",
            "Current user turn",
            "sent",
            prompt,
            "Current prompt sent to the provider.",
        ),
        ContextSection(
            key="stored_conversation_history",
            label="Stored conversation history",
            status="sent" if history_characters else "not_configured",
            characters=history_characters or prior_history,
            estimated_tokens=_estimate_tokens(history_characters or prior_history),
            notes="Prior completed turns for this profile are replayed into provider input."
            if history_characters
            else "No prior completed turn for this profile was available to replay.",
        ),
    ]


def _build_comparison(profiles: dict[str, ProfileAnalysis]) -> AnalysisComparison:
    ordered = list(profiles.values())
    reference_profile = ordered[0] if ordered else None
    controlled_profile = ordered[1] if len(ordered) > 1 else None
    if not controlled_profile or not reference_profile:
        return AnalysisComparison()
    return AnalysisComparison(
        total_token_delta=controlled_profile.current_turn_usage.total_tokens
        - reference_profile.current_turn_usage.total_tokens,
        input_token_delta=controlled_profile.current_turn_usage.input_tokens
        - reference_profile.current_turn_usage.input_tokens,
        output_token_delta=controlled_profile.current_turn_usage.output_tokens
        - reference_profile.current_turn_usage.output_tokens,
        reasoning_token_delta=controlled_profile.current_turn_usage.reasoning_tokens
        - reference_profile.current_turn_usage.reasoning_tokens,
        controlled_profile_extra_sections=[
            section.key
            for section in controlled_profile.context_sections
            if section.status == "sent"
            and not any(
                peer.key == section.key and peer.status == "sent"
                for peer in reference_profile.context_sections
            )
        ],
    )


def _cumulative_usage(project_runs: list[Path], turn_index: int, profile_id: str) -> TokenUsage:
    total = TokenUsage(source="provider_reported")
    found = False
    for run_path in project_runs:
        run_doc = _read_optional_json(run_path / "run.json")
        if int(run_doc.get("turn_index", -1)) > turn_index:
            continue
        usage = _usage_from_doc(_read_optional_json(run_path / profile_id / "usage.json"))
        if usage.source == "missing":
            continue
        found = True
        total.input_tokens += usage.input_tokens
        total.cached_tokens += usage.cached_tokens
        total.output_tokens += usage.output_tokens
        total.reasoning_tokens += usage.reasoning_tokens
        total.total_tokens += usage.total_tokens
    if not found:
        total.source = "missing"
    return total


def _prior_history_characters(project_runs: list[Path], turn_index: int, profile_id: str) -> int:
    characters = 0
    for run_path in project_runs:
        run_doc = _read_optional_json(run_path / "run.json")
        if int(run_doc.get("turn_index", -1)) >= turn_index:
            continue
        input_doc = _read_optional_json(run_path / profile_id / "input.json")
        output_doc = _read_optional_json(run_path / profile_id / "output.json")
        characters += len(str(input_doc.get("prompt", "")))
        characters += len(str(output_doc.get("text", "")))
    return characters


def _conversation_messages_characters(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    characters = 0
    for message in value:
        if isinstance(message, dict):
            characters += len(str(message.get("content", "")))
    return characters


def _usage_from_doc(usage_doc: dict[str, Any]) -> TokenUsage:
    usage = usage_doc.get("usage") if isinstance(usage_doc.get("usage"), dict) else {}
    if not usage:
        return TokenUsage()
    return TokenUsage(
        input_tokens=_as_int(usage.get("input_tokens")),
        cached_tokens=_as_int(usage.get("cached_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
        reasoning_tokens=_as_int(usage.get("reasoning_tokens")),
        total_tokens=_as_int(usage.get("total_tokens")),
        source="provider_reported",
    )


def _subagent_analyses(profile_dir: Path) -> dict[str, SubagentAnalysis]:
    subagents_dir = profile_dir / "subagents"
    if not subagents_dir.exists():
        return {}
    analyses: dict[str, SubagentAnalysis] = {}
    for subagent_dir in sorted(child for child in subagents_dir.iterdir() if child.is_dir()):
        input_doc = _read_optional_json(subagent_dir / "input.json")
        output_doc = _read_optional_json(subagent_dir / "output.json")
        usage_doc = _read_optional_json(subagent_dir / "usage.json")
        subagent_id = str(input_doc.get("subagent_id") or subagent_dir.name)
        subagent_label = str(input_doc.get("subagent_label") or subagent_id)
        instructions = str(input_doc.get("instructions", ""))
        prompt = str(input_doc.get("prompt", ""))
        usage = _usage_from_doc(usage_doc)
        analyses[subagent_id] = SubagentAnalysis(
            subagent_id=subagent_id,
            subagent_label=subagent_label,
            current_turn_usage=usage,
            output_characters=len(str(output_doc.get("text", ""))),
            event_counts=_event_counts(subagent_dir / "events.jsonl"),
            context_sections=[
                _section(
                    "subagent_instructions",
                    "Subagent instructions",
                    "sent" if instructions else "missing",
                    instructions,
                    "Instructions sent to this subagent.",
                ),
                _section(
                    "subagent_task",
                    "Subagent delegated task",
                    "sent" if prompt else "missing",
                    prompt,
                    "Delegated task and manager-supplied context sent to this subagent.",
                ),
            ],
            provider_context_keys=["instructions", "prompt"],
        )
    return analyses


def _event_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type") or "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _sum_usage(usages: Any) -> TokenUsage:
    total = TokenUsage(source="provider_reported")
    found = False
    for usage in usages:
        if usage.source == "missing":
            continue
        found = True
        total.input_tokens += usage.input_tokens
        total.cached_tokens += usage.cached_tokens
        total.output_tokens += usage.output_tokens
        total.reasoning_tokens += usage.reasoning_tokens
        total.total_tokens += usage.total_tokens
    if not found:
        total.source = "missing"
    return total


def _section(key: str, label: str, status: str, text: str, notes: str) -> ContextSection:
    characters = len(text)
    return ContextSection(
        key=key,
        label=label,
        status=status,
        characters=characters,
        estimated_tokens=_estimate_tokens(characters),
        notes=notes,
    )


def _estimate_tokens(characters: int) -> int:
    if characters <= 0:
        return 0
    return max(1, math.ceil(characters / 4))


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _harness_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    decisions: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            decision = event.get("harness_decision")
            if isinstance(decision, dict):
                decisions.append(decision)
    return decisions
