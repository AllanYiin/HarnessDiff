from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.models.analysis import AnalysisComparison, AnalysisDocument, ContextSection, PaneAnalysis, TokenUsage
from app.models.project import utc_now_iso
from app.models.run import RunDocument
from app.storage.json_io import read_json

PANES = ("NoHarness", "Harness")


def build_run_analysis(run: RunDocument, run_dir: Path, project_runs: list[Path]) -> AnalysisDocument:
    panes = {
        pane: _build_pane_analysis(run, run_dir, project_runs, pane)
        for pane in PANES
        if pane in run.target_panes
    }
    comparison = _build_comparison(panes)
    notes = [
        "Token usage is provider-reported when usage.json exists.",
        "Context section tokens are deterministic estimates from saved characters.",
        "Conversation history is stored for analysis but is not yet replayed into provider requests.",
    ]
    return AnalysisDocument(
        schema_version=settings.schema_version,
        project_id=run.project_id,
        run_id=run.id,
        turn_index=run.turn_index,
        generated_at=utc_now_iso(),
        panes=panes,
        comparison=comparison,
        notes=notes,
        raw_sources={
            "run_json": str(run_dir / "run.json"),
            "analysis_basis": "local_json_artifacts",
        },
    )


def _build_pane_analysis(
    run: RunDocument, run_dir: Path, project_runs: list[Path], pane: str
) -> PaneAnalysis:
    pane_dir = run_dir / pane
    input_doc = _read_optional_json(pane_dir / "input.json")
    output_doc = _read_optional_json(pane_dir / "output.json")
    usage_doc = _read_optional_json(pane_dir / "usage.json")
    usage = _usage_from_doc(usage_doc)
    cumulative = _cumulative_usage(project_runs, run.turn_index, pane)
    harness_modules = input_doc.get("harness_modules", {}) if pane == "Harness" else {}
    enabled_modules = [name for name, enabled in harness_modules.items() if enabled]
    context_sections = _context_sections(run, project_runs, pane, input_doc)
    return PaneAnalysis(
        pane=pane,
        current_turn_usage=usage,
        cumulative_usage=cumulative,
        context_sections=context_sections,
        output_characters=len(str(output_doc.get("text", ""))),
        enabled_harness_modules=enabled_modules,
        provider_context_keys=["instructions", "prompt"],
    )


def _context_sections(
    run: RunDocument, project_runs: list[Path], pane: str, input_doc: dict[str, Any]
) -> list[ContextSection]:
    instructions = str(input_doc.get("instructions", ""))
    prompt = str(input_doc.get("prompt", run.prompt))
    harness_modules = input_doc.get("harness_modules", {}) if pane == "Harness" else {}
    prior_history = _prior_history_characters(project_runs, run.turn_index, pane)
    enabled_module_names = ", ".join(name for name, enabled in harness_modules.items() if enabled)
    return [
        _section(
            "system_prompt",
            "System prompt / instructions",
            "sent",
            instructions,
            "Final pane instructions sent to the provider.",
        ),
        _section(
            "tool_definitions",
            "Tool definitions",
            "not_configured",
            "",
            "Tool definitions are reserved in the context model but not yet sent in Stage 5.",
        ),
        _section(
            "behavior_preferences",
            "Behavior preferences",
            "sent" if enabled_module_names else "not_configured",
            enabled_module_names,
            "Harness modules become behavior preferences for the Harness pane.",
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
            status="stored_not_sent",
            characters=prior_history,
            estimated_tokens=_estimate_tokens(prior_history),
            notes="Prior local artifacts are retained but not yet replayed into provider input.",
        ),
    ]


def _build_comparison(panes: dict[str, PaneAnalysis]) -> AnalysisComparison:
    harness = panes.get("Harness")
    no_harness = panes.get("NoHarness")
    if not harness or not no_harness:
        return AnalysisComparison()
    return AnalysisComparison(
        total_token_delta=harness.current_turn_usage.total_tokens
        - no_harness.current_turn_usage.total_tokens,
        input_token_delta=harness.current_turn_usage.input_tokens
        - no_harness.current_turn_usage.input_tokens,
        output_token_delta=harness.current_turn_usage.output_tokens
        - no_harness.current_turn_usage.output_tokens,
        reasoning_token_delta=harness.current_turn_usage.reasoning_tokens
        - no_harness.current_turn_usage.reasoning_tokens,
        harness_extra_sections=[
            section.key
            for section in harness.context_sections
            if section.status == "sent"
            and not any(
                peer.key == section.key and peer.status == "sent"
                for peer in no_harness.context_sections
            )
        ],
    )


def _cumulative_usage(project_runs: list[Path], turn_index: int, pane: str) -> TokenUsage:
    total = TokenUsage(source="provider_reported")
    found = False
    for run_path in project_runs:
        run_doc = _read_optional_json(run_path / "run.json")
        if int(run_doc.get("turn_index", -1)) > turn_index:
            continue
        usage = _usage_from_doc(_read_optional_json(run_path / pane / "usage.json"))
        if usage.source == "missing":
            continue
        found = True
        total.input_tokens += usage.input_tokens
        total.output_tokens += usage.output_tokens
        total.reasoning_tokens += usage.reasoning_tokens
        total.total_tokens += usage.total_tokens
    if not found:
        total.source = "missing"
    return total


def _prior_history_characters(project_runs: list[Path], turn_index: int, pane: str) -> int:
    characters = 0
    for run_path in project_runs:
        run_doc = _read_optional_json(run_path / "run.json")
        if int(run_doc.get("turn_index", -1)) >= turn_index:
            continue
        input_doc = _read_optional_json(run_path / pane / "input.json")
        output_doc = _read_optional_json(run_path / pane / "output.json")
        characters += len(str(input_doc.get("prompt", "")))
        characters += len(str(output_doc.get("text", "")))
    return characters


def _usage_from_doc(usage_doc: dict[str, Any]) -> TokenUsage:
    usage = usage_doc.get("usage") if isinstance(usage_doc.get("usage"), dict) else {}
    if not usage:
        return TokenUsage()
    return TokenUsage(
        input_tokens=_as_int(usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
        reasoning_tokens=_as_int(usage.get("reasoning_tokens")),
        total_tokens=_as_int(usage.get("total_tokens")),
        source="provider_reported",
    )


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
