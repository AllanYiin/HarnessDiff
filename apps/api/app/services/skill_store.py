from __future__ import annotations

import base64
import json
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.settings import REPO_ROOT, resolve_harnessdiff_home, settings
from app.models.skill import (
    SkillImportFile,
    SkillSummary,
    SubagentCreateRequest,
    SubagentSummary,
    ToolSummary,
)
from app.services.subagent_definitions import (
    DEFAULT_SUBAGENTS,
    SubagentDefinition,
    definition_to_markdown,
    load_subagent_definitions,
    normalize_subagent_tools,
)


DEFAULT_MEMORY_TEXT = """# HarnessDiff Memory

HarnessDiff keeps user-imported skills in `skills/`.
Only the first layer of each skill, name and description, should be loaded into chat context by default.
Open the full `SKILL.md` only when a user explicitly wants that skill or its detailed workflow.
"""

SUBAGENT_DELETED_FILENAME = ".deleted-subagents.json"
TOOL_SETTINGS_FILENAME = "tools.json"

AUTO_SKILL_LIMIT = 3
AUTO_SKILL_MIN_SCORE = 8
REQUESTED_SKILL_DETAILS_MARKER = "Requested skill details:"
SKILL_METADATA_BUDGET_CHARS = 12000
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_CJK_NGRAM_MIN = 2
_CJK_NGRAM_MAX = 6
_STOPWORDS = {
    "and",
    "any",
    "are",
    "ask",
    "asks",
    "for",
    "from",
    "how",
    "into",
    "the",
    "this",
    "that",
    "use",
    "used",
    "user",
    "users",
    "when",
    "with",
    "work",
    "works",
}
_CJK_STOP_TERMS = {
    "使用",
    "使用者",
    "用者",
    "者要",
    "要做",
    "常見",
    "觸發",
    "輸出",
    "適合",
    "不適",
    "不適合",
    "不適用",
    "任務",
    "請求",
    "內容",
    "時使用",
}


class SkillImportError(ValueError):
    pass


class SubagentDefinitionError(ValueError):
    pass


class ToolManagementError(ValueError):
    pass


@dataclass(frozen=True)
class SkillRoot:
    scope: str
    rank: int
    root: Path
    alias: str


@dataclass(frozen=True)
class SkillRecord:
    summary: SkillSummary
    skill_md: Path
    root: SkillRoot
    relative_dir: str


@dataclass(frozen=True)
class SkillActivation:
    id: str
    name: str
    path: str
    content: str
    score: int
    source: str = "selected"
    reason: str = ""
    load_policy: str = "auto"
    required_tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    priority: int = 0


