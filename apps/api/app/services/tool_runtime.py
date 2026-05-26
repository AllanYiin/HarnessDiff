from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.read_only_bash import ReadOnlyBashExecutor


ALLOWED_TOOL_NAMES: tuple[str, ...] = (
    "standard.web.extract_links",
    "standard.web.search",
    "standard.web.fetch",
    "standard.web.extract_text",
    "standard.fs.list",
    "standard.fs.stat",
    "standard.fs.search",
    "standard.fs.grep",
    "standard.data.json_parse",
    "standard.data.json_validate",
    "standard.data.csv_inspect",
    "standard.data.jsonl_inspect",
    "standard.shell.bash",
)


@dataclass(frozen=True)
class ToolInvocationRecord:
    ok: bool
    name: str
    openai_name: str
    arguments: dict[str, Any]
    elapsed_ms: int
    result: Any = None
    error: dict[str, Any] | None = None

    def output_payload(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "tool_name": self.name, "result": self.result}
        return {"ok": False, "tool_name": self.name, "error": self.error or {}}

    def event_payload(self) -> dict[str, Any]:
        payload = {
            "ok": self.ok,
            "tool_name": self.name,
            "openai_name": self.openai_name,
            "arguments": _truncate_jsonable(self.arguments),
            "elapsed_ms": self.elapsed_ms,
        }
        if self.ok:
            payload["result_summary"] = _json_summary(self.result)
        else:
            payload["error"] = self.error or {}
        return payload


class ToolAnythingRuntime:
    def __init__(
        self,
        root: Path,
        *,
        allowed_tool_names: tuple[str, ...] = ALLOWED_TOOL_NAMES,
    ) -> None:
        from toolanything import StandardToolOptions, ToolRegistry, register_standard_tools
        from toolanything import ToolSpec
        from toolanything.adapters.openai_adapter import OpenAIAdapter

        self.root = root.resolve()
        self.allowed_tool_names = tuple(allowed_tool_names)
        self.registry = ToolRegistry()
        self.bash_executor = ReadOnlyBashExecutor(self.root)
        register_standard_tools(
            self.registry,
            StandardToolOptions(
                roots={"workspace": self.root},
                include_write_tools=False,
            ),
        )
        self.registry.register(
            ToolSpec(
                name="standard.fs.grep",
                description=(
                    "Search text files under the workspace with grep-style line "
                    "matches and optional context. Use this instead of reading an "
                    "entire document when looking for facts, symbols, sections, or "
                    "evidence. Returns only matching excerpts, not full file content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "root_id": {
                            "type": "string",
                            "description": "Configured root id. Use workspace.",
                            "default": "workspace",
                        },
                        "relative_path": {
                            "type": "string",
                            "description": (
                                "Workspace-relative file or directory to search. "
                                "Use '.' for the whole workspace."
                            ),
                            "default": ".",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Regex or literal text to search for.",
                        },
                        "glob": {
                            "type": "string",
                            "description": "File glob used when relative_path is a directory.",
                            "default": "*",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "Whether matching is case-sensitive.",
                            "default": False,
                        },
                        "regex": {
                            "type": "boolean",
                            "description": "Treat pattern as a regular expression.",
                            "default": True,
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Number of lines before and after each match.",
                            "default": 2,
                        },
                        "max_matches": {
                            "type": "integer",
                            "description": "Maximum number of matches to return.",
                            "default": 50,
                        },
                    },
                    "required": [
                        "root_id",
                        "relative_path",
                        "pattern",
                        "glob",
                        "case_sensitive",
                        "regex",
                        "context_lines",
                        "max_matches",
                    ],
                    "additionalProperties": False,
                },
                tags=("standard", "fs", "readonly", "grep"),
                strict=True,
                func=self._grep,
            )
        )
        self.registry.register(
            ToolSpec(
                name="standard.shell.bash",
                description=(
                    "Run a constrained read-only Bash-style command inside the "
                    "workspace root. Supports grep, sed, awk, head, tail, wc, "
                    "nl, cat, ls, find, pwd, echo, simple pipes, and &&/||/; "
                    "control flow. Paths must be workspace-relative. Mutation, "
                    "network access, redirects, and process-launch commands are rejected."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "Read-only Bash-style command to run in the workspace. "
                                "Use relative paths such as apps/api/app/main.py."
                            ),
                        }
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                tags=("standard", "shell", "readonly"),
                strict=True,
                func=self.bash_executor.run,
            )
        )
        for spec in list(self.registry.list()):
            if spec.name not in self.allowed_tool_names:
                self.registry.unregister(spec.name)
        registered = {spec.name for spec in self.registry.list()}
        missing = set(self.allowed_tool_names) - registered
        if missing:
            raise RuntimeError(f"ToolAnything tools missing from registry: {sorted(missing)}")
        self.adapter = OpenAIAdapter(self.registry)

    def list_tool_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.registry.list())

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return [_to_responses_tool(tool) for tool in self.adapter.to_schema()]

    def tool_manifest(self) -> list[dict[str, Any]]:
        return self.registry.to_tool_manifest(tags=["standard"])

    def to_openai_name(self, tool_name: str) -> str:
        return self.adapter.to_openai_name(tool_name)

    def from_openai_name(self, openai_name: str) -> str:
        return self.adapter.from_openai_name(openai_name)

    async def invoke_openai_tool(
        self, openai_name: str, arguments: dict[str, Any]
    ) -> ToolInvocationRecord:
        started = time.perf_counter()
        original_name = self.from_openai_name(openai_name)
        if original_name not in self.allowed_tool_names:
            return ToolInvocationRecord(
                ok=False,
                name=original_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool is not enabled for HarnessDiff: {original_name}",
                },
            )
        try:
            result = await self.registry.invoke_tool_async(
                original_name,
                arguments=dict(arguments or {}),
            )
        except Exception as exc:
            return ToolInvocationRecord(
                ok=False,
                name=original_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
        return ToolInvocationRecord(
            ok=True,
            name=original_name,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            result=result,
        )


    def _grep(
        self,
        root_id: str = "workspace",
        relative_path: str = ".",
        pattern: str = "",
        glob: str = "*",
        case_sensitive: bool = False,
        regex: bool = True,
        context_lines: int = 2,
        max_matches: int = 50,
    ) -> dict[str, Any]:
        if root_id != "workspace":
            raise ValueError("Only the workspace root is available.")
        if not pattern:
            raise ValueError("pattern is required.")
        context = max(0, min(int(context_lines), 10))
        limit = max(1, min(int(max_matches), 200))
        target = _safe_workspace_path(self.root, relative_path)
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern if regex else re.escape(pattern), flags)
        files = [target] if target.is_file() else sorted(target.rglob(glob or "*"))
        matches: list[dict[str, Any]] = []
        scanned_files = 0
        skipped_files = 0
        for file_path in files:
            if len(matches) >= limit:
                break
            if not file_path.is_file():
                continue
            scanned_files += 1
            try:
                file_matches = _grep_file(
                    file_path,
                    self.root,
                    compiled,
                    context_lines=context,
                    remaining_matches=limit - len(matches),
                )
            except OSError:
                skipped_files += 1
                continue
            matches.extend(file_matches)
        return {
            "pattern": pattern,
            "relative_path": relative_path,
            "glob": glob,
            "matches": matches,
            "match_count": len(matches),
            "scanned_files": scanned_files,
            "skipped_files": skipped_files,
            "truncated": len(matches) >= limit,
        }

