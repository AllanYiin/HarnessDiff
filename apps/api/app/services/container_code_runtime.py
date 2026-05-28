from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTAINER_CODE_TOOL_NAME = "standard.code.container_exec"
DEFAULT_CODE_IMAGE = "harnessdiff-code-runtime:latest"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 300
MAX_COMMAND_CHARS = 6000
MAX_OUTPUT_CHARS = 12000

_COPY_IGNORED_NAMES = {
    ".compile_pycache",
    ".env",
    ".env.local",
    ".git",
    ".idea",
    ".launcher.env",
    ".mypy_cache",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "dist",
    "htmlcov",
    "logs",
    "playwright-report",
    "release",
    "test-results",
}

_SENSITIVE_ENV_PREFIXES = (
    "OPENAI_",
    "ANTHROPIC_",
    "AZURE_",
    "AWS_",
    "GOOGLE_",
    "GCP_",
    "SERPAPI_",
)


@dataclass(frozen=True)
class DockerRuntimeStatus:
    available: bool
    docker_found: bool
    daemon_available: bool
    image_present: bool
    image: str
    message: str = ""

    def model_dump(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "docker_found": self.docker_found,
            "daemon_available": self.daemon_available,
            "image_present": self.image_present,
            "image": self.image,
            "message": self.message,
        }


