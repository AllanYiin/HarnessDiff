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
    assert events[-1]["type"] == "run_completed"

    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"]
    assert json.loads((run_dir / "NoHarness" / "output.json").read_text(encoding="utf-8"))[
        "text"
    ] == "NoHarness:hello"
    assert json.loads((run_dir / "Harness" / "output.json").read_text(encoding="utf-8"))[
        "text"
    ] == "Harness:hello"
    assert (run_dir / "NoHarness" / "usage.json").exists()
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "completed"
    assert {request.pane for request in provider.requests} == {"NoHarness", "Harness"}


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
