from __future__ import annotations

import os

import pytest

from app.services.container_code_runtime import ContainerCodeExecutor, _limit_text


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
