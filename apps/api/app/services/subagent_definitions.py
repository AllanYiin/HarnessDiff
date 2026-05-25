from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentDefinition:
    id: str
    label: str
    description: str
    instructions: str
    model: str = "gpt-5.4-mini"
    reasoning_effort: str = "medium"
    max_output_chars: int = 4000
    enabled: bool = True


DEFAULT_SUBAGENTS: tuple[SubagentDefinition, ...] = (
    SubagentDefinition(
        id="researcher",
        label="Researcher",
        description="Research provided context and return concise source-grounded notes.",
        instructions=(
            "You are a web research specialist subagent inside HarnessDiff. "
            "Answer only the delegated task from the context supplied by the manager. "
            "Return notes, not raw search results or full page text. "
            "Use 3-5 concise bullet findings with source URLs when sources are provided. "
            "Do not speculate beyond the supplied sources; if information is not found, say so clearly."
        ),
    ),
    SubagentDefinition(
        id="critic",
        label="Critic",
        description="Review a draft or plan for gaps, risks, and weak assumptions.",
        instructions=(
            "You are a critical review subagent inside HarnessDiff. "
            "Identify concrete risks, missing evidence, contradictions, and test gaps. "
            "Prefer actionable findings over broad commentary."
        ),
    ),
    SubagentDefinition(
        id="summarizer",
        label="Summarizer",
        description="Compress provided context into a compact, decision-useful summary.",
        instructions=(
            "You are a summarization subagent inside HarnessDiff. "
            "Preserve key facts, constraints, decisions, and unresolved questions. "
            "Do not add unsupported facts."
        ),
    ),
)


def enabled_subagents(
    definitions: tuple[SubagentDefinition, ...] = DEFAULT_SUBAGENTS,
) -> tuple[SubagentDefinition, ...]:
    return tuple(definition for definition in definitions if definition.enabled)


def subagent_by_id(
    subagent_id: str,
    definitions: tuple[SubagentDefinition, ...] = DEFAULT_SUBAGENTS,
) -> SubagentDefinition | None:
    for definition in enabled_subagents(definitions):
        if definition.id == subagent_id:
            return definition
    return None
