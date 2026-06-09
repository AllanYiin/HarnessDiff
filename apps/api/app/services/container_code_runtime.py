from __future__ import annotations

import hashlib
import json
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
CODE_RUNTIME_BACKEND_ENV = "HARNESSDIFF_CODE_RUNTIME_BACKEND"
MXC_EXPERIMENTAL_ENV = "HARNESSDIFF_MXC_EXPERIMENTAL"
MXC_RUNNER_NAME = "mxc_code_runner.mjs"
MXC_POLICY_VERSION = "0.6.0-alpha"
MXC_PREVIEW_WARNING = (
    "Microsoft MXC support is experimental. The upstream MXC repository currently "
    "describes this as an early preview and says MXC profiles should not be "
    "treated as security boundaries."
)

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
    """Runs development commands in an isolated temporary copy of the repo."""

    def __init__(
        self,
        root: Path,
        *,
        image: str = DEFAULT_CODE_IMAGE,
        dockerfile: Path | None = None,
        backend: str | None = None,
        mxc_runner: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.backend_mode = _normalize_backend(backend or os.environ.get(CODE_RUNTIME_BACKEND_ENV))
        self.docker_backend = DockerCodeExecutor(self.root, image=image, dockerfile=dockerfile)
        self.mxc_backend = MxcCodeExecutor(
            self.root,
            runner=mxc_runner or Path(__file__).with_name(MXC_RUNNER_NAME),
        )

    @property
    def image(self) -> str:
        return self.docker_backend.image

    @property
    def dockerfile(self) -> Path:
        return self.docker_backend.dockerfile

    def status(self) -> dict[str, Any]:
        docker_status = self.docker_backend.status(build_if_missing=False).model_dump()
        payload = {
            **docker_status,
            "backend_mode": self.backend_mode,
            "selected_backend": "docker",
            "backends": {"docker": docker_status},
        }
        if self.backend_mode in {"mxc", "auto"}:
            mxc_status = self.mxc_backend.status()
            payload["backends"]["mxc"] = mxc_status
            if self.backend_mode == "mxc":
                payload.update(
                    {
                        "available": bool(mxc_status.get("available")),
                        "selected_backend": "mxc",
                        "runtime_backend": "mxc",
                        "message": mxc_status.get("message", ""),
                    }
                )
            elif mxc_status.get("available"):
                payload["selected_backend"] = "mxc"
        return payload

    def run(
        self,
        command: str,
        workdir: str = ".",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        command = str(command or "").strip()
        if not command:
            return _error_result(
                "missing_command",
                "command is required",
                started,
                backend=self.backend_mode,
            )
        if len(command) > MAX_COMMAND_CHARS:
            return _error_result(
                "command_too_long",
                f"command must be {MAX_COMMAND_CHARS} characters or fewer",
                started,
                command=command[:200],
                backend=self.backend_mode,
            )

        timeout_seconds = _coerce_timeout(timeout_seconds)
        workdir_result = self._normalize_workdir(workdir)
        if isinstance(workdir_result, dict):
            return _error_result(
                workdir_result["type"],
                workdir_result["message"],
                started,
                command=command,
                workdir=str(workdir or "."),
                backend=self.backend_mode,
            )

        backend, fallback = self._select_backend_for_run()

        with tempfile.TemporaryDirectory(prefix="harnessdiff-code-") as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            try:
                shutil.copytree(self.root, workspace, ignore=self._copy_ignore)
            except OSError as exc:
                return _error_result(
                    "workspace_copy_failed",
                    str(exc),
                    started,
                    command=command,
                    workdir=workdir_result,
                    backend=backend.name,
                )

            local_workdir = (workspace / workdir_result).resolve()
            try:
                local_workdir.relative_to(workspace)
            except ValueError:
                return _error_result(
                    "invalid_workdir",
                    "workdir escapes the temporary workspace",
                    started,
                    command=command,
                    workdir=workdir_result,
                    backend=backend.name,
                )
            if not local_workdir.is_dir():
                return _error_result(
                    "invalid_workdir",
                    f"workdir does not exist in the temporary workspace: {workdir_result}",
                    started,
                    command=command,
                    workdir=workdir_result,
                    backend=backend.name,
                )

            result = backend.run_workspace(
                workspace=workspace,
                command=command,
                workdir=workdir_result,
                timeout_seconds=timeout_seconds,
                started=started,
            )
            result["requested_backend"] = self.backend_mode
            if fallback:
                result["runtime_fallback"] = fallback
            return result

    def build_docker_run_args(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
        container_name: str,
    ) -> list[str]:
        return self.docker_backend.build_docker_run_args(
            workspace=workspace,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
            container_name=container_name,
        )

    def build_mxc_policy(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        return build_mxc_policy(
            workspace=workspace,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
        )

    def _select_backend_for_run(self) -> tuple["CodeExecutionBackend", dict[str, Any] | None]:
        if self.backend_mode == "docker":
            return self.docker_backend, None
        if self.backend_mode == "mxc":
            return self.mxc_backend, None
        mxc_status = self.mxc_backend.status()
        if mxc_status.get("available"):
            return self.mxc_backend, None
        return (
            self.docker_backend,
            {
                "from": "mxc",
                "to": "docker",
                "reason": mxc_status.get("message") or "MXC runtime is unavailable.",
                "same_or_stricter_data_policy": True,
                "same_or_stricter_permission_boundary": True,
            },
        )

    def _host_env(self) -> dict[str, str]:
        return _host_env()

    def _normalize_workdir(self, workdir: str) -> str | dict[str, str]:
        return _normalize_workdir(workdir)

    def _copy_ignore(self, directory: str, names: list[str]) -> set[str]:
        return _copy_ignore(self.root, directory, names)


class CodeExecutionBackend:
    name: str

    def run_workspace(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
        started: float,
    ) -> dict[str, Any]:
        raise NotImplementedError


class DockerCodeExecutor(CodeExecutionBackend):
    name = "docker"

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

    def status(self, *, build_if_missing: bool = False) -> DockerRuntimeStatus:
        return self._status(build_if_missing=build_if_missing)

    def run_workspace(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
        started: float,
    ) -> dict[str, Any]:
        status = self._status(build_if_missing=True)
        if not status.available:
            return _error_result(
                "container_runtime_unavailable",
                status.message or "Docker container runtime is unavailable.",
                started,
                command=command,
                workdir=workdir,
                backend=self.name,
                image=self.image,
                network="none",
                extra=status.model_dump(),
            )

        container_name = f"harnessdiff-code-{uuid.uuid4().hex[:12]}"
        argv = self.build_docker_run_args(
            workspace=workspace,
            command=command,
            workdir=workdir,
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
                env=_host_env(),
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

        containment = _docker_containment(timeout_seconds)
        return {
            "command": command,
            "workdir": workdir,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "elapsed_ms": _elapsed_ms(started),
            "image": self.image,
            "network": "none",
            "runtime_backend": self.name,
            "containment": containment,
            "policy_hash": _policy_hash(containment),
            "enforcement_gaps": [],
            "preview_warning": "",
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

        daemon = _run_quiet([docker, "version", "--format", "{{.Server.Version}}"])
        if daemon.returncode != 0:
            return DockerRuntimeStatus(
                available=False,
                docker_found=True,
                daemon_available=False,
                image_present=False,
                image=self.image,
                message=(daemon.stderr or daemon.stdout or "Docker daemon is unavailable.").strip(),
            )

        image = _run_quiet([docker, "image", "inspect", self.image])
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
        build = _run_quiet(
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
            env=_host_env(),
        )

    def _docker_binary(self) -> str | None:
        return shutil.which("docker")


class MxcCodeExecutor(CodeExecutionBackend):
    name = "mxc"

    def __init__(self, root: Path, *, runner: Path) -> None:
        self.root = root.resolve()
        self.runner = runner

    def status(self) -> dict[str, Any]:
        base = {
            "available": False,
            "runtime_backend": self.name,
            "node_found": bool(shutil.which("node")),
            "runner_found": self.runner.is_file(),
            "mxc_experimental": _mxc_experimental_enabled(),
            "preview_warning": MXC_PREVIEW_WARNING,
            "security_boundary": "preview_not_trusted",
            "message": "",
        }
        if not _mxc_experimental_enabled():
            base["message"] = f"Set {MXC_EXPERIMENTAL_ENV}=1 to enable experimental MXC runtime."
            return base
        node = shutil.which("node")
        if not node:
            base["message"] = "Node.js was not found on PATH."
            return base
        if not self.runner.is_file():
            base["message"] = f"MXC runner not found: {self.runner}"
            return base
        runner = self._run_runner({"mode": "status"}, timeout=10)
        if runner.get("ok") is False:
            base.update(runner)
            base["message"] = runner.get("message") or runner.get("stderr") or "MXC status failed."
            return base
        base.update(runner)
        base["available"] = bool(runner.get("available"))
        return base

    def run_workspace(
        self,
        *,
        workspace: Path,
        command: str,
        workdir: str,
        timeout_seconds: int,
        started: float,
    ) -> dict[str, Any]:
        status = self.status()
        if not status.get("available"):
            return _error_result(
                "mxc_runtime_unavailable",
                status.get("message") or "MXC runtime is unavailable.",
                started,
                command=command,
                workdir=workdir,
                backend=self.name,
                network="block",
                extra=status,
                preview_warning=MXC_PREVIEW_WARNING,
            )

        policy = build_mxc_policy(
            workspace=workspace,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
        )
        enforcement_gaps = _mxc_enforcement_gaps()
        policy_hash = _policy_hash(policy)
        runner = self._run_runner(
            {
                "mode": "run",
                "workspace": str(workspace.resolve()),
                "command": command,
                "workdir": workdir,
                "timeout_seconds": timeout_seconds,
                "experimental": True,
                "policy": policy,
                "policy_hash": policy_hash,
                "enforcement_gaps": enforcement_gaps,
            },
            timeout=timeout_seconds + 30,
        )
        if runner.get("ok") is False:
            return _error_result(
                runner.get("error_type") or "mxc_runner_failed",
                runner.get("message") or runner.get("stderr") or "MXC runner failed.",
                started,
                command=command,
                workdir=workdir,
                backend=self.name,
                network="block",
                extra=runner,
                preview_warning=MXC_PREVIEW_WARNING,
            )

        stdout, stdout_truncated = _limit_text(str(runner.get("stdout") or ""))
        stderr, stderr_truncated = _limit_text(str(runner.get("stderr") or ""))
        return {
            "command": command,
            "workdir": workdir,
            "exit_code": int(runner.get("exit_code") or 0),
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "elapsed_ms": _elapsed_ms(started),
            "image": "",
            "network": "block",
            "runtime_backend": self.name,
            "containment": {
                "backend": runner.get("containment") or policy.get("containment"),
                "network": policy.get("network", {}),
                "filesystem": {
                    "workspace": str(workspace.resolve()),
                    "readwrite": "temporary_workspace_copy",
                    "writeback": "none",
                },
                "limits": {"timeout_seconds": timeout_seconds},
            },
            "policy_hash": runner.get("policy_hash") or policy_hash,
            "enforcement_gaps": runner.get("enforcement_gaps") or enforcement_gaps,
            "preview_warning": MXC_PREVIEW_WARNING,
            "mxc": {
                "schema_version": policy.get("version"),
                "runner": str(self.runner),
            },
        }

    def _run_runner(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        node = shutil.which("node")
        if not node:
            return {"ok": False, "error_type": "node_missing", "message": "Node.js was not found on PATH."}
        if not self.runner.is_file():
            return {
                "ok": False,
                "error_type": "mxc_runner_missing",
                "message": f"MXC runner not found: {self.runner}",
            }
        request_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
                json.dump(payload, handle, ensure_ascii=False)
                request_path = Path(handle.name)
            completed = subprocess.run(
                [node, str(self.runner), str(request_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=_host_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ok": False,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        finally:
            if request_path is not None:
                try:
                    request_path.unlink(missing_ok=True)
                except OSError:
                    pass

        try:
            result = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error_type": "mxc_runner_invalid_json",
                "message": "MXC runner did not return JSON.",
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        if completed.returncode != 0 and "ok" not in result:
            result["ok"] = False
        if completed.stderr and "stderr" not in result:
            result["stderr"] = completed.stderr
        return result


def build_mxc_policy(
    *,
    workspace: Path,
    command: str,
    workdir: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    cwd = workspace if workdir == "." else (workspace / workdir).resolve()
    readonly_paths = _mxc_readonly_tool_paths()
    return {
        "version": MXC_POLICY_VERSION,
        "containerId": f"harnessdiff-code-{uuid.uuid4().hex[:12]}",
        "containment": "process",
        "lifecycle": {"destroyOnExit": True, "preservePolicy": False},
        "process": {
            "commandLine": _mxc_command_line(command),
            "cwd": str(cwd),
            "env": ["CI=1", "NO_COLOR=1"],
            "timeout": timeout_seconds * 1000,
        },
        "filesystem": {
            "readonlyPaths": readonly_paths,
            "readwritePaths": [str(workspace)],
            "deniedPaths": [],
        },
        "network": {"defaultPolicy": "block"},
        "fallback": {"allowDaclMutation": False},
    }


def _normalize_backend(value: str | None) -> str:
    normalized = str(value or "docker").strip().lower()
    if normalized not in {"docker", "mxc", "auto"}:
        return "docker"
    return normalized


def _mxc_experimental_enabled() -> bool:
    return os.environ.get(MXC_EXPERIMENTAL_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _mxc_enforcement_gaps() -> list[str]:
    gaps = ["mxc_preview_not_security_boundary"]
    if os.name == "nt":
        gaps.append("windows_host_allow_block_lists_not_enforced")
    return gaps


def _mxc_command_line(command: str) -> str:
    if os.name == "nt":
        escaped = command.replace('"', '\\"')
        return f'cmd.exe /d /s /c "{escaped}"'
    return f"bash -lc {shlex.quote(command)}"


def _mxc_readonly_tool_paths() -> list[str]:
    tool_names = (
        "cmd",
        "bash",
        "sh",
        "python",
        "python3",
        "py",
        "node",
        "npm",
        "npx",
        "pnpm",
        "git",
        "rg",
        "jq",
        "curl",
    )
    paths: list[str] = []
    seen: set[str] = set()
    for name in tool_names:
        found = shutil.which(name)
        if not found:
            continue
        for candidate in (Path(found), Path(found).parent):
            try:
                resolved = str(candidate.resolve())
            except OSError:
                resolved = str(candidate)
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return paths


def _docker_containment(timeout_seconds: int) -> dict[str, Any]:
    return {
        "backend": "docker",
        "network": "none",
        "filesystem": {
            "workspace": "temporary_copy_bind_mounted_readwrite",
            "original_workspace_writeback": "none",
        },
        "limits": {
            "memory": "1g",
            "cpus": "1",
            "pids": 256,
            "timeout_seconds": timeout_seconds,
            "no_new_privileges": True,
            "cap_drop": "ALL",
        },
    }


def _run_quiet(
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
            env=_host_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 1, "", str(exc))


def _host_env() -> dict[str, str]:
    safe: dict[str, str] = {}
    for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "DOCKER_HOST", "NODE_PATH"):
        value = os.environ.get(key)
        if value:
            safe[key] = value
    return safe


def _normalize_workdir(workdir: str) -> str | dict[str, str]:
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


def _copy_ignore(root: Path, directory: str, names: list[str]) -> set[str]:
    current = Path(directory).resolve()
    ignored = {name for name in names if name in _COPY_IGNORED_NAMES}
    try:
        relative = current.relative_to(root)
    except ValueError:
        relative = Path(".")
    if relative.as_posix() == "data" and "projects" in names:
        ignored.add("projects")
    return ignored


def _error_result(
    error_type: str,
    message: str,
    started: float,
    *,
    command: str = "",
    workdir: str = ".",
    backend: str = "docker",
    image: str = DEFAULT_CODE_IMAGE,
    network: str = "none",
    extra: dict[str, Any] | None = None,
    preview_warning: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "command": command,
        "workdir": workdir,
        "exit_code": 127,
        "stdout": "",
        "stderr": message,
        "truncated": False,
        "elapsed_ms": _elapsed_ms(started),
        "image": image,
        "network": network,
        "runtime_backend": backend,
        "containment": {"backend": backend, "network": network},
        "policy_hash": "",
        "enforcement_gaps": _mxc_enforcement_gaps() if backend == "mxc" else [],
        "preview_warning": preview_warning,
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


def _policy_hash(policy: dict[str, Any]) -> str:
    serialized = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def env_key_is_sensitive(key: str) -> bool:
    return key.upper().endswith(("_KEY", "_TOKEN", "_SECRET")) or key.upper().startswith(
        _SENSITIVE_ENV_PREFIXES
    )