class ContainerCodeExecutor:
    """Runs development commands in an offline Docker container copy of the repo."""

    def __init__(
        self,
        root: Path,
        *,
        image: str = DEFAULT_CODE_IMAGE,
        dockerfile: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.image = image
        self.dockerfile = dockerfile or self.root / "docker" / "code-runtime" / "Dockerfile"

    def status(self) -> dict[str, Any]:
        return self._status(build_if_missing=False).model_dump()

    def run(
        self,
        command: str,
        workdir: str = ".",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        command = str(command or "").strip()
        if not command:
            return self._error_result("missing_command", "command is required", started)
        if len(command) > MAX_COMMAND_CHARS:
            return self._error_result(
                "command_too_long",
                f"command must be {MAX_COMMAND_CHARS} characters or fewer",
                started,
                command=command[:200],
            )

        timeout_seconds = _coerce_timeout(timeout_seconds)
        workdir_result = self._normalize_workdir(workdir)
        if isinstance(workdir_result, dict):
            return self._error_result(
                workdir_result["type"],
                workdir_result["message"],
                started,
                command=command,
                workdir=str(workdir or "."),
            )

        status = self._status(build_if_missing=True)
        if not status.available:
            return self._error_result(
                "container_runtime_unavailable",
                status.message or "Docker container runtime is unavailable.",
                started,
                command=command,
                workdir=workdir_result,
                extra=status.model_dump(),
            )

        with tempfile.TemporaryDirectory(prefix="harnessdiff-code-") as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            try:
                shutil.copytree(self.root, workspace, ignore=self._copy_ignore)
            except OSError as exc:
                return self._error_result(
                    "workspace_copy_failed",
                    str(exc),
                    started,
                    command=command,
                    workdir=workdir_result,
                )

            local_workdir = (workspace / workdir_result).resolve()
            try:
                local_workdir.relative_to(workspace)
            except ValueError:
                return self._error_result(
                    "invalid_workdir",
                    "workdir escapes the temporary workspace",
                    started,
                    command=command,
                    workdir=workdir_result,
                )
            if not local_workdir.is_dir():
                return self._error_result(
                    "invalid_workdir",
                    f"workdir does not exist in the temporary workspace: {workdir_result}",
                    started,
                    command=command,
                    workdir=workdir_result,
                )

            container_name = f"harnessdiff-code-{uuid.uuid4().hex[:12]}"
            argv = self.build_docker_run_args(
                workspace=workspace,
                command=command,
                workdir=workdir_result,
                timeout_seconds=timeout_seconds,
                container_name=container_name,
            )
            try:
                completed = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds + 30,
                    env=self._host_env(),
                )
                exit_code = int(completed.returncode)
                stdout, stdout_truncated = _limit_text(completed.stdout or "")
                stderr, stderr_truncated = _limit_text(completed.stderr or "")
            except subprocess.TimeoutExpired as exc:
                self._remove_container(container_name)
                exit_code = 124
                stdout, stdout_truncated = _limit_text(exc.stdout or "")
                stderr, stderr_truncated = _limit_text(
                    (exc.stderr or "") + "\ncontainer execution timed out"
                )

            return {
                "command": command,
                "workdir": workdir_result,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_truncated or stderr_truncated,
                "elapsed_ms": _elapsed_ms(started),
                "image": self.image,
                "network": "none",
            }

    def build_docker_run_args(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
        container_name: str,
    ) -> list[str]:
        container_workdir = "/workspace" if workdir == "." else f"/workspace/{workdir}"
        timeout_command = (
            f"timeout --kill-after=5s {timeout_seconds}s "
            f"bash -lc {shlex.quote(command)}"
        )
        return [
            self._docker_binary() or "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--pids-limit",
            "256",
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "-e",
            "CI=1",
            "-e",
            "NO_COLOR=1",
            "-v",
            f"{workspace.resolve()}:/workspace",
            "-w",
            container_workdir,
            self.image,
            "bash",
            "-lc",
            timeout_command,
        ]

    def _status(self, *, build_if_missing: bool) -> DockerRuntimeStatus:
        docker = self._docker_binary()
        if not docker:
            return DockerRuntimeStatus(
                available=False,
                docker_found=False,
                daemon_available=False,
                image_present=False,
                image=self.image,
                message="Docker CLI was not found on PATH.",
            )

        daemon = self._run_quiet([docker, "version", "--format", "{{.Server.Version}}"])
        if daemon.returncode != 0:
            return DockerRuntimeStatus(
                available=False,
                docker_found=True,
                daemon_available=False,
                image_present=False,
                image=self.image,
                message=(daemon.stderr or daemon.stdout or "Docker daemon is unavailable.").strip(),
            )

        image = self._run_quiet([docker, "image", "inspect", self.image])
        if image.returncode == 0:
            return DockerRuntimeStatus(True, True, True, True, self.image)

        if not build_if_missing:
            return DockerRuntimeStatus(
                available=False,
                docker_found=True,
                daemon_available=True,
                image_present=False,
                image=self.image,
                message=f"Docker image is not built: {self.image}",
            )

        if not self.dockerfile.is_file():
            return DockerRuntimeStatus(
                available=False,
                docker_found=True,
                daemon_available=True,
                image_present=False,
                image=self.image,
                message=f"Dockerfile not found: {self.dockerfile}",
            )
        build = self._run_quiet(
            [
                docker,
                "build",
                "-t",
                self.image,
                "-f",
                str(self.dockerfile),
                str(self.dockerfile.parent),
            ],
            timeout=600,
        )
        if build.returncode != 0:
            return DockerRuntimeStatus(
                available=False,
                docker_found=True,
                daemon_available=True,
                image_present=False,
                image=self.image,
                message=(build.stderr or build.stdout or "Docker image build failed.").strip(),
            )
        return DockerRuntimeStatus(True, True, True, True, self.image)

    def _run_quiet(
        self,
        argv: list[str],
        *,
        timeout: int = 10,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self._host_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(argv, 1, "", str(exc))

    def _remove_container(self, container_name: str) -> None:
        docker = self._docker_binary()
        if not docker:
            return
        subprocess.run(
            [docker, "rm", "-f", container_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=self._host_env(),
        )

    def _docker_binary(self) -> str | None:
        return shutil.which("docker")

    def _host_env(self) -> dict[str, str]:
        safe: dict[str, str] = {}
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "DOCKER_HOST"):
            value = os.environ.get(key)
            if value:
                safe[key] = value
        return safe

    def _normalize_workdir(self, workdir: str) -> str | dict[str, str]:
        value = str(workdir or ".").replace("\\", "/").strip()
        if value in {"", "."}:
            return "."
        candidate = Path(value)
        if candidate.is_absolute():
            return {"type": "invalid_workdir", "message": "workdir must be relative"}
        normalized = Path(".")
        for part in candidate.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                return {
                    "type": "invalid_workdir",
                    "message": "workdir cannot contain parent-directory segments",
                }
            normalized = normalized / part
        return normalized.as_posix()

    def _copy_ignore(self, directory: str, names: list[str]) -> set[str]:
        current = Path(directory).resolve()
        ignored = {name for name in names if name in _COPY_IGNORED_NAMES}
        try:
            relative = current.relative_to(self.root)
        except ValueError:
            relative = Path(".")
        if relative.as_posix() == "data" and "projects" in names:
            ignored.add("projects")
        return ignored

    def _error_result(
        self,
        error_type: str,
        message: str,
        started: float,
        *,
        command: str = "",
        workdir: str = ".",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "command": command,
            "workdir": workdir,
            "exit_code": 127,
            "stdout": "",
            "stderr": message,
            "truncated": False,
            "elapsed_ms": _elapsed_ms(started),
            "image": self.image,
            "network": "none",
            "error": {"type": error_type, "message": message},
        }
        if extra:
            result["runtime"] = extra
        return result


def _coerce_timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    return min(MAX_TIMEOUT_SECONDS, max(1, timeout))


def _limit_text(value: str, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[: limit - 18] + "\n...[truncated]...", True


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def env_key_is_sensitive(key: str) -> bool:
    return key.upper().endswith(("_KEY", "_TOKEN", "_SECRET")) or key.upper().startswith(
        _SENSITIVE_ENV_PREFIXES
    )
