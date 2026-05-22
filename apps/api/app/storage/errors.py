from __future__ import annotations

from pathlib import Path


class ProjectNotFoundError(Exception):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project not found: {project_id}")
        self.project_id = project_id


class InvalidProjectIdError(Exception):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Invalid project id: {project_id}")
        self.project_id = project_id


class StorageCorruptionError(Exception):
    def __init__(self, project_id: str, report_path: Path) -> None:
        super().__init__(f"Project storage is corrupt: {project_id}")
        self.project_id = project_id
        self.report_path = report_path

