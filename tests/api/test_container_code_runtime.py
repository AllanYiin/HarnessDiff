from __future__ import annotations

import os

import pytest

from app.services.container_code_runtime import (
    ContainerCodeExecutor,
    DockerCodeExecutor,
    MxcCodeExecutor,
    _limit_text,
)


def test_container_code_runtime_builds_offline_constrained_docker_args(tmp_path) -> None:
    executor = ContainerCodeExecutor(tmp_path)

    argv = executor.build_docker_run_args(
        workspace=tmp_path,
        command="python --version && node --version",
        workdir="apps/web",
        timeout_seconds=120,
        container_name="harnessdiff-code-test",
    )

    assert argv[1:3] == ["run", "--rm"]
    assert "--network" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert "--memory" in argv
    assert argv[argv.index("--memory") + 1] == "1g"
    assert "--cpus" in argv
    assert argv[argv.index("--cpus") + 1] == "1"
    assert "--pids-limit" in argv
    assert argv[argv.index("--pids-limit") + 1] == "256"
    assert "--cap-drop" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "-w" in argv
    assert argv[argv.index("-w") + 1] == "/workspace/apps/web"
    assert "OPENAI_API_KEY" not in " ".join(argv)


def test_container_code_runtime_rejects_workdir_escape_before_docker(tmp_path) -> None:
    executor = ContainerCodeExecutor(tmp_path)

    result = executor.run("python --version", workdir="../outside")

    assert result["exit_code"] == 127
    assert result["error"]["type"] == "invalid_workdir"
    assert "parent-directory" in result["stderr"]


def test_container_code_runtime_host_env_omits_sensitive_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("SERPAPI_KEY", "secret")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    executor = ContainerCodeExecutor(tmp_path)

    env = executor._host_env()
    ignored = executor._copy_ignore(str(tmp_path), [".env", ".env.local", "sample.py"])

    assert "PATH" in env
    assert "OPENAI_API_KEY" not in env
    assert "SERPAPI_KEY" not in env
    assert ".env" in ignored
    assert ".env.local" in ignored
    assert "sample.py" not in ignored


def test_mxc_policy_blocks_network_and_marks_temp_workspace(tmp_path) -> None:
    executor = ContainerCodeExecutor(tmp_path)
    policy = executor.build_mxc_policy(
        workspace=tmp_path,
        command="python --version",
        workdir=".",
        timeout_seconds=120,
    )

    assert policy["version"] == "0.6.0-alpha"
    assert policy["containment"] == "process"
    assert policy["network"]["defaultPolicy"] == "block"
    assert policy["fallback"]["allowDaclMutation"] is False
    assert str(tmp_path.resolve()) in policy["filesystem"]["readwritePaths"]
    assert policy["process"]["timeout"] == 120_000
    assert "powershell" not in policy["process"]["commandLine"].lower()


def test_explicit_mxc_requires_experimental_opt_in(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HARNESSDIFF_CODE_RUNTIME_BACKEND", "mxc")
    monkeypatch.delenv("HARNESSDIFF_MXC_EXPERIMENTAL", raising=False)
    executor = ContainerCodeExecutor(tmp_path)

    result = executor.run("python --version")

    assert result["exit_code"] == 127
    assert result["runtime_backend"] == "mxc"
    assert result["error"]["type"] == "mxc_runtime_unavailable"
    assert "HARNESSDIFF_MXC_EXPERIMENTAL" in result["stderr"]
    assert result["preview_warning"]
    assert "mxc_preview_not_security_boundary" in result["enforcement_gaps"]


def test_auto_backend_falls_back_to_docker_with_policy_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HARNESSDIFF_CODE_RUNTIME_BACKEND", "auto")
    monkeypatch.setenv("HARNESSDIFF_MXC_EXPERIMENTAL", "1")
    executor = ContainerCodeExecutor(tmp_path)
    executor.mxc_backend = UnavailableMxcBackend(tmp_path)
    executor.docker_backend = FakeDockerBackend(tmp_path)

    result = executor.run("python --version")

    assert result["exit_code"] == 0
    assert result["runtime_backend"] == "docker"
    assert result["requested_backend"] == "auto"
    assert result["runtime_fallback"]["from"] == "mxc"
    assert result["runtime_fallback"]["to"] == "docker"
    assert result["runtime_fallback"]["same_or_stricter_data_policy"] is True
    assert result["policy_hash"]
    assert result["containment"]["limits"]["timeout_seconds"] == 120


def test_container_code_runtime_truncates_long_output() -> None:
    text, truncated = _limit_text("x" * 13000)

    assert truncated is True
    assert text.endswith("...[truncated]...")
    assert len(text) <= 12000


@pytest.mark.skipif(
    os.environ.get("HARNESSDIFF_RUN_DOCKER_TESTS") != "1",
    reason="set HARNESSDIFF_RUN_DOCKER_TESTS=1 to run Docker smoke tests",
)
def test_container_code_runtime_docker_smoke_python_node_pnpm(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"check":"node --version && pnpm --version"}}',
        encoding="utf-8",
    )
    executor = ContainerCodeExecutor(tmp_path)

    result = executor.run(
        "python3 --version && node --version && pnpm --version",
        timeout_seconds=120,
    )

    assert result["exit_code"] == 0
    assert "Python" in result["stdout"]
    assert "v" in result["stdout"]


class UnavailableMxcBackend(MxcCodeExecutor):
    def __init__(self, root):
        super().__init__(root, runner=root / "missing-mxc-runner.mjs")

    def status(self) -> dict:
        return {"available": False, "message": "MXC unavailable for test"}


class FakeDockerBackend(DockerCodeExecutor):
    def __init__(self, root):
        super().__init__(root)

    def run_workspace(self, *, workspace, command, workdir, timeout_seconds, started):
        containment = {
            "backend": "docker",
            "network": "none",
            "filesystem": {"original_workspace_writeback": "none"},
            "limits": {"timeout_seconds": timeout_seconds},
        }
        return {
            "command": command,
            "workdir": workdir,
            "exit_code": 0,
            "stdout": "Python 3.x",
            "stderr": "",
            "truncated": False,
            "elapsed_ms": 0,
            "image": "fake",
            "network": "none",
            "runtime_backend": "docker",
            "containment": containment,
            "policy_hash": "fake-hash",
            "enforcement_gaps": [],
            "preview_warning": "",
        }
