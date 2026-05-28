from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re


@dataclass(frozen=True)
class SubagentDefinition:
    id: str
    label: str
    description: str
    instructions: str
    model: str = "gpt-5.4-mini"
    reasoning_effort: str = "medium"
    max_output_chars: int = 4000
    tools: tuple[str, ...] = ()
    enabled: bool = True


SUBAGENT_TOOL_ALIASES: dict[str, str] = {
    "websearch": "standard.web.search",
    "webfetch": "standard.web.fetch",
    "webextracttext": "standard.web.extract_text",
    "webextractlinks": "standard.web.extract_links",
    "standard.web.search": "standard.web.search",
    "standard.web.fetch": "standard.web.fetch",
    "standard.web.extract_text": "standard.web.extract_text",
    "standard.web.extract_links": "standard.web.extract_links",
}


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
        id="web-researcher",
        label="Web Researcher",
        description="Search and fetch web sources, then return concise source-grounded notes.",
        instructions=(
            "You are a web research specialist subagent inside HarnessDiff. "
            "Research only the delegated task. Return notes, not raw search results or full page text. "
            "Use 3-5 concise bullet findings with source URLs. "
            "Do not speculate beyond fetched or searched sources; if information is not found, say so clearly."
        ),
        tools=("standard.web.search", "standard.web.fetch"),
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

SUBAGENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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


def load_subagent_definitions(agents_dir: Path) -> tuple[SubagentDefinition, ...]:
    if not agents_dir.exists():
        return ()
    definitions: list[SubagentDefinition] = []
    seen: set[str] = set()
    for path in sorted(child for child in agents_dir.iterdir() if child.is_file()):
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        try:
            definition = (
                _definition_from_json(path)
                if path.suffix.lower() == ".json"
                else _definition_from_markdown(path)
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if definition is None or definition.id in seen:
            continue
        seen.add(definition.id)
        definitions.append(definition)
    return tuple(definitions)


def definition_to_markdown(definition: SubagentDefinition) -> str:
    return (
        "---\n"
        f"id: {definition.id}\n"
        f"label: {definition.label}\n"
        f"description: {definition.description}\n"
        f"model: {definition.model}\n"
        f"reasoning_effort: {definition.reasoning_effort}\n"
        f"max_output_chars: {definition.max_output_chars}\n"
        f"{_tools_frontmatter(definition.tools)}"
        f"enabled: {str(definition.enabled).lower()}\n"
        "---\n"
        f"{definition.instructions}\n"
    )


def _definition_from_json(path: Path) -> SubagentDefinition | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return _definition_from_data(data, fallback_id=path.stem)


def _definition_from_markdown(path: Path) -> SubagentDefinition | None:
    text = path.read_text(encoding="utf-8")
    metadata, body = _frontmatter(text)
    data = {**metadata, "instructions": metadata.get("instructions") or body.strip()}
    return _definition_from_data(data, fallback_id=path.stem)


def _definition_from_data(data: dict[str, object], *, fallback_id: str) -> SubagentDefinition | None:
    subagent_id = str(data.get("id") or data.get("name") or fallback_id).strip()
    if not SUBAGENT_ID_RE.fullmatch(subagent_id):
        return None
    instructions = str(data.get("instructions") or "").strip()
    if not instructions:
        return None
    return SubagentDefinition(
        id=subagent_id,
        label=str(data.get("label") or subagent_id).strip() or subagent_id,
        description=str(data.get("description") or "").strip(),
        instructions=instructions,
        model=str(data.get("model") or "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        reasoning_effort=str(data.get("reasoning_effort") or "medium").strip() or "medium",
        max_output_chars=_as_int(data.get("max_output_chars"), default=4000),
        tools=normalize_subagent_tools(data.get("tools")),
        enabled=_as_bool(data.get("enabled"), default=True),
    )


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return metadata, "\n".join(lines[index + 1 :])
        key, sep, value = line.partition(":")
        if sep:
            metadata[key.strip().lower()] = value.strip().strip('"')
    return metadata, text


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return default
    return default


def normalize_subagent_tools(value: object) -> tuple[str, ...]:
    raw_items: list[object]
    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        raw_items = re.split(r"[,;\s]+", stripped)
    else:
        return ()

    tools: list[str] = []
    for item in raw_items:
        normalized = str(item).strip().strip("[]\"'").lower()
        if not normalized:
            continue
        tool_name = SUBAGENT_TOOL_ALIASES.get(normalized)
        if tool_name is not None and tool_name not in tools:
            tools.append(tool_name)
    return tuple(tools)


def _tools_frontmatter(tools: tuple[str, ...]) -> str:
    if not tools:
        return ""
    return f"tools: {', '.join(tools)}\n"
