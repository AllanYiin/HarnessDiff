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

