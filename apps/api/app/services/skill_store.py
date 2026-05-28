from __future__ import annotations

import base64
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.settings import REPO_ROOT, resolve_harnessdiff_home, settings
from app.models.skill import SkillImportFile, SubagentCreateRequest, SubagentSummary, SkillSummary
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

    def list_skills(self) -> list[SkillSummary]:
        self.ensure_dirs()
        return [record.summary for record in self._discover_skill_records()]

    def read_skill(self, skill_id: str) -> dict[str, str]:
        record = self._record_for_skill_id(skill_id)
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
            "- Explicit invocation: if the user writes $skill-id or clearly names a skill, use that skill.",
            "- Implicit invocation: if the request clearly matches a skill description, use that skill.",
            "- When a skill is activated, apply its SKILL.md body for this turn.",
            "- Load bundled references, scripts, and assets only when needed; prefer running or patching scripts over retyping large code blocks.",
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
        explicit_terms = tuple(match.group(1) for match in re.finditer(r"\$([A-Za-z0-9_.-]+)", prompt))
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
        scored: list[tuple[int, SkillSummary]] = []
        for skill in self.list_skills():
            score = _score_skill_prompt(prompt, skill)
            if score >= AUTO_SKILL_MIN_SCORE:
                scored.append((score, skill))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        activations: list[SkillActivation] = []
        for score, skill in scored[:limit]:
            detail = self.read_skill(skill.id)
            activations.append(
                SkillActivation(
                    id=skill.id,
                    name=skill.name,
                    path=detail["path"],
                    content=detail["content"],
                    score=score,
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

    def activations_for_skill_ids(self, skill_ids: tuple[str, ...]) -> list[SkillActivation]:
        activations: list[SkillActivation] = []
        seen: set[str] = set()
        for skill_id in skill_ids:
            if skill_id in seen:
                continue
            record = self._record_for_skill_id(skill_id)
            if record is None:
                continue
            try:
                detail = self.read_skill(skill_id)
            except FileNotFoundError:
                continue
            skill_md = Path(detail["path"])
            summary = record.summary
            activations.append(
                SkillActivation(
                    id=skill_id,
                    name=summary.name,
                    path=detail["path"],
                    content=detail["content"],
                    score=100,
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
                        "Resolve relative paths in this SKILL.md from its containing folder.",
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
                *blocks,
            ]
        )

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
            tools=normalize_subagent_tools(payload.tools),
            enabled=payload.enabled,
        )
        path.write_text(definition_to_markdown(definition), encoding="utf-8", newline="\n")
        return _summary_from_subagent_definition(definition, path)

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

    def _discover_skill_records(self) -> list[SkillRecord]:
        records: list[SkillRecord] = []
        for root in self._skill_roots():
            for skill_md in sorted(root.root.rglob("SKILL.md")):
                if any(part.startswith(".import-") for part in skill_md.parts):
                    continue
                parsed = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
                if not parsed.enabled:
                    continue
                relative_dir = _relative_posix(skill_md.parent, root.root)
                records.append(
                    SkillRecord(
                        summary=SkillSummary(
                            id="",
                            name=parsed.name or skill_md.parent.name,
                            description=parsed.description,
                            version=parsed.version,
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

    def _record_for_skill_id(self, skill_id: str) -> SkillRecord | None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:--[A-Za-z0-9_.-]+)?", skill_id):
            return None
        for record in self._discover_skill_records():
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
    enabled: bool = True


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
    enabled = metadata.get("enabled", "true").strip().lower() not in {"0", "false", "no", "off"}
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
    return ParsedSkill(name=name, description=description, version=version, enabled=enabled)


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
