from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.services.skill_store import SkillStore
from app.services.tool_runtime import ToolInvocationRecord, _elapsed_ms


SKILL_RESOURCES_LIST_TOOL_NAME = "skill.resources.list"
SKILL_RESOURCES_LIST_OPENAI_NAME = "skill_resources_list"
SKILL_RESOURCES_READ_TOOL_NAME = "skill.resources.read"
SKILL_RESOURCES_READ_OPENAI_NAME = "skill_resources_read"

SKILL_RESOURCE_TOOL_NAMES = (
    SKILL_RESOURCES_LIST_TOOL_NAME,
    SKILL_RESOURCES_READ_TOOL_NAME,
)

ALLOWED_RESOURCE_DIRS = ("references", "scripts", "assets")
MAX_LISTED_RESOURCES_PER_SKILL = 200
DEFAULT_READ_MAX_CHARS = 6000
MAX_READ_CHARS = 20000
MAX_TEXT_FILE_BYTES = 512 * 1024


class SkillResourceError(ValueError):
    pass


class SkillResourceRuntime:
    def __init__(
        self,
        *,
        skill_store: SkillStore,
        selected_skill_ids: tuple[str, ...],
    ) -> None:
        self.skill_store = skill_store
        self.selected_skill_ids = tuple(dict.fromkeys(selected_skill_ids))

    def has_selected_skills(self) -> bool:
        return bool(self.selected_skill_ids)

    def list_tool_names(self) -> tuple[str, ...]:
        return SKILL_RESOURCE_TOOL_NAMES if self.has_selected_skills() else ()

    def list_openai_tools(self) -> list[dict[str, Any]]:
        if not self.has_selected_skills():
            return []
        return [_skill_resources_list_tool(), _skill_resources_read_tool()]

    def from_openai_name(self, openai_name: str) -> str:
        return {
            SKILL_RESOURCES_LIST_OPENAI_NAME: SKILL_RESOURCES_LIST_TOOL_NAME,
            SKILL_RESOURCES_LIST_TOOL_NAME: SKILL_RESOURCES_LIST_TOOL_NAME,
            SKILL_RESOURCES_READ_OPENAI_NAME: SKILL_RESOURCES_READ_TOOL_NAME,
            SKILL_RESOURCES_READ_TOOL_NAME: SKILL_RESOURCES_READ_TOOL_NAME,
        }.get(openai_name, "")

    async def invoke_openai_tool(
        self, openai_name: str, arguments: dict[str, Any]
    ) -> ToolInvocationRecord:
        started = time.perf_counter()
        tool_name = self.from_openai_name(openai_name)
        if tool_name not in self.list_tool_names():
            return ToolInvocationRecord(
                ok=False,
                name=tool_name or openai_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool is not enabled for selected skills: {openai_name}",
                },
            )
        try:
            if tool_name == SKILL_RESOURCES_LIST_TOOL_NAME:
                result = self.list_resources(skill_id=_optional_str(arguments.get("skill_id")))
            else:
                result = self.read_resource(
                    skill_id=_required_str(arguments.get("skill_id"), "skill_id"),
                    relative_path=_required_str(arguments.get("relative_path"), "relative_path"),
                    max_chars=_optional_int(
                        arguments.get("max_chars"),
                        default=DEFAULT_READ_MAX_CHARS,
                        minimum=1,
                        maximum=MAX_READ_CHARS,
                    ),
                )
        except Exception as exc:
            return ToolInvocationRecord(
                ok=False,
                name=tool_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
        return ToolInvocationRecord(
            ok=True,
            name=tool_name,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            result=result,
        )

    def list_resources(self, *, skill_id: str = "") -> dict[str, Any]:
        skill_ids = (skill_id,) if skill_id else self.selected_skill_ids
        resources_by_skill = []
        for selected_skill_id in skill_ids:
            self._assert_selected_skill(selected_skill_id)
            root = self._skill_root(selected_skill_id)
            resources_by_skill.append(
                {
                    "skill_id": selected_skill_id,
                    "allowed_dirs": list(ALLOWED_RESOURCE_DIRS),
                    "resources": _resource_manifest(root),
                }
            )
        return {"skills": resources_by_skill}

    def read_resource(
        self, *, skill_id: str, relative_path: str, max_chars: int = DEFAULT_READ_MAX_CHARS
    ) -> dict[str, Any]:
        self._assert_selected_skill(skill_id)
        root = self._skill_root(skill_id)
        target = _resolve_allowed_resource(root, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(relative_path)
        size_bytes = target.stat().st_size
        if size_bytes > MAX_TEXT_FILE_BYTES:
            raise SkillResourceError(
                f"Skill resource is too large to read on demand: {relative_path}"
            )
        data = target.read_bytes()
        if _looks_binary(data):
            raise SkillResourceError(f"Skill resource is not a text file: {relative_path}")
        text = data.decode("utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return {
            "skill_id": skill_id,
            "relative_path": _relative_resource_path(root, target),
            "size_bytes": size_bytes,
            "content": text,
            "truncated": truncated,
            "max_chars": max_chars,
        }

    def _assert_selected_skill(self, skill_id: str) -> None:
        if skill_id not in self.selected_skill_ids:
            raise SkillResourceError(f"Skill is not activated for this turn: {skill_id}")

    def _skill_root(self, skill_id: str) -> Path:
        detail = self.skill_store.read_skill(skill_id)
        return Path(str(detail["path"])).resolve().parent


def _resource_manifest(root: Path) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for directory_name in ALLOWED_RESOURCE_DIRS:
        directory = root / directory_name
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            if len(resources) >= MAX_LISTED_RESOURCES_PER_SKILL:
                break
            size_bytes = path.stat().st_size
            resources.append(
                {
                    "relative_path": _relative_resource_path(root, path),
                    "kind": directory_name[:-1] if directory_name.endswith("s") else directory_name,
                    "size_bytes": size_bytes,
                    "readable_text": _is_likely_text_resource(path, size_bytes),
                }
            )
    return resources


def _resolve_allowed_resource(root: Path, relative_path: str) -> Path:
    candidate_path = Path(relative_path)
    if candidate_path.is_absolute():
        raise SkillResourceError("Skill resource path must be relative.")
    parts = candidate_path.parts
    if not parts or parts[0] not in ALLOWED_RESOURCE_DIRS:
        raise SkillResourceError(
            "Skill resource path must start with references/, scripts/, or assets/."
        )
    if any(part in {"", ".", ".."} for part in parts):
        raise SkillResourceError("Skill resource path cannot contain empty, dot, or parent segments.")
    target = (root / candidate_path).resolve()
    if not target.is_relative_to(root):
        raise SkillResourceError("Skill resource path escapes the skill directory.")
    return target


def _relative_resource_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _is_likely_text_resource(path: Path, size_bytes: int) -> bool:
    if size_bytes > MAX_TEXT_FILE_BYTES:
        return False
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return False
    return not _looks_binary(data)


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data


def _required_str(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SkillResourceError(f"{name} is required.")
    return text


def _optional_str(value: Any) -> str:
    return str(value or "").strip()


def _optional_int(
    value: Any, *, default: int, minimum: int, maximum: int
) -> int:
    if value in (None, ""):
        return default
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise SkillResourceError("max_chars must be an integer.") from exc
    return max(minimum, min(maximum, integer))


def _skill_resources_list_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": SKILL_RESOURCES_LIST_OPENAI_NAME,
        "description": (
            "List on-demand resources for skills activated in this turn. Returns only "
            "paths and metadata for references/, scripts/, and assets/; use read for "
            "one text resource when its details are needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Optional activated skill id. Omit to list all activated skills.",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def _skill_resources_read_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": SKILL_RESOURCES_READ_OPENAI_NAME,
        "description": (
            "Read one text resource from an activated skill. Only paths under "
            "references/, scripts/, or assets/ are allowed; read resources only when "
            "the SKILL.md workflow needs that supporting detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "relative_path": {
                    "type": "string",
                    "description": "Skill-relative path such as references/guide.md or scripts/helper.py.",
                },
                "max_chars": {"type": "integer", "default": DEFAULT_READ_MAX_CHARS},
            },
            "required": ["skill_id", "relative_path"],
            "additionalProperties": False,
        },
    }