@dataclass(frozen=True)
class SkillStore:
    home_dir: Path = settings.harnessdiff_home
    repo_root: Path = REPO_ROOT

    def __post_init__(self) -> None:
        object.__setattr__(self, "home_dir", resolve_harnessdiff_home(self.home_dir))
        object.__setattr__(self, "repo_root", Path(self.repo_root).expanduser().resolve())

    @property
    def skills_dir(self) -> Path:
        return self.home_dir / "skills"

    @property
    def agents_dir(self) -> Path:
        return self.home_dir / "agents"

    def ensure_dirs(self) -> Path:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        for name in ("CLAUDE.md", "AGENTS.md", "agents.md"):
            path = self.home_dir / name
            if not path.exists():
                path.write_text(DEFAULT_MEMORY_TEXT, encoding="utf-8", newline="\n")
        self._ensure_default_subagents()
        return self.home_dir

    def list_skills(self, *, include_disabled: bool = False) -> list[SkillSummary]:
        self.ensure_dirs()
        return [
            record.summary
            for record in self._discover_skill_records(include_disabled=include_disabled)
        ]

    def read_skill(self, skill_id: str) -> dict[str, str]:
        record = self._record_for_skill_id(skill_id, include_disabled=True)
        if record is None:
            raise FileNotFoundError(skill_id)
        return {
            "id": record.summary.id,
            "path": str(record.skill_md),
            "scope": record.root.scope,
            "root_alias": record.root.alias,
            "relative_path": f"{record.relative_dir}/SKILL.md",
            "content": record.skill_md.read_text(encoding="utf-8"),
        }

    def context_manifest(self) -> str:
        records = self._discover_skill_records()
        if not records:
            return ""
        lines = [
            "Available HarnessDiff skills (metadata layer only; follow progressive disclosure):",
            "- Metadata is always available here: skill name and description only.",
            "- Explicit invocation: if the user writes $skill-id, /skill-id, or clearly names a skill, use that skill.",
            "- Implicit invocation: if the request clearly matches a skill description, use that skill.",
            "- When a skill is activated, apply its SKILL.md body for this turn.",
            "- Bundled references, scripts, and assets are not loaded by default. Use skill.resources.list and skill.resources.read only when the activated SKILL.md workflow needs supporting files.",
        ]
        root_lines = []
        for root in _unique_roots(record.root for record in records):
            root_lines.append(f"- {root.alias} ({root.scope}) = {root.root}")
        if root_lines:
            lines.extend(["Skill roots:", *root_lines])
        for record in records:
            skill = record.summary
            description = f": {skill.description}" if skill.description else ""
            location = f" [{record.root.alias}/{record.relative_dir}]"
            lines.append(f"- ${skill.id} / {skill.name}{description}{location}")
        return _fit_metadata_budget(lines, SKILL_METADATA_BUDGET_CHARS)

    def explicit_skill_ids_for_prompt(self, prompt: str) -> tuple[str, ...]:
        if REQUESTED_SKILL_DETAILS_MARKER in prompt:
            return ()
        explicit_terms = tuple(
            match.group(1)
            for match in re.finditer(r"(?<!\S)[$/]([A-Za-z0-9_.-]+)", prompt)
        )
        if not explicit_terms:
            return ()
        by_key: dict[str, str] = {}
        for skill in self.list_skills():
            for value in (skill.id, skill.name):
                key = _slugify(value)
                if key:
                    by_key[key] = skill.id
        selected: list[str] = []
        for term in explicit_terms:
            skill_id = by_key.get(_slugify(term))
            if skill_id and skill_id not in selected:
                selected.append(skill_id)
        return tuple(selected)

    def select_skills_for_prompt(
        self, prompt: str, *, limit: int = AUTO_SKILL_LIMIT
    ) -> list[SkillActivation]:
        if REQUESTED_SKILL_DETAILS_MARKER in prompt:
            return []
        scored: list[tuple[int, SkillRecord]] = []
        for record in self._discover_skill_records():
            score = _score_skill_prompt(prompt, record.summary)
            if score >= AUTO_SKILL_MIN_SCORE:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], -_parse_skill_md(item[1].skill_md.read_text(encoding="utf-8")).priority, item[1].summary.id))
        activations: list[SkillActivation] = []
        for score, record in scored[:limit]:
            activations.append(
                self._activation_from_record(
                    record,
                    score=score,
                    source="deterministic",
                    reason="matched skill name or description terms",
                )
            )
        return activations

    def skill_selection_candidates(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
            }
            for skill in self.list_skills()
        )

    def activations_for_skill_ids(
        self,
        skill_ids: tuple[str, ...],
        *,
        source: str = "selected",
        reasons: dict[str, str] | None = None,
    ) -> list[SkillActivation]:
        activations: list[SkillActivation] = []
        seen: set[str] = set()
        for skill_id in skill_ids:
            if skill_id in seen:
                continue
            record = self._record_for_skill_id(skill_id)
            if record is None:
                continue
            activations.append(
                self._activation_from_record(
                    record,
                    score=100,
                    source=source,
                    reason=(reasons or {}).get(skill_id, ""),
                )
            )
            seen.add(skill_id)
        return activations

    def auto_skill_context(
        self,
        prompt: str,
        *,
        limit: int = AUTO_SKILL_LIMIT,
        skill_ids: tuple[str, ...] | None = None,
    ) -> str:
        activations = (
            self.activations_for_skill_ids(skill_ids[:limit])
            if skill_ids is not None
            else self.select_skills_for_prompt(prompt, limit=limit)
        )
        if not activations:
            return ""
        blocks = []
        for index, activation in enumerate(activations, start=1):
            blocks.append(
                "\n".join(
                    [
                        f"### Activated skill {index}: {activation.id}",
                        f"Path: {activation.path}",
                        f"Load policy: {activation.load_policy}",
                        _optional_skill_metadata_line("Required tools", activation.required_tools),
                        _optional_skill_metadata_line("Allowed tools", activation.allowed_tools),
                        "Resolve relative paths in this SKILL.md from its containing folder.",
                        "If this skill references bundled references/, scripts/, or assets/, call skill.resources.list then skill.resources.read for the specific activated-skill file needed.",
                        "```markdown",
                        activation.content.replace("```", "`\u200b``"),
                        "```",
                    ]
                )
            )
        return "\n".join(
            [
                "Auto-activated HarnessDiff skill details:",
                "Apply these SKILL.md instructions for this turn because the user request matched the skill name or description.",
                "Do not assume bundled references/scripts/assets are loaded; request individual resource files through skill.resources.* only when needed.",
                *blocks,
            ]
        )

    def skill_activation_metadata(self, skill_id: str) -> dict[str, object]:
        record = self._record_for_skill_id(skill_id)
        if record is None:
            return {}
        activation = self._activation_from_record(record, score=100)
        return {
            "load_policy": activation.load_policy,
            "required_tools": list(activation.required_tools),
            "allowed_tools": list(activation.allowed_tools),
            "priority": activation.priority,
        }

    def agents_context(self) -> str:
        self.ensure_dirs()
        agents_md = self.home_dir / "AGENTS.md"
        if not agents_md.exists():
            return ""
        text = agents_md.read_text(encoding="utf-8").strip()
        if not text:
            return ""
        return "HarnessDiff AGENTS.md instructions:\n" + text

    def subagent_definitions(self) -> tuple[SubagentDefinition, ...]:
        self.ensure_dirs()
        return load_subagent_definitions(self.agents_dir)

    def list_subagents(self) -> list[SubagentSummary]:
        self.ensure_dirs()
        definitions_by_id = {definition.id: definition for definition in self.subagent_definitions()}
        summaries = []
        for subagent_id, definition in sorted(definitions_by_id.items()):
            path = self._subagent_path(subagent_id, must_exist=False)
            summaries.append(_summary_from_subagent_definition(definition, path))
        return summaries

    def create_subagent(self, payload: SubagentCreateRequest) -> SubagentSummary:
        self.ensure_dirs()
        path = self._subagent_path(payload.id, must_exist=False)
        if path.exists():
            raise SubagentDefinitionError(f"Subagent already exists: {payload.id}")
        definition = SubagentDefinition(
            id=payload.id,
            label=payload.label,
            description=payload.description,
            instructions=payload.instructions,
            model=payload.model,
            reasoning_effort=payload.reasoning_effort,
            max_output_chars=payload.max_output_chars,
            tools=normalize_subagent_tools(payload.tools),
            enabled=payload.enabled,
        )
        path.write_text(definition_to_markdown(definition), encoding="utf-8", newline="\n")
        self._unmark_deleted_subagent(payload.id)
        return _summary_from_subagent_definition(definition, path)

    def update_subagent_enabled(self, subagent_id: str, enabled: bool) -> SubagentSummary:
        self.ensure_dirs()
        path = self._subagent_path(subagent_id, must_exist=True)
        definition = load_subagent_definitions(self.agents_dir)
        by_id = {candidate.id: candidate for candidate in definition}
        if subagent_id not in by_id:
            raise SubagentDefinitionError(f"Subagent not found: {subagent_id}")
        _write_frontmatter_enabled(path, enabled)
        refreshed = {
            candidate.id: candidate
            for candidate in load_subagent_definitions(self.agents_dir)
        }.get(subagent_id)
        if refreshed is None:
            raise SubagentDefinitionError(f"Subagent not found: {subagent_id}")
        return _summary_from_subagent_definition(refreshed, path)

    def delete_subagent(self, subagent_id: str) -> None:
        self.ensure_dirs()
        path = self._subagent_path(subagent_id, must_exist=True)
        if path.exists():
            path.unlink()
        self._mark_deleted_subagent(subagent_id)

    def list_tools(self, available_tool_names: tuple[str, ...]) -> list[ToolSummary]:
        self.ensure_dirs()
        settings = self._tool_settings()
        disabled = set(settings.get("disabled", []))
        deleted = set(settings.get("deleted", []))
        return [
            ToolSummary(
                id=tool_name,
                name=tool_name,
                description=_tool_description(tool_name),
                enabled=tool_name not in disabled,
                can_toggle=True,
                can_delete=True,
            )
            for tool_name in dict.fromkeys(available_tool_names)
            if tool_name not in deleted
        ]

    def update_tool_enabled(
        self, tool_id: str, enabled: bool, available_tool_names: tuple[str, ...]
    ) -> ToolSummary:
        if tool_id not in set(available_tool_names):
            raise ToolManagementError(f"Tool not found: {tool_id}")
        settings = self._tool_settings()
        deleted = set(settings.get("deleted", []))
        if tool_id in deleted:
            raise ToolManagementError(f"Tool has been deleted: {tool_id}")
        disabled = set(settings.get("disabled", []))
        if enabled:
            disabled.discard(tool_id)
        else:
            disabled.add(tool_id)
        settings["disabled"] = sorted(disabled)
        self._write_tool_settings(settings)
        for tool in self.list_tools(available_tool_names):
            if tool.id == tool_id:
                return tool
        raise ToolManagementError(f"Tool not found: {tool_id}")

    def delete_tool(self, tool_id: str, available_tool_names: tuple[str, ...]) -> None:
        if tool_id not in set(available_tool_names):
            raise ToolManagementError(f"Tool not found: {tool_id}")
        settings = self._tool_settings()
        disabled = set(settings.get("disabled", []))
        deleted = set(settings.get("deleted", []))
        disabled.add(tool_id)
        deleted.add(tool_id)
        settings["disabled"] = sorted(disabled)
        settings["deleted"] = sorted(deleted)
        self._write_tool_settings(settings)

    def disabled_or_deleted_tool_names(self) -> tuple[str, ...]:
        settings = self._tool_settings()
        return tuple(sorted(set(settings.get("disabled", [])) | set(settings.get("deleted", []))))

    def import_skill_file(self, filename: str, data_base64: str) -> SkillSummary:
        self.ensure_dirs()
        content = _decode_base64(data_base64)
        parsed = _parse_skill_md(content.decode("utf-8", errors="replace"))
        stem = Path(filename).stem or "skill"
        dest = self._available_skill_dir(parsed.name or stem)
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "SKILL.md").write_bytes(content)
        return self._summary_from_skill_md(dest / "SKILL.md")

    def import_folder(self, files: list[SkillImportFile], filename: str) -> SkillSummary:
        self.ensure_dirs()
        if not files:
            raise SkillImportError("Folder import did not include any files.")
        staging = self.skills_dir / f".import-{uuid.uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for item in files:
                target = _safe_join(staging, item.relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_decode_base64(item.data_base64))
            return self._install_from_staging(staging, fallback_name=Path(filename).stem or "skill")
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def import_zip(self, filename: str, data_base64: str) -> SkillSummary:
        self.ensure_dirs()
        archive_path = self.skills_dir / f".import-{uuid.uuid4().hex}.zip"
        staging = self.skills_dir / f".import-{uuid.uuid4().hex}"
        archive_path.write_bytes(_decode_base64(data_base64))
        staging.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    target = _safe_join(staging, info.filename)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source:
                        target.write_bytes(source.read())
            return self._install_from_staging(staging, fallback_name=Path(filename).stem or "skill")
        except zipfile.BadZipFile as exc:
            raise SkillImportError("Invalid zip archive.") from exc
        finally:
            if archive_path.exists():
                archive_path.unlink()
            if staging.exists():
                shutil.rmtree(staging)

    def update_skill_enabled(self, skill_id: str, enabled: bool) -> SkillSummary:
        record = self._record_for_skill_id(skill_id, include_disabled=True)
        if record is None:
            raise FileNotFoundError(skill_id)
        if not record.summary.can_toggle:
            raise SkillImportError(f"Skill cannot be toggled: {skill_id}")
        _write_skill_enabled(record.skill_md, enabled)
        refreshed = self._record_for_skill_id(skill_id, include_disabled=True)
        return (refreshed or record).summary

    def delete_skill(self, skill_id: str) -> None:
        record = self._record_for_skill_id(skill_id, include_disabled=True)
        if record is None:
            raise FileNotFoundError(skill_id)
        if not record.summary.can_delete:
            raise SkillImportError(f"Skill cannot be deleted: {skill_id}")
        skill_dir = record.skill_md.parent.resolve()
        skills_dir = self.skills_dir.resolve()
        if not skill_dir.is_relative_to(skills_dir):
            raise SkillImportError(f"Skill cannot be deleted: {skill_id}")
        shutil.rmtree(skill_dir)

    def _install_from_staging(self, staging: Path, *, fallback_name: str) -> SkillSummary:
        candidates = sorted(staging.rglob("SKILL.md"))
        if not candidates:
            raise SkillImportError("Imported content must contain a SKILL.md file.")
        skill_md = candidates[0]
        summary = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        dest = self._available_skill_dir(summary.name or fallback_name or skill_md.parent.name)
        shutil.copytree(skill_md.parent, dest)
        return self._summary_from_skill_md(dest / "SKILL.md")

    def _summary_from_skill_md(self, skill_md: Path) -> SkillSummary:
        parsed = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        return SkillSummary(
            id=skill_md.parent.name,
            name=parsed.name or skill_md.parent.name,
            description=parsed.description,
            version=parsed.version,
            enabled=parsed.enabled,
            can_toggle=True,
            can_delete=skill_md.parent.resolve().is_relative_to(self.skills_dir.resolve()),
            path=str(skill_md.parent),
        )

    def _activation_from_record(
        self,
        record: SkillRecord,
        *,
        score: int,
        source: str = "selected",
        reason: str = "",
    ) -> SkillActivation:
        detail = self.read_skill(record.summary.id)
        parsed = _parse_skill_md(Path(detail["path"]).read_text(encoding="utf-8"))
        return SkillActivation(
            id=record.summary.id,
            name=record.summary.name,
            path=detail["path"],
            content=detail["content"],
            score=score,
            source=source,
            reason=reason,
            load_policy=parsed.load_policy,
            required_tools=parsed.required_tools,
            allowed_tools=parsed.allowed_tools,
            priority=parsed.priority,
        )

    def _skill_roots(self) -> tuple[SkillRoot, ...]:
        raw_roots = [
            ("project", 0, self.repo_root / ".codex" / "skills"),
            ("project", 0, self.repo_root / ".agents" / "skills"),
            # Backward-compatible import root. It is user-scoped for selection priority.
            ("user", 1, self.skills_dir),
            ("user", 1, self.home_dir.parent / ".agents" / "skills"),
            ("admin", 3, Path("/etc/codex/skills")),
        ]
        roots: list[SkillRoot] = []
        seen: set[Path] = set()
        for scope, rank, raw_root in raw_roots:
            root = raw_root.expanduser().resolve()
            if root in seen or not root.exists():
                continue
            seen.add(root)
            roots.append(SkillRoot(scope=scope, rank=rank, root=root, alias=f"r{len(roots)}"))
        return tuple(roots)

    def _discover_skill_records(self, *, include_disabled: bool = False) -> list[SkillRecord]:
        records: list[SkillRecord] = []
        for root in self._skill_roots():
            for skill_md in sorted(root.root.rglob("SKILL.md")):
                if any(part.startswith(".import-") for part in skill_md.parts):
                    continue
                parsed = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
                if not include_disabled and not parsed.enabled:
                    continue
                relative_dir = _relative_posix(skill_md.parent, root.root)
                records.append(
                    SkillRecord(
                        summary=SkillSummary(
                            id="",
                            name=parsed.name or skill_md.parent.name,
                            description=parsed.description,
                            version=parsed.version,
                            enabled=parsed.enabled,
                            can_toggle=root.scope in {"project", "user"},
                            can_delete=skill_md.parent.resolve().is_relative_to(self.skills_dir.resolve()),
                            path=str(skill_md.parent),
                        ),
                        skill_md=skill_md,
                        root=root,
                        relative_dir=relative_dir,
                    )
                )
        records.sort(
            key=lambda record: (
                record.root.rank,
                record.summary.name.lower(),
                str(record.skill_md).lower(),
            )
        )
        records = _dedupe_skill_records_by_base_id(records)
        return _assign_unique_skill_ids(records)

    def _record_for_skill_id(
        self, skill_id: str, *, include_disabled: bool = False
    ) -> SkillRecord | None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:--[A-Za-z0-9_.-]+)?", skill_id):
            return None
        for record in self._discover_skill_records(include_disabled=include_disabled):
            if record.summary.id == skill_id:
                return record
        return None

    def _available_skill_dir(self, name: str) -> Path:
        base = _slugify(name) or "skill"
        candidate = self.skills_dir / base
        counter = 2
        while candidate.exists():
            candidate = self.skills_dir / f"{base}-{counter}"
            counter += 1
        return candidate

    def _skill_dir(self, skill_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", skill_id):
            raise FileNotFoundError(skill_id)
        path = (self.skills_dir / skill_id).resolve()
        if not path.is_relative_to(self.skills_dir.resolve()):
            raise FileNotFoundError(skill_id)
        return path

    def _ensure_default_subagents(self) -> None:
        deleted = self._deleted_subagent_ids()
        for definition in DEFAULT_SUBAGENTS:
            if definition.id in deleted:
                continue
            path = self.agents_dir / f"{definition.id}.md"
            if not path.exists():
                path.write_text(
                    definition_to_markdown(definition),
                    encoding="utf-8",
                    newline="\n",
                )

    def _deleted_subagent_ids(self) -> set[str]:
        path = self.agents_dir / SUBAGENT_DELETED_FILENAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if not isinstance(data, list):
            return set()
        return {str(item) for item in data if isinstance(item, str)}

    def _write_deleted_subagent_ids(self, subagent_ids: set[str]) -> None:
        path = self.agents_dir / SUBAGENT_DELETED_FILENAME
        path.write_text(
            json.dumps(sorted(subagent_ids), ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    def _mark_deleted_subagent(self, subagent_id: str) -> None:
        deleted = self._deleted_subagent_ids()
        deleted.add(subagent_id)
        self._write_deleted_subagent_ids(deleted)

    def _unmark_deleted_subagent(self, subagent_id: str) -> None:
        deleted = self._deleted_subagent_ids()
        if subagent_id not in deleted:
            return
        deleted.remove(subagent_id)
        self._write_deleted_subagent_ids(deleted)

    def _tool_settings(self) -> dict[str, list[str]]:
        path = self.home_dir / TOOL_SETTINGS_FILENAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"disabled": [], "deleted": []}
        if not isinstance(data, dict):
            return {"disabled": [], "deleted": []}
        return {
            "disabled": _string_list(data.get("disabled")),
            "deleted": _string_list(data.get("deleted")),
        }

    def _write_tool_settings(self, settings: dict[str, list[str]]) -> None:
        path = self.home_dir / TOOL_SETTINGS_FILENAME
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    def _subagent_path(self, subagent_id: str, *, must_exist: bool = True) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", subagent_id):
            raise SubagentDefinitionError(f"Invalid subagent id: {subagent_id}")
        path = (self.agents_dir / f"{subagent_id}.md").resolve()
        if not path.is_relative_to(self.agents_dir.resolve()):
            raise SubagentDefinitionError(f"Invalid subagent id: {subagent_id}")
        if must_exist and not path.exists():
            raise SubagentDefinitionError(f"Subagent not found: {subagent_id}")
        return path


@dataclass(frozen=True)
class ParsedSkill:
    name: str = ""
    description: str = ""
    version: str = ""
    enabled: bool = True
    load_policy: str = "auto"
    required_tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    priority: int = 0


def _parse_skill_md(text: str) -> ParsedSkill:
    metadata: dict[str, str | list[str]] = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        current_list_key = ""
        for line in lines[1:]:
            if line.strip() == "---":
                break
            stripped = line.strip()
            if current_list_key and stripped.startswith("- "):
                values = metadata.setdefault(current_list_key, [])
                if isinstance(values, list):
                    values.append(_strip_yaml_scalar(stripped[2:]))
                continue
            key, sep, value = line.partition(":")
            if sep:
                normalized_key = key.strip().lower()
                scalar = _strip_yaml_scalar(value)
                metadata[normalized_key] = scalar if scalar else []
                current_list_key = normalized_key if not scalar else ""
                continue
            current_list_key = ""
    name = str(metadata.get("name", ""))
    description = str(metadata.get("description", ""))
    version = str(metadata.get("version", ""))
    enabled_value = str(metadata.get("enabled", "true"))
    enabled = enabled_value.strip().lower() not in {"0", "false", "no", "off"}
    load_policy = str(metadata.get("load_policy", metadata.get("load-policy", "auto")) or "auto")
    load_policy = _slugify(load_policy.replace("_", "-")).replace("-", "_") or "auto"
    required_tools = _metadata_list(metadata, "required_tools", "required-tools")
    allowed_tools = _metadata_list(metadata, "allowed_tools", "allowed-tools")
    priority = _metadata_int(metadata.get("priority"), default=0)
    if not name:
        for line in lines:
            if line.startswith("# "):
                name = line[2:].strip()
                break
    if not description:
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped != "---":
                description = stripped[:300]
                break
    return ParsedSkill(
        name=name,
        description=description,
        version=version,
        enabled=enabled,
        load_policy=load_policy,
        required_tools=required_tools,
        allowed_tools=allowed_tools,
        priority=priority,
    )


def _optional_skill_metadata_line(label: str, values: tuple[str, ...]) -> str:
    return f"{label}: {', '.join(values)}" if values else f"{label}: none declared"


def _strip_yaml_scalar(value: str) -> str:
    return value.strip().strip("'\"")


def _metadata_list(metadata: dict[str, str | list[str]], *keys: str) -> tuple[str, ...]:
    for key in keys:
        raw = metadata.get(key)
        if raw is None:
            continue
        if isinstance(raw, list):
            return tuple(item for item in (_strip_yaml_scalar(value) for value in raw) if item)
        value = _strip_yaml_scalar(raw)
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        if "," in value:
            return tuple(item.strip() for item in value.split(",") if item.strip())
        if "(" in value and ")" in value:
            return (value,)
        return tuple(item for item in re.split(r"\s+", value) if item)
    return ()


def _metadata_int(value: str | list[str] | None, *, default: int) -> int:
    if not isinstance(value, str):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _write_skill_enabled(skill_md: Path, enabled: bool) -> None:
    value = "true" if enabled else "false"
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        closing_index = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            ),
            None,
        )
        if closing_index is not None:
            for index in range(1, closing_index):
                key, sep, _ = lines[index].partition(":")
                if sep and key.strip().lower() == "enabled":
                    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
                    lines[index] = f"enabled: {value}{newline}"
                    skill_md.write_text("".join(lines), encoding="utf-8", newline="")
                    return
            newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
            lines.insert(closing_index, f"enabled: {value}{newline}")
            skill_md.write_text("".join(lines), encoding="utf-8", newline="")
            return
    prefix = f"---\nenabled: {value}\n---\n"
    skill_md.write_text(f"{prefix}{text}", encoding="utf-8", newline="")


