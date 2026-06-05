from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.agent import AgentRunConfig, AgentStepEvent
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent


class FakeAgentProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        yield ProviderEvent(
            type="created",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=0,
            response_id=f"resp_{request.profile_id}",
        )
        yield ProviderEvent(
            type="delta",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=1,
            text=f"{request.profile_label}: ",
        )
        yield ProviderEvent(
            type="delta",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=2,
            text=request.prompt,
        )
        yield ProviderEvent(
            type="completed",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=3,
            usage={
                "input_tokens": 4,
                "cached_tokens": 0,
                "output_tokens": 6,
                "reasoning_tokens": 1,
                "total_tokens": 11,
            },
        )


class ToolCallingAgentProvider(FakeAgentProvider):
    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        yield ProviderEvent(
            type="created",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=0,
        )
        if request.profile_id == "harness_agent":
            yield ProviderEvent(
                type="tool_call",
                profile_id=request.profile_id,
                profile_label=request.profile_label,
                sequence=1,
                raw={
                    "ok": True,
                    "tool_name": "harness.subagent.run",
                    "openai_name": "harness_subagent_run",
                    "arguments": {"subagent_id": "researcher", "task": "Delegate research"},
                    "result_summary": "{\"output\":\"research notes\"}",
                    "elapsed_ms": 25,
                    "subagent_id": "researcher",
                    "subagent_label": "Researcher",
                    "token_usage": {
                        "source": "provider_reported",
                        "input_tokens": 3,
                        "output_tokens": 4,
                        "total_tokens": 7,
                    },
                },
            )
        yield ProviderEvent(
            type="delta",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=2,
            text=f"{request.profile_label}: done",
        )
        yield ProviderEvent(
            type="completed",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=3,
            usage={"input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
        )


def _sse_events(body: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def test_agent_run_config_validates_objective_and_defaults() -> None:
    config = AgentRunConfig(objective="Compare agent behavior")

    assert config.type == "agent"
    assert config.context == ""
    assert config.max_steps == 16
    assert config.allow_subagents is True
    assert config.allow_container_tools is True


def test_agent_step_event_accepts_trace_metadata() -> None:
    event = AgentStepEvent(
        schema_version="2026-05-22.1",
        run_id="run_agent",
        profile_id="harness_agent",
        profile_label="Harness Agent",
        step_id="step_0001",
        sequence=1,
        type="agent_step_started",
        label="Prepare task",
        status="running",
        created_at="2026-05-31T00:00:00+00:00",
    )

    assert event.step_id == "step_0001"
    assert event.status == "running"


def test_chat_run_payload_stays_backward_compatible(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))
    project_id = client.post("/api/projects", json={"name": "Chat"}).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "hello",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    )

    assert response.status_code == 201
    run = response.json()
    assert run["surface_payload"] is None


def test_agent_surface_payload_is_persisted_without_changing_chat_defaults(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))
    project_id = client.post(
        "/api/projects", json={"name": "Agent", "surface_type": "agent"}
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Inspect the repository",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "surface_payload": {
                "type": "agent",
                "objective": "Inspect the repository",
                "context": "Focus on tests",
                "max_steps": 8,
            },
        },
    )

    assert response.status_code == 201
    run = response.json()
    assert run["surface_payload"]["objective"] == "Inspect the repository"
    run_path = tmp_path / "projects" / project_id / "runs" / run["id"] / "run.json"
    stored = json.loads(run_path.read_text(encoding="utf-8"))
    assert stored["surface_payload"]["context"] == "Focus on tests"