def create_default_tool_runtime() -> ToolAnythingRuntime:
    repo_root = Path(__file__).resolve().parents[4]
    return ToolAnythingRuntime(repo_root)


def _to_responses_tool(tool: dict[str, Any]) -> dict[str, Any]:
    if tool.get("type") != "function":
        return dict(tool)
    function = tool.get("function")
    if not isinstance(function, dict):
        return dict(tool)
    payload = {
        "type": "function",
        "name": function.get("name"),
        "description": function.get("description", ""),
        "parameters": function.get("parameters", {"type": "object", "properties": {}}),
    }
    if "strict" in function:
        payload["strict"] = function["strict"]
    return payload


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _json_summary(value: Any, *, max_chars: int = 1200) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = repr(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _truncate_jsonable(value: Any, *, max_chars: int = 1200) -> Any:
    summary = _json_summary(value, max_chars=max_chars)
    try:
        return json.loads(summary)
    except json.JSONDecodeError:
        return summary



def _safe_workspace_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path escapes configured workspace root")
    if not candidate.exists():
        raise ValueError(f"path does not exist: {relative_path}")
    return candidate


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _grep_file(
    file_path: Path,
    root: Path,
    regex: re.Pattern[str],
    *,
    context_lines: int,
    remaining_matches: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    before = deque(maxlen=context_lines)
    pending_after: list[dict[str, Any]] = []
    relative = _relative_path(file_path, root)
    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            still_pending: list[dict[str, Any]] = []
            for pending in pending_after:
                pending["match"]["after"].append({"line_number": line_number, "line": line})
                pending["remaining"] -= 1
                if pending["remaining"] > 0:
                    still_pending.append(pending)
            pending_after = still_pending

            if len(matches) < remaining_matches and regex.search(line):
                match = {
                    "path": relative,
                    "line_number": line_number,
                    "line": line,
                    "before": list(before),
                    "after": [],
                }
                matches.append(match)
                if context_lines:
                    pending_after.append({"match": match, "remaining": context_lines})

            before.append({"line_number": line_number, "line": line})
            if len(matches) >= remaining_matches and not pending_after:
                break
    return matches