def _write_frontmatter_enabled(path: Path, enabled: bool) -> None:
    _write_skill_enabled(path, enabled)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if isinstance(item, str) and item.strip()})


def _tool_description(tool_name: str) -> str:
    if tool_name == "harness.subagent.run":
        return "Delegate a focused task to an enabled HarnessDiff subagent."
    if tool_name == "multi_tool_use.parallel":
        return "Run multiple currently allowed HarnessDiff tools concurrently."
    if tool_name == "skill_routing_review":
        return "Review HarnessDiff skill routing and return the fixed Harnessable JSON contract."
    if tool_name.startswith("standard.web."):
        return "Web access and extraction tool."
    if tool_name.startswith("standard.fs."):
        return "Read-only workspace filesystem tool."
    if tool_name.startswith("standard.data."):
        return "Structured data inspection and validation tool."
    if tool_name.startswith("standard.shell."):
        return "Constrained read-only shell tool."
    if tool_name.startswith("standard.code."):
        return "Containerized code execution tool."
    if tool_name.startswith("attachment.pdf."):
        return "Per-run PDF attachment reading tool."
    return "HarnessDiff tool."


def _decode_base64(data: str) -> bytes:
    try:
        return base64.b64decode(data.encode("ascii"), validate=True)
    except Exception as exc:
        raise SkillImportError("Invalid base64 payload.") from exc


