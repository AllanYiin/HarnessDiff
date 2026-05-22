from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent


class FakeProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        yield ProviderEvent(type="created", pane=request.pane, sequence=0, response_id="resp_fake")
        yield ProviderEvent(type="delta", pane=request.pane, sequence=1, text=f"{request.pane}:")
        yield ProviderEvent(type="delta", pane=request.pane, sequence=2, text=request.prompt)
        yield ProviderEvent(
            type="completed",
            pane=request.pane,
            sequence=3,
            response_id="resp_fake",
            usage={
                "input_tokens": 3,
                "output_tokens": 5,
                "reasoning_tokens": 1,
                "total_tokens": 9,
                "provider_raw_usage": {"input_tokens": 3},
            },
        )


class FailingHarnessProvider(FakeProvider):
    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        if request.pane == "Harness":
            raise RuntimeError("simulated provider failure")
        async for event in super().stream_text(request):
            yield event


def test_run_stream_writes_pane_outputs_and_usage(tmp_path) -> None:
    provider = FakeProvider()
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=provider))
    project_id = client.post("/api/projects", json={"name": "Streaming"}).json()["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "hello",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "target_panes": ["NoHarness", "Harness"],
        },
    )
    assert create_response.status_code == 201
    run = create_response.json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert any(event["type"] == "delta" and event["pane"] == "NoHarness" for event in events)
    assert any(event["type"] == "delta" and event["pane"] == "Harness" for event in events)
    assert events[-2]["type"] == "analysis_ready"
    assert events[-1]["type"] == "run_completed"

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    assert json.loads((run_dir / "NoHarness" / "output.json").read_text(encoding="utf-8"))[
        "text"
    ] == "NoHarness:hello"
    assert json.loads((run_dir / "Harness" / "output.json").read_text(encoding="utf-8"))[
        "text"
    ] == "Harness:hello"
    assert (run_dir / "NoHarness" / "usage.json").exists()
    assert (run_dir / "analysis" / "analysis.json").exists()
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "completed"
    assert {request.pane for request in provider.requests} == {"NoHarness", "Harness"}

    analysis = client.get(f"/api/runs/{run['id']}/analysis")
    assert analysis.status_code == 200
    analysis_doc = analysis.json()
    assert analysis_doc["panes"]["NoHarness"]["current_turn_usage"]["total_tokens"] == 9
    assert analysis_doc["panes"]["Harness"]["context_sections"][0]["key"] == "system_prompt"
    assert analysis_doc["comparison"]["total_token_delta"] == 0


def test_run_applies_harness_module_overrides_to_harness_instructions(tmp_path) -> None:
    provider = FakeProvider()
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=provider))
    project_id = client.post("/api/projects", json={"name": "Harness modules"}).json()["id"]

    create_response = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "hello",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "target_panes": ["Harness"],
            "harness_modules": {
                "output_contract": False,
                "planning_preamble": True,
            },
        },
    )
    assert create_response.status_code == 201
    run = create_response.json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    harness_request = provider.requests[0]
    assert harness_request.pane == "Harness"
    assert "briefly plan the steps" in harness_request.instructions
    assert "explicit output contract" not in harness_request.instructions

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    input_doc = json.loads((run_dir / "Harness" / "input.json").read_text(encoding="utf-8"))
    assert input_doc["harness_modules"]["planning_preamble"] is True
    assert input_doc["harness_modules"]["output_contract"] is False


def test_analysis_accumulates_usage_across_completed_turns(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=FakeProvider()))
    project_id = client.post("/api/projects", json={"name": "Cumulative analysis"}).json()["id"]

    run_ids = []
    for prompt in ["first", "second"]:
        create_response = client.post(
            f"/api/projects/{project_id}/runs",
            json={
                "prompt": prompt,
                "input_mode": "independent",
                "model": "fake-model",
                "reasoning_effort": "medium",
                "target_panes": ["Harness"],
            },
        )
        assert create_response.status_code == 201
        run = create_response.json()
        run_ids.append(run["id"])
        with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
            assert response.status_code == 200
            _ = "".join(response.iter_text())

    analysis = client.get(f"/api/runs/{run_ids[-1]}/analysis").json()
    harness = analysis["panes"]["Harness"]
    assert harness["current_turn_usage"]["total_tokens"] == 9
    assert harness["cumulative_usage"]["total_tokens"] == 18
    history = next(
        section
        for section in harness["context_sections"]
        if section["key"] == "stored_conversation_history"
    )
    assert history["status"] == "stored_not_sent"
    assert history["characters"] > 0


def test_run_marks_failed_when_one_pane_provider_fails(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=FailingHarnessProvider()))
    project_id = client.post("/api/projects", json={"name": "Provider failure"}).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "hello",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "target_panes": ["NoHarness", "Harness"],
        },
    ).json()

    with client.stream("GET", f"/api/runs/{run['id']}/stream") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert any(event["type"] == "error" and event["pane"] == "Harness" for event in events)
    assert events[-1]["type"] == "run_failed"

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert not (run_dir / "analysis" / "analysis.json").exists()
    assert (run_dir / "Harness" / "events.jsonl").exists()


def test_analysis_endpoint_can_build_missing_analysis_artifact(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=FakeProvider()))
    project_id = client.post("/api/projects", json={"name": "Lazy analysis"}).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "draft only",
            "input_mode": "independent",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "target_panes": ["NoHarness"],
        },
    ).json()

    analysis = client.get(f"/api/runs/{run['id']}/analysis")

    assert analysis.status_code == 200
    doc = analysis.json()
    assert set(doc["panes"].keys()) == {"NoHarness"}
    assert doc["panes"]["NoHarness"]["current_turn_usage"]["source"] == "missing"
    assert doc["comparison"]["total_token_delta"] == 0
    assert (
        tmp_path / "projects" / project_id / "runs" / run["id"] / "analysis" / "analysis.json"
    ).exists()


def test_run_routes_reject_invalid_or_missing_ids(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, llm_provider=FakeProvider()))

    assert client.get("/api/runs/../bad/stream").status_code == 404
    assert client.get("/api/runs/bad$id/stream").status_code == 400
    assert client.get("/api/runs/run_missing/analysis").status_code == 404