def test_agent_project_uses_agent_profiles_and_streams_steps(tmp_path) -> None:
    provider = FakeAgentProvider()
    client = TestClient(
        create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff", llm_provider=provider)
    )
    project_id = client.post(
        "/api/projects", json={"name": "Agent", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Inspect the repository",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    assert any(event["type"] == "agent_step_started" for event in events)
    assert any(event["type"] == "delta" and event["profile_id"] == "baseline_agent" for event in events)
    assert any(event["type"] == "delta" and event["profile_id"] == "harness_agent" for event in events)
    assert events[-1]["type"] == "run_completed"
    assert {request.profile_id for request in provider.requests} == {
        "baseline_agent",
        "harness_agent",
    }
    requests_by_profile = {request.profile_id: request for request in provider.requests}
    assert requests_by_profile["baseline_agent"].conversation_messages == ()
    assert "Agent mode" in requests_by_profile["harness_agent"].instructions
    assert requests_by_profile["harness_agent"].tools_enabled is True

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "completed"
    assert (run_dir / "baseline_agent" / "steps.jsonl").exists()
    assert (run_dir / "harness_agent" / "steps.jsonl").exists()
    baseline_output = json.loads((run_dir / "baseline_agent" / "output.json").read_text(encoding="utf-8"))
    assert baseline_output["text"] == "NoHarness Agent: Inspect the repository"


def test_harness_agent_reads_harnessdiff_agents_md(tmp_path) -> None:
    provider = FakeAgentProvider()
    home = tmp_path / ".harnessdiff"
    home.mkdir()
    (home / "AGENTS.md").write_text(
        "# Local instructions\nHarness Agent sentinel instruction.",
        encoding="utf-8",
    )
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=home, llm_provider=provider))
    project_id = client.post(
        "/api/projects", json={"name": "Agent", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Inspect the repository",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        _sse_events("".join(response.iter_text()))

    requests = {request.profile_id: request for request in provider.requests}
    assert "Harness Agent sentinel instruction." not in requests["baseline_agent"].instructions
    assert "Harness Agent sentinel instruction." in requests["harness_agent"].instructions


def test_agent_explicit_skill_invocation_loads_skill_context(tmp_path) -> None:
    provider = FakeAgentProvider()
    home = tmp_path / ".harnessdiff"
    skill_dir = home / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo agent skill.\n---\n"
        "# Demo Skill\n\nApply the demo skill sentinel workflow.",
        encoding="utf-8",
    )
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=home, llm_provider=provider))
    project_id = client.post(
        "/api/projects", json={"name": "Agent skill", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "$demo-skill inspect the repository",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    assert any(event["type"] == "skill_invocation" for event in events)
    assert all(
        "Apply the demo skill sentinel workflow." in request.instructions
        for request in provider.requests
    )


def test_agent_tool_policy_keeps_high_risk_tools_harness_only(tmp_path) -> None:
    provider = FakeAgentProvider()
    client = TestClient(
        create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff", llm_provider=provider)
    )
    project_id = client.post(
        "/api/projects", json={"name": "Agent tools", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Use tools if needed",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        _sse_events("".join(response.iter_text()))

    requests = {request.profile_id: request for request in provider.requests}
    baseline_tools = set(requests["baseline_agent"].tool_context.list_tool_names())
    harness_tools = set(requests["harness_agent"].tool_context.list_tool_names())
    assert "standard.shell.bash" not in baseline_tools
    assert "standard.code.container_exec" not in baseline_tools
    assert "harness.subagent.run" not in baseline_tools
    assert "multi_tool_use.parallel" not in baseline_tools
    assert "skill_routing_review" not in baseline_tools
    assert "standard.shell.bash" in harness_tools
    assert "standard.code.container_exec" in harness_tools
    assert "harness.subagent.run" in harness_tools
    assert "multi_tool_use.parallel" in harness_tools
    assert "skill_routing_review" in harness_tools


def test_agent_tool_call_is_recorded_as_step_trace(tmp_path) -> None:
    provider = ToolCallingAgentProvider()
    client = TestClient(
        create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff", llm_provider=provider)
    )
    project_id = client.post(
        "/api/projects", json={"name": "Agent trace", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Delegate research",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    tool_step = next(
        event
        for event in events
        if event["type"] == "agent_step_completed"
        and event["agent_step"]["tool_name"] == "harness.subagent.run"
    )
    assert tool_step["agent_step"]["subagent_id"] == "researcher"
    assert tool_step["agent_step"]["token_usage"]["total_tokens"] == 7
    steps_path = (
        tmp_path
        / "projects"
        / project_id
        / "runs"
        / run["id"]
        / "harness_agent"
        / "steps.jsonl"
    )
    steps = [json.loads(line) for line in steps_path.read_text(encoding="utf-8").splitlines()]
    assert any(step["tool_name"] == "harness.subagent.run" for step in steps)


def test_agent_analysis_artifact_and_transcript_steps_are_traceable(tmp_path) -> None:
    provider = ToolCallingAgentProvider()
    client = TestClient(
        create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff", llm_provider=provider)
    )
    project_id = client.post(
        "/api/projects", json={"name": "Agent analysis", "surface_type": "agent"}
    ).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "Trace artifacts",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    analysis_events = [event for event in events if event["type"] == "analysis_ready"]
    assert len(analysis_events) == 1
    analysis = analysis_events[0]["analysis"]
    assert analysis["raw_sources"]["analysis_basis"] == "local_agent_artifacts"
    assert analysis["raw_sources"]["agent_metrics"]["harness_agent"]["tool_call_count"] == 1
    assert analysis["raw_sources"]["agent_metrics"]["harness_agent"]["subagent_count"] == 1
    assert analysis["profiles"]["harness_agent"]["subagent_count"] == 0

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    analysis_path = run_dir / "analysis" / "agent-analysis.json"
    assert analysis_path.exists()
    stored_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert stored_analysis["run_id"] == run["id"]

    response = client.get(f"/api/runs/{run['id']}/analysis")
    assert response.status_code == 200
    assert response.json()["raw_sources"]["agent_metrics"]["harness_agent"]["subagent_count"] == 1

    transcript = client.get(f"/api/projects/{project_id}/transcript").json()
    harness_profile = next(
        profile
        for profile in transcript["runs"][0]["profiles"]
        if profile["id"] == "harness_agent"
    )
    assert any(step["tool_name"] == "harness.subagent.run" for step in harness_profile["steps"])
    assert harness_profile["tool_calls"][0]["arguments"]["subagent_id"] == "researcher"
    assert "research notes" in harness_profile["tool_calls"][0]["result_summary"]