def _safe_join(root: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise SkillImportError(f"Unsafe import path: {relative_path}")
    target = (root / Path(*normalized.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise SkillImportError(f"Unsafe import path: {relative_path}")
    return target


def _relative_posix(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.name
    return relative.as_posix() or path.name


def _unique_roots(roots) -> list[SkillRoot]:
    unique: list[SkillRoot] = []
    seen: set[Path] = set()
    for root in roots:
        if root.root in seen:
            continue
        seen.add(root.root)
        unique.append(root)
    return unique


def _assign_unique_skill_ids(records: list[SkillRecord]) -> list[SkillRecord]:
    assigned: list[SkillRecord] = []
    seen: set[str] = set()
    for record in records:
        base_id = _slugify(record.summary.name or Path(record.relative_dir).name) or "skill"
        skill_id = base_id
        if skill_id in seen:
            suffix_base = _slugify(f"{record.root.scope}-{record.relative_dir}") or record.root.alias
            skill_id = f"{base_id}--{suffix_base}"
            counter = 2
            while skill_id in seen:
                skill_id = f"{base_id}--{suffix_base}-{counter}"
                counter += 1
        seen.add(skill_id)
        assigned.append(
            SkillRecord(
                summary=record.summary.model_copy(update={"id": skill_id}),
                skill_md=record.skill_md,
                root=record.root,
                relative_dir=record.relative_dir,
            )
        )
    return assigned


def _dedupe_skill_records_by_base_id(records: list[SkillRecord]) -> list[SkillRecord]:
    deduped: list[SkillRecord] = []
    seen: set[str] = set()
    for record in records:
        base_id = _slugify(record.summary.name or Path(record.relative_dir).name) or "skill"
        if base_id in seen:
            continue
        seen.add(base_id)
        deduped.append(record)
    return deduped


def _fit_metadata_budget(lines: list[str], budget_chars: int) -> str:
    output: list[str] = []
    used = 0
    omitted = 0
    for line in lines:
        line_len = len(line) + 1
        if used + line_len > budget_chars:
            omitted += 1
            continue
        output.append(line)
        used += line_len
    if omitted:
        output.append(f"- ... {omitted} skill metadata lines omitted due to budget.")
    return "\n".join(output)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    return slug[:80]


def _summary_from_subagent_definition(
    definition: SubagentDefinition, path: Path
) -> SubagentSummary:
    return SubagentSummary(
        id=definition.id,
        label=definition.label,
        description=definition.description,
        model=definition.model,
        reasoning_effort=definition.reasoning_effort,
        max_output_chars=definition.max_output_chars,
        tools=list(definition.tools),
        enabled=definition.enabled,
        can_toggle=True,
        can_delete=True,
        path=str(path),
    )


def _score_skill_prompt(prompt: str, skill: SkillSummary) -> int:
    prompt_text = _normalize_text(prompt)
    if not prompt_text:
        return 0
    aliases = {_normalize_text(skill.id), _normalize_text(skill.name)}
    aliases = {alias for alias in aliases if alias}
    for alias in aliases:
        if _contains_term(prompt_text, alias):
            return 100

    matched_terms = []
    for term in _routing_terms(skill.name, skill.description):
        if _contains_term(prompt_text, term):
            matched_terms.append(term)

    if not matched_terms:
        return 0
    score = sum(_term_score(term) for term in matched_terms)
    if len(matched_terms) == 1 and not _is_strong_single_match(matched_terms[0]):
        return 0
    return score


def _routing_terms(*values: str) -> set[str]:
    text = _normalize_text(" ".join(values))
    terms = {
        match.group(0)
        for match in _WORD_RE.finditer(text)
        if match.group(0) not in _STOPWORDS
    }
    for match in _CJK_RE.finditer(text):
        terms.update(_cjk_routing_terms(match.group(0)))
    return terms


def _normalize_text(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^a-z0-9_.\-\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    if _CJK_RE.fullmatch(term):
        return term in text
    return re.search(rf"(?<![a-z0-9_.-]){re.escape(term)}(?![a-z0-9_.-])", text) is not None


def _cjk_routing_terms(text: str) -> set[str]:
    terms: set[str] = set()
    if _is_signal_cjk_term(text) and len(text) <= 12:
        terms.add(text)
    max_size = min(_CJK_NGRAM_MAX, len(text))
    for size in range(_CJK_NGRAM_MIN, max_size + 1):
        for index in range(0, len(text) - size + 1):
            term = text[index : index + size]
            if _is_signal_cjk_term(term):
                terms.add(term)
    return terms


def _is_signal_cjk_term(term: str) -> bool:
    if len(term) < _CJK_NGRAM_MIN or term in _CJK_STOP_TERMS:
        return False
    if term.startswith(("使用", "常見", "不適")) or term.endswith(("使用", "觸發")):
        return False
    return not all(char in "在當要做的是和或與及以用者請幫我此這" for char in term)


def _term_score(term: str) -> int:
    if _CJK_RE.fullmatch(term):
        return min(12, len(term) * 2)
    return 4 if len(term) >= 8 else 3


def _is_strong_single_match(term: str) -> bool:
    if _CJK_RE.fullmatch(term):
        return len(term) >= 4
    return len(term) >= 8
