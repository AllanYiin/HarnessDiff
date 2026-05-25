from __future__ import annotations

import fnmatch
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SHELL_SYNTAX_DENY_RE = re.compile(r"(\$\(|`|(?<![=!<>])>>?(?![=])|<\()", re.IGNORECASE)
_DENIED_COMMANDS = {
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "mount",
    "umount",
    "curl",
    "wget",
    "ssh",
    "scp",
    "ftp",
    "nc",
    "ncat",
    "telnet",
    "python",
    "python3",
    "py",
    "node",
    "perl",
    "ruby",
    "php",
    "powershell",
    "pwsh",
    "cmd",
    "git",
    "pip",
    "npm",
    "pnpm",
    "yarn",
    "tee",
    "touch",
    "mkdir",
    "rmdir",
}

_MAX_COMMAND_CHARS = 1000
_MAX_OUTPUT_CHARS = 12000
_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_FIND_RESULTS = 500


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout_lines: list[str]
    stderr: str = ""


class ReadOnlyBashExecutor:
    """Small read-only Bash-style interpreter scoped to a workspace root.

    This mirrors TokenSaving's Windows fallback approach instead of exposing a
    full OS shell to the model.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def run(self, command: str) -> dict[str, Any]:
        started = time.perf_counter()
        command = str(command or "").strip()
        if not command:
            return {"error": "missing command"}
        if len(command) > _MAX_COMMAND_CHARS:
            return {"error": f"command too long; keep it under {_MAX_COMMAND_CHARS} chars"}
        if _SHELL_SYNTAX_DENY_RE.search(command):
            return {
                "error": (
                    "command rejected by read-only guard; use grep/sed/awk/head/"
                    "tail/wc/nl/cat/ls/find/pwd/echo inside the workspace without "
                    "network access, redirects, mutation, or process-launch commands"
                )
            }

        result = self._execute(command)
        stdout_raw = "\n".join(result.stdout_lines)
        if stdout_raw:
            stdout_raw += "\n"
        stdout, out_truncated = _limit_text(stdout_raw)
        stderr, err_truncated = _limit_text(result.stderr)
        return {
            "command": command,
            "exit_code": result.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": out_truncated or err_truncated,
            "fallback": "python-readonly-bash",
            "workspace_root": str(self.root),
            "elapsed_ms": max(0, int((time.perf_counter() - started) * 1000)),
        }

    def _execute(self, command: str) -> CommandResult:
        statements = _split_into_statements(command)
        if not statements:
            return CommandResult(2, [], "empty command")

        last_exit = 0
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        for separator, statement in statements:
            if separator == "&&" and last_exit != 0:
                continue
            if separator == "||" and last_exit == 0:
                continue
            if not statement:
                continue

            stdin_lines: list[str] | None = None
            exit_code = 0
            for segment in _split_pipeline(statement):
                segment_result = self._run_segment(segment, stdin_lines)
                exit_code = segment_result.exit_code
                stdin_lines = segment_result.stdout_lines
                if segment_result.stderr:
                    stderr_chunks.append(segment_result.stderr)
                if exit_code not in (0, 1):
                    break
            if stdin_lines:
                stdout_chunks.extend(stdin_lines)
            last_exit = exit_code
        return CommandResult(last_exit, stdout_chunks, "\n".join(stderr_chunks))

    def _run_segment(self, segment: str, stdin_lines: list[str] | None) -> CommandResult:
        try:
            argv = shlex.split(segment, posix=True)
        except ValueError as exc:
            return CommandResult(2, [], f"parse error: {exc}")
        if not argv:
            return CommandResult(0, stdin_lines or [])

        cmd, args = argv[0], argv[1:]
        if Path(cmd).name.lower() in _DENIED_COMMANDS:
            return CommandResult(
                2,
                [],
                (
                    "command rejected by read-only guard; use grep/sed/awk/head/"
                    "tail/wc/nl/cat/ls/find/pwd/echo only"
                ),
            )
        if cmd == "pwd":
            return CommandResult(0, ["."])
        if cmd == "echo":
            return CommandResult(0, [" ".join(args)])
        if cmd == "ls":
            return self._ls(args)
        if cmd == "find":
            return self._find(args)
        if cmd == "cat":
            return self._cat(args, stdin_lines)
        if cmd == "nl":
            return self._nl(args, stdin_lines)
        if cmd == "wc":
            return self._wc(args, stdin_lines)
        if cmd in {"head", "tail"}:
            return self._head_tail(cmd, args, stdin_lines)
        if cmd == "sed":
            return self._sed(args, stdin_lines)
        if cmd == "grep":
            return self._grep(args, stdin_lines)
        if cmd == "awk":
            return self._awk(args, stdin_lines)
        return CommandResult(127, [], f"unsupported read-only bash command: {cmd}")

    def _ls(self, args: list[str]) -> CommandResult:
        paths = [arg for arg in args if not arg.startswith("-")]
        if len(paths) > 1:
            return CommandResult(2, [], "ls fallback supports at most one path")
        target = self._resolve_path(paths[0] if paths else ".")
        if isinstance(target, CommandResult):
            return target
        if target.is_file():
            return CommandResult(0, [self._display_path(target)])
        if not target.is_dir():
            return CommandResult(2, [], f"ls: no such file or directory: {paths[0] if paths else '.'}")
        rows = [
            child.name + ("/" if child.is_dir() else "")
            for child in sorted(target.iterdir(), key=lambda item: item.name.lower())
        ]
        return CommandResult(0, rows)

    def _find(self, args: list[str]) -> CommandResult:
        if not args:
            args = ["."]
        root_arg = args[0]
        rest = args[1:]
        target = self._resolve_path(root_arg)
        if isinstance(target, CommandResult):
            return target
        if not target.exists():
            return CommandResult(1, [], f"find: no such file or directory: {root_arg}")

        maxdepth: int | None = None
        type_filter: str | None = None
        name_pattern: str | None = None
        i = 0
        while i < len(rest):
            token = rest[i]
            if token == "-maxdepth" and i + 1 < len(rest):
                try:
                    maxdepth = max(0, int(rest[i + 1]))
                except ValueError:
                    return CommandResult(2, [], "find: invalid -maxdepth")
                i += 2
            elif token == "-type" and i + 1 < len(rest):
                type_filter = rest[i + 1]
                if type_filter not in {"f", "d"}:
                    return CommandResult(2, [], "find fallback supports only -type f or -type d")
                i += 2
            elif token == "-name" and i + 1 < len(rest):
                name_pattern = rest[i + 1]
                i += 2
            else:
                return CommandResult(2, [], "find fallback supports: find PATH [-maxdepth N] [-type f|d] [-name PATTERN]")

        rows: list[str] = []
        base_depth = len(target.relative_to(self.root).parts)
        candidates = [target] if target.is_file() else target.rglob("*")
        for path in candidates:
            depth = len(path.relative_to(self.root).parts) - base_depth
            if maxdepth is not None and depth > maxdepth:
                continue
            if type_filter == "f" and not path.is_file():
                continue
            if type_filter == "d" and not path.is_dir():
                continue
            if name_pattern and not fnmatch.fnmatch(path.name, name_pattern):
                continue
            rows.append(self._display_path(path))
            if len(rows) >= _MAX_FIND_RESULTS:
                rows.append("...[truncated]...")
                break
        return CommandResult(0 if rows else 1, rows)

    def _cat(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        if not args:
            return CommandResult(0, stdin_lines or [])
        rows: list[str] = []
        for arg in args:
            file_result = self._read_file_lines(arg)
            if isinstance(file_result, CommandResult):
                return file_result
            rows.extend(file_result)
        return CommandResult(0, rows)

    def _nl(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        rest = _drop_nl_flags(args)
        source = self._source_lines(rest, stdin_lines, "nl")
        if isinstance(source, CommandResult):
            return source
        return CommandResult(0, [f"{i:>6}\t{line}" for i, line in enumerate(source, start=1)])

    def _wc(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        rest = args[:]
        if rest and rest[0] == "-l":
            rest = rest[1:]
        elif rest and rest[0].startswith("-"):
            return CommandResult(2, [], "wc fallback supports only -l")
        source = self._source_lines(rest, stdin_lines, "wc")
        if isinstance(source, CommandResult):
            return source
        suffix = f" {rest[0]}" if rest else ""
        return CommandResult(0, [f"{len(source)}{suffix}"])

    def _head_tail(self, cmd: str, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        n = 10
        rest = args[:]
        if rest:
            if rest[0] == "-n" and len(rest) >= 2:
                try:
                    n = max(0, int(rest[1]))
                except ValueError:
                    return CommandResult(2, [], f"{cmd}: invalid line count")
                rest = rest[2:]
            elif rest[0].startswith("-n") and len(rest[0]) > 2:
                try:
                    n = max(0, int(rest[0][2:]))
                except ValueError:
                    return CommandResult(2, [], f"{cmd}: invalid line count")
                rest = rest[1:]
            elif re.fullmatch(r"-\d+", rest[0]):
                n = max(0, int(rest[0][1:]))
                rest = rest[1:]
        source = self._source_lines(rest, stdin_lines, cmd)
        if isinstance(source, CommandResult):
            return source
        return CommandResult(0, source[:n] if cmd == "head" else source[-n:] if n else [])

    def _sed(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        if len(args) < 2 or args[0] != "-n":
            return CommandResult(2, [], "sed fallback supports only: sed -n 'A,Bp' [PATH]")
        match = re.fullmatch(r"(\d+)(?:,(\d+))?p", args[1].strip())
        if not match:
            return CommandResult(2, [], "sed fallback supports numeric print ranges like '120,180p'")
        source = self._source_lines(args[2:], stdin_lines, "sed")
        if isinstance(source, CommandResult):
            return source
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            start, end = end, start
        return CommandResult(0, source[max(0, start - 1):end])

    def _grep(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        show_numbers = False
        ignore_case = False
        extended_regex = False
        context = 0
        rest: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-C" and i + 1 < len(args):
                try:
                    context = max(0, int(args[i + 1]))
                except ValueError:
                    return CommandResult(2, [], "grep: invalid context")
                i += 2
            elif arg.startswith("-C") and len(arg) > 2:
                try:
                    context = max(0, int(arg[2:]))
                except ValueError:
                    return CommandResult(2, [], "grep: invalid context")
                i += 1
            elif arg.startswith("-") and set(arg[1:]).issubset({"n", "i", "E"}):
                show_numbers = show_numbers or "n" in arg
                ignore_case = ignore_case or "i" in arg
                extended_regex = extended_regex or "E" in arg
                i += 1
            else:
                rest.append(arg)
                i += 1
        if not rest:
            return CommandResult(2, [], "grep fallback needs a pattern")
        pattern = rest[0]
        source = self._source_lines(rest[1:], stdin_lines, "grep")
        if isinstance(source, CommandResult):
            return source
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags) if extended_regex else None
        except re.error as exc:
            return CommandResult(2, [], f"grep: invalid regex: {exc}")
        needle = pattern.lower() if ignore_case and not regex else pattern
        matched_indexes: set[int] = set()
        for idx, line in enumerate(source):
            haystack = line.lower() if ignore_case and not regex else line
            matched = bool(regex.search(line)) if regex else needle in haystack
            if matched:
                for offset in range(-context, context + 1):
                    pos = idx + offset
                    if 0 <= pos < len(source):
                        matched_indexes.add(pos)
        rows = [
            f"{idx + 1}:{source[idx]}" if show_numbers else source[idx]
            for idx in sorted(matched_indexes)
        ]
        return CommandResult(0 if rows else 1, rows)

    def _awk(self, args: list[str], stdin_lines: list[str] | None) -> CommandResult:
        if not args:
            return CommandResult(2, [], "awk fallback needs a simple NR range expression")
        expr = args[0].strip()
        match = (
            re.search(r"NR\s*>=\s*(\d+)\s*&&\s*NR\s*<=\s*(\d+)", expr)
            or re.search(r"NR\s*==\s*(\d+)\s*,\s*NR\s*==\s*(\d+)", expr)
        )
        if not match:
            return CommandResult(2, [], "awk fallback supports simple NR ranges, e.g. awk 'NR>=120 && NR<=180' [PATH]")
        source = self._source_lines(args[1:], stdin_lines, "awk")
        if isinstance(source, CommandResult):
            return source
        start, end = int(match.group(1)), int(match.group(2))
        if end < start:
            start, end = end, start
        return CommandResult(0, source[max(0, start - 1):end])

    def _source_lines(
        self, args: list[str], stdin_lines: list[str] | None, cmd: str
    ) -> list[str] | CommandResult:
        if not args:
            if stdin_lines is None:
                return CommandResult(2, [], f"{cmd} fallback needs piped input or one workspace-relative path")
            return stdin_lines
        if len(args) != 1:
            return CommandResult(2, [], f"{cmd} fallback supports at most one path")
        return self._read_file_lines(args[0])

    def _read_file_lines(self, arg: str) -> list[str] | CommandResult:
        target = self._resolve_path(arg)
        if isinstance(target, CommandResult):
            return target
        if not target.is_file():
            return CommandResult(2, [], f"not a readable file: {arg}")
        if target.stat().st_size > _MAX_FILE_BYTES:
            return CommandResult(2, [], f"file too large for bash fallback: {arg}")
        return target.read_text(encoding="utf-8", errors="replace").splitlines()

    def _resolve_path(self, arg: str) -> Path | CommandResult:
        value = str(arg).replace("\\", "/").strip("\"'")
        if value in {"", "."}:
            value = "."
        candidate = Path(value)
        if candidate.is_absolute():
            return CommandResult(2, [], "absolute paths are not allowed")
        target = (self.root / candidate).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            return CommandResult(2, [], "path escapes configured workspace root")
        return target

    def _display_path(self, path: Path) -> str:
        if path == self.root:
            return "."
        return path.relative_to(self.root).as_posix()


def _drop_nl_flags(args: list[str]) -> list[str]:
    rest: list[str] = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "-ba":
            continue
        if arg == "-b" and i + 1 < len(args) and args[i + 1] == "a":
            skip_next = True
            continue
        rest.append(arg)
    return rest


def _limit_text(value: str, limit: int = _MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[: limit - 18] + "\n...[truncated]...", True


def _split_into_statements(command: str) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    buf = ""
    separator: str | None = None
    i = 0
    in_quote: str | None = None
    while i < len(command):
        char = command[i]
        if in_quote:
            buf += char
            if char == in_quote:
                in_quote = None
            i += 1
            continue
        if char in ("'", '"'):
            in_quote = char
            buf += char
            i += 1
            continue
        if char == "\\" and i + 1 < len(command):
            buf += command[i:i + 2]
            i += 2
            continue
        if char == ";":
            out.append((separator, buf.strip()))
            buf = ""
            separator = ";"
            i += 1
            continue
        if command.startswith("&&", i):
            out.append((separator, buf.strip()))
            buf = ""
            separator = "&&"
            i += 2
            continue
        if command.startswith("||", i):
            out.append((separator, buf.strip()))
            buf = ""
            separator = "||"
            i += 2
            continue
        buf += char
        i += 1
    if buf.strip() or separator:
        out.append((separator, buf.strip()))
    return [(sep, statement) for sep, statement in out if statement or sep in {"&&", "||", ";"}]


def _split_pipeline(statement: str) -> list[str]:
    segments: list[str] = []
    buf = ""
    i = 0
    in_quote: str | None = None
    while i < len(statement):
        char = statement[i]
        if in_quote:
            buf += char
            if char == in_quote:
                in_quote = None
            i += 1
            continue
        if char in ("'", '"'):
            in_quote = char
            buf += char
            i += 1
            continue
        if char == "\\" and i + 1 < len(statement):
            buf += statement[i:i + 2]
            i += 2
            continue
        if char == "|" and not statement.startswith("||", i):
            if buf.strip():
                segments.append(buf.strip())
            buf = ""
            i += 1
            continue
        buf += char
        i += 1
    if buf.strip():
        segments.append(buf.strip())
    return segments
