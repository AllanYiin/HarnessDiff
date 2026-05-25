from __future__ import annotations

import base64
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.settings import resolve_harnessdiff_home, settings
from app.models.skill import SkillImportFile, SubagentCreateRequest, SubagentSummary, SkillSummary
from app.services.subagent_definitions import (
    DEFAULT_SUBAGENTS,
    SubagentDefinition,
    definition_to_markdown,
    load_subagent_definitions,
)


DEFAULT_MEMORY_TEXT = """# HarnessDiff Memory

HarnessDiff keeps user-imported skills in `skills/`.
Only the first layer of each skill, name and description, should be loaded into chat context by default.
Open the full `SKILL.md` only when a user explicitly wants that skill or its detailed workflow.
"""


class SkillImportError(ValueError):
    pass


class SubagentDefinitionError(ValueError):
    pass


@dataclass(frozen=True)
class SkillStore:
    home_dir: Path = settings.harnessdiff_home

    def __post_init__(self) -> None:
        object.__setattr__(self, "home_dir", resolve_harnessdiff_home(self.home_dir))

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

    def list_skills(self) -> list[SkillSummary]:
        self.ensure_dirs()
        skills = []
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            skills.append(self._summary_from_skill_md(skill_md))
        return skills

    def read_skill(self, skill_id: str) -> dict[str, str]:
        skill_dir = self._skill_dir(skill_id)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(skill_id)
        return {
            "id": skill_dir.name,
            "path": str(skill_md),
            "content": skill_md.read_text(encoding="utf-8"),
        }

    def context_manifest(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [
            "Available HarnessDiff skills (first layer only; full SKILL.md is loaded on demand):"
        ]
        for skill in skills:
            description = f": {skill.description}" if skill.description else ""
            lines.append(f"- {skill.name}{description}")
        return "\n".join(lines)

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
        definitions = load_subagent_definitions(self.agents_dir)
        return definitions or DEFAULT_SUBAGENTS

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
            enabled=payload.enabled,
        )
        path.write_text(definition_to_markdown(definition), encoding="utf-8", newline="\n")
        return _summary_from_subagent_definition(definition, path)

    def import_skill_file(self, filename: str, data_base64: str) -> SkillSummary:
        self.ensure_dirs()
        content = _decode_base64(data_base64)
        stem = Path(filename).stem or "skill"
        dest = self._available_skill_dir(stem)
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
            path=str(skill_md.parent),
        )

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
        for definition in DEFAULT_SUBAGENTS:
            path = self.agents_dir / f"{definition.id}.md"
            if not path.exists():
                path.write_text(
                    definition_to_markdown(definition),
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


def _parse_skill_md(text: str) -> ParsedSkill:
    metadata: dict[str, str] = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, sep, value = line.partition(":")
            if sep:
                metadata[key.strip().lower()] = value.strip().strip('"')
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    version = metadata.get("version", "")
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
    return ParsedSkill(name=name, description=description, version=version)


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
        enabled=definition.enabled,
        path=str(path),
    )
