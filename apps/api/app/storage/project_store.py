from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.core.settings import settings
from app.models.project import ProjectCreate, ProjectDocument, ProjectUpdate, utc_now_iso
from app.models.run import RunCreate, RunDocument, RunStatus, new_run_document
from app.providers.base import ProviderEvent
from app.storage.errors import InvalidProjectIdError, ProjectNotFoundError, StorageCorruptionError
from app.storage.json_io import read_json, write_json_atomic

PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ProjectStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = (data_dir or settings.data_dir).resolve()
        self.projects_dir = self.data_dir / "projects"

    def ensure_dirs(self) -> Path:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def list_projects(self) -> list[ProjectDocument]:
        self.ensure_dirs()
        projects: list[ProjectDocument] = []
        for project_dir in sorted(self.projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            try:
                projects.append(self._read_project_document(project_dir.name))
            except (ProjectNotFoundError, StorageCorruptionError, InvalidProjectIdError):
                continue
        return sorted(projects, key=lambda project: project.updated_at, reverse=True)

    def create_project(self, payload: ProjectCreate) -> ProjectDocument:
        self.ensure_dirs()
        now = utc_now_iso()
        project = ProjectDocument(
            schema_version=settings.schema_version,
            id=self._new_project_id(),
            name=payload.name,
            surface_type=payload.surface_type,
            config_profile=payload.config_profile,
            created_at=now,
            updated_at=now,
        )
        project_dir = self._project_dir(project.id, must_exist=False)
        (project_dir / "config").mkdir(parents=True, exist_ok=False)
        (project_dir / "runs").mkdir(parents=True, exist_ok=True)
        write_json_atomic(project_dir / "project.json", project.model_dump(mode="json"))
        write_json_atomic(
            project_dir / "config" / "harness.default.json",
            self._default_harness_config(project.schema_version),
        )
        return project

    def get_project(self, project_id: str) -> ProjectDocument:
        return self._read_project_document(project_id)

    def update_project(self, project_id: str, payload: ProjectUpdate) -> ProjectDocument:
        project = self._read_project_document(project_id)
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return project
        updated = project.model_copy(update={**update_data, "updated_at": utc_now_iso()})
        project_dir = self._project_dir(project_id)
        write_json_atomic(project_dir / "project.json", updated.model_dump(mode="json"))
        return updated

    def delete_project(self, project_id: str) -> None:
        project_dir = self._project_dir(project_id)
        if not self._is_inside_projects_dir(project_dir):
            raise InvalidProjectIdError(project_id)
        shutil.rmtree(project_dir)

    def create_run(self, project_id: str, payload: RunCreate) -> RunDocument:
        self._read_project_document(project_id)
        runs_dir = self._project_dir(project_id) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        harness_modules = self._effective_harness_modules(project_id, payload.harness_modules)
        run = new_run_document(
            schema_version=settings.schema_version,
            run_id=self._new_run_id(runs_dir),
            project_id=project_id,
            turn_index=self._next_turn_index(runs_dir),
            payload=payload,
            harness_modules=harness_modules,
        )
        run_dir = runs_dir / run.id
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json_atomic(run_dir / "run.json", run.model_dump(mode="json"))
        return run

    def get_run(self, run_id: str) -> RunDocument:
        run_path = self._find_run_path(run_id)
        data = read_json(run_path)
        return RunDocument.model_validate(data)

    def get_run_dir(self, project_id: str, run_id: str) -> Path:
        return self._run_dir(project_id, run_id)

    def list_run_dirs(self, project_id: str) -> list[Path]:
        runs_dir = self._project_dir(project_id) / "runs"
        if not runs_dir.exists():
            return []
        return sorted(
            [child for child in runs_dir.iterdir() if child.is_dir()],
            key=lambda child: int(read_json(child / "run.json").get("turn_index", 0))
            if (child / "run.json").exists()
            else 0,
        )

    def write_run_analysis(self, project_id: str, run_id: str, analysis: dict[str, Any]) -> None:
        analysis_dir = self._run_dir(project_id, run_id) / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(analysis_dir / "analysis.json", analysis)

    def read_run_analysis(self, project_id: str, run_id: str) -> dict[str, Any]:
        analysis_path = self._run_dir(project_id, run_id) / "analysis" / "analysis.json"
        if not analysis_path.exists():
            raise ProjectNotFoundError(run_id)
        data = read_json(analysis_path)
        return data if isinstance(data, dict) else {}

    def update_run_status(self, project_id: str, run_id: str, status: RunStatus) -> RunDocument:
        run_dir = self._run_dir(project_id, run_id)
        run = RunDocument.model_validate(read_json(run_dir / "run.json"))
        updated = run.model_copy(update={"status": status, "updated_at": utc_now_iso()})
        write_json_atomic(run_dir / "run.json", updated.model_dump(mode="json"))
        return updated

    def prepare_pane_run(
        self,
        project_id: str,
        run_id: str,
        pane: str,
        prompt: str,
        instructions: str,
        harness_modules: dict[str, bool],
    ) -> None:
        pane_dir = self._run_dir(project_id, run_id) / pane
        pane_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            pane_dir / "input.json",
            {
                "schema_version": settings.schema_version,
                "pane": pane,
                "prompt": prompt,
                "instructions": instructions,
                "harness_modules": harness_modules if pane == "Harness" else {},
                "created_at": utc_now_iso(),
            },
        )
        output_path = pane_dir / "output.json"
        if not output_path.exists():
            write_json_atomic(
                output_path,
                {
                    "schema_version": settings.schema_version,
                    "pane": pane,
                    "text": "",
                    "updated_at": utc_now_iso(),
                },
            )

    def append_pane_event(
        self, project_id: str, run_id: str, pane: str, event: ProviderEvent
    ) -> None:
        event_payload = {
            "schema_version": settings.schema_version,
            "type": event.type,
            "pane": event.pane,
            "sequence": event.sequence,
            "text": event.text,
            "response_id": event.response_id,
            "usage": event.usage,
            "raw": event.raw,
            "created_at": utc_now_iso(),
        }
        self._append_jsonl(self._run_dir(project_id, run_id) / pane / "events.jsonl", event_payload)

    def append_error_event(
        self, project_id: str, run_id: str, pane: str, error_payload: dict[str, Any]
    ) -> None:
        self._append_jsonl(
            self._run_dir(project_id, run_id) / pane / "events.jsonl",
            {
                "schema_version": settings.schema_version,
                **error_payload,
                "created_at": utc_now_iso(),
            },
        )

    def append_pane_output_delta(self, project_id: str, run_id: str, pane: str, text: str) -> None:
        output_path = self._run_dir(project_id, run_id) / pane / "output.json"
        output = read_json(output_path)
        output["text"] = f"{output.get('text', '')}{text}"
        output["updated_at"] = utc_now_iso()
        write_json_atomic(output_path, output)

    def write_pane_usage(
        self, project_id: str, run_id: str, pane: str, usage: dict[str, Any]
    ) -> None:
        write_json_atomic(
            self._run_dir(project_id, run_id) / pane / "usage.json",
            {
                "schema_version": settings.schema_version,
                "pane": pane,
                "usage": usage,
                "created_at": utc_now_iso(),
            },
        )

    def _read_project_document(self, project_id: str) -> ProjectDocument:
        project_dir = self._project_dir(project_id)
        project_path = project_dir / "project.json"
        if not project_path.exists():
            raise ProjectNotFoundError(project_id)
        try:
            data = read_json(project_path)
            return ProjectDocument.model_validate(data)
        except (json.JSONDecodeError, ValueError, ValidationError):
            report_path = self._write_repair_report(project_id, project_dir, project_path)
            raise StorageCorruptionError(project_id, report_path) from None

    def _project_dir(self, project_id: str, must_exist: bool = True) -> Path:
        if not PROJECT_ID_RE.match(project_id):
            raise InvalidProjectIdError(project_id)
        path = (self.projects_dir / project_id).resolve()
        if not self._is_inside_projects_dir(path):
            raise InvalidProjectIdError(project_id)
        if must_exist and not path.exists():
            raise ProjectNotFoundError(project_id)
        return path

    def _is_inside_projects_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.projects_dir.resolve())
        except ValueError:
            return False
        return True

    def _new_project_id(self) -> str:
        while True:
            project_id = f"proj_{uuid4().hex[:16]}"
            if not (self.projects_dir / project_id).exists():
                return project_id

    def _new_run_id(self, runs_dir: Path) -> str:
        while True:
            run_id = f"run_{uuid4().hex[:16]}"
            if not (runs_dir / run_id).exists():
                return run_id

    def _next_turn_index(self, runs_dir: Path) -> int:
        if not runs_dir.exists():
            return 0
        return sum(1 for child in runs_dir.iterdir() if child.is_dir())

    def _run_dir(self, project_id: str, run_id: str) -> Path:
        if not PROJECT_ID_RE.match(run_id):
            raise InvalidProjectIdError(run_id)
        run_dir = (self._project_dir(project_id) / "runs" / run_id).resolve()
        project_dir = self._project_dir(project_id).resolve()
        try:
            run_dir.relative_to(project_dir)
        except ValueError:
            raise InvalidProjectIdError(run_id) from None
        if not run_dir.exists():
            raise ProjectNotFoundError(run_id)
        return run_dir

    def _find_run_path(self, run_id: str) -> Path:
        if not PROJECT_ID_RE.match(run_id):
            raise InvalidProjectIdError(run_id)
        self.ensure_dirs()
        for project_dir in self.projects_dir.iterdir():
            run_path = project_dir / "runs" / run_id / "run.json"
            if run_path.exists():
                return run_path
        raise ProjectNotFoundError(run_id)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    def _write_repair_report(self, project_id: str, project_dir: Path, project_path: Path) -> Path:
        report_path = project_dir / "repair-report.json"
        report: dict[str, Any] = {
            "schema_version": settings.schema_version,
            "project_id": project_id,
            "status": "corrupt",
            "file": str(project_path),
            "message": "project.json could not be decoded or validated.",
            "created_at": utc_now_iso(),
        }
        write_json_atomic(report_path, report)
        return report_path

    def _default_harness_config(self, schema_version: str) -> dict[str, Any]:
        return {
            "schema_version": schema_version,
            "profile": "harness.default",
            "modules": {
                "context_manifest": {"enabled": True},
                "source_map": {"enabled": True},
                "guardrails": {"enabled": True},
                "output_contract": {"enabled": True},
                "planning_preamble": {"enabled": False},
                "tool_policy": {"enabled": True},
                "memory_selection": {"enabled": True},
                "post_answer_critique": {"enabled": True},
                "token_budgeter": {"enabled": True},
            },
        }

    def _effective_harness_modules(
        self, project_id: str, overrides: dict[str, bool] | None
    ) -> dict[str, bool]:
        config_path = self._project_dir(project_id) / "config" / "harness.default.json"
        if config_path.exists():
            config = read_json(config_path)
        else:
            config = self._default_harness_config(settings.schema_version)
        modules = {
            name: bool(value.get("enabled", False))
            for name, value in config.get("modules", {}).items()
            if isinstance(value, dict)
        }
        if overrides:
            modules.update({name: bool(enabled) for name, enabled in overrides.items()})
        return modules
