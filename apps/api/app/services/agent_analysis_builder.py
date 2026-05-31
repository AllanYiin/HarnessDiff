from __future__ import annotations

import json
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


def build_agent_run_analysis(run: RunDocument, run_dir: Path) -> AnalysisDocument:
    profiles = {
        profile.id: _build_agent_profile_analysis(run, run_dir, profile.id, profile.label)
        for profile in run.profiles
    }
    metrics = {
        profile_id: _agent_metrics(run_dir / profile_id)
        for profile_id in profiles
    }
    return AnalysisDocument(
        schema_version=settings.schema_version,
        project_id=run.project_id,
        run_id=run.id,
        turn_index=run.turn_index,
        generated_at=utc_now_iso(),
        profiles=profiles,
        comparison=_build_comparison(profiles),
        notes=[
            "Agent analysis is deterministic and based on local JSON artifacts.",
            "Step, tool, and subagent counts are structural metrics, not semantic quality scores.",
        ],
        raw_sources={
            "run_json": str(run_dir / "run.json"),
            "analysis_basis": "local_agent_artifacts",
            "agent_metrics": metrics,
        },
    )


def _build_agent_profile_analysis(
    run: RunDocument,
    run_dir: Path,
    profile_id: str,
    profile_label: str,
) -> ProfileAnalysis:
    profile_dir = run_dir / profile_id
    input_doc = _read_optional_json(profile_dir / "input.json")
    output_doc = _read_optional_json(profile_dir / "output.json")
    usage = _usage_from_doc(_read_optional_json(profile_dir / "usage.json"))
    harness_modules = normalize_harness_modules(input_doc.get("harness_modules", {}))
    enabled_modules = [name for name, enabled in harness_modules.items() if enabled]
    harness_decisions = _events_with_key(profile_dir / "events.jsonl", "harness_decision")
    subagents = _subagent_analyses(profile_dir)
    subagent_usage_total = _sum_usage(
        subagent.current_turn_usage for subagent in subagents.values()
    )
    tool_names = input_doc.get("tool_names", [])
    tool_text = ", ".join(str(name) for name in tool_names) if isinstance(tool_names, list) else ""
    steps_text = _steps_summary(profile_dir / "steps.jsonl")
    return ProfileAnalysis(
        profile_id=profile_id,
        profile_label=profile_label,
        current_turn_usage=usage,
        cumulative_usage=usage,
        context_sections=[
            _section(
                "agent_instructions",
                "Agent instructions",
                "sent" if input_doc.get("instructions") else "missing",
                str(input_doc.get("instructions", "")),
                "Final agent instructions sent to the provider.",
            ),
            _section(
                "tool_definitions",
                "Tool definitions",
                "sent" if tool_text else "not_configured",
                tool_text,
                "Tool definitions available to this agent profile.",
            ),
            _section(
                "current_agent_task",
                "Current agent task",
                "sent",
                str(input_doc.get("prompt", run.prompt)),
                "Agent task objective sent to the provider.",
            ),
            _section(
                "agent_steps",
                "Agent step trace",
                "recorded" if steps_text else "missing",
                steps_text,
                "Recorded foreground agent steps and tool trace summaries.",
            ),
        ],
        output_characters=len(str(output_doc.get("text", ""))),
        enabled_harness_modules=enabled_modules,
        harness_decisions=harness_decisions,
        provider_context_keys=["instructions", "prompt", "tools"] if tool_text else ["instructions", "prompt"],
        subagent_count=len(subagents),
        subagent_usage_total=subagent_usage_total,
        caller_usage_total=_sum_usage([usage, subagent_usage_total]),
        subagents=subagents,
    )


def _agent_metrics(profile_dir: Path) -> dict[str, int]:
    events = _read_jsonl(profile_dir / "events.jsonl")
    steps = _read_jsonl(profile_dir / "steps.jsonl")
    return {
        "step_count": len(steps),
        "tool_call_count": sum(1 for event in events if event.get("type") == "tool_call"),
        "tool_error_count": sum(
            1
            for event in events
            if event.get("type") == "tool_call"
            and isinstance(event.get("raw"), dict)
            and event["raw"].get("ok") is False
        ),
        "subagent_count": sum(
            1
            for event in events
            if event.get("type") == "tool_call"
            and isinstance(event.get("raw"), dict)
            and event["raw"].get("subagent_id")
        ),
        "error_count": sum(1 for event in events if event.get("type") == "error"),
        "harness_decision_count": sum(1 for event in events if "harness_decision" in event),
    }


def _steps_summary(path: Path) -> str:
    return "\n".join(
        f"{step.get('sequence')}: {step.get('label')} [{step.get('status')}]"
        for step in _read_jsonl(path)
    )


def _events_with_key(path: Path, key: str) -> list[dict[str, Any]]:
    return [
        event[key]
        for event in _read_jsonl(path)
        if isinstance(event.get(key), dict)
    ]


def _subagent_analyses(profile_dir: Path) -> dict[str, SubagentAnalysis]:
    subagents_dir = profile_dir / "subagents"
    if not subagents_dir.exists():
        return {}
    analyses: dict[str, SubagentAnalysis] = {}
    for subagent_dir in sorted(child for child in subagents_dir.iterdir() if child.is_dir()):
        input_doc = _read_optional_json(subagent_dir / "input.json")
        output_doc = _read_optional_json(subagent_dir / "output.json")
        usage = _usage_from_doc(_read_optional_json(subagent_dir / "usage.json"))
        subagent_id = str(input_doc.get("subagent_id") or subagent_dir.name)
        subagent_label = str(input_doc.get("subagent_label") or subagent_id)
        analyses[subagent_id] = SubagentAnalysis(
            subagent_id=subagent_id,
            subagent_label=subagent_label,
            current_turn_usage=usage,
            output_characters=len(str(output_doc.get("text", ""))),
            event_counts=_event_counts(subagent_dir / "events.jsonl"),
            context_sections=[
                _section(
                    "subagent_task",
                    "Subagent delegated task",
                    "sent" if input_doc.get("prompt") else "missing",
                    str(input_doc.get("prompt", "")),
                    "Delegated task sent to the subagent.",
                )
            ],
            provider_context_keys=["instructions", "prompt"],
        )
    return analyses


def _event_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in _read_jsonl(path):
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


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


def _build_comparison(profiles: dict[str, ProfileAnalysis]) -> AnalysisComparison:
    ordered = list(profiles.values())
    if len(ordered) < 2:
        return AnalysisComparison()
    reference_profile, controlled_profile = ordered[0], ordered[1]
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
            if section.status in {"sent", "recorded"}
            and not any(
                peer.key == section.key and peer.status == section.status
                for peer in reference_profile.context_sections
            )
        ],
    )


def _sum_usage(usages) -> TokenUsage:
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
        estimated_tokens=max(1, (characters + 3) // 4) if characters else 0,
        notes=notes,
    )


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
