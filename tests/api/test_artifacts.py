from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent


class CapturingProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        yield ProviderEvent(
            type="created",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=0,
            response_id="resp_artifact",
        )
        yield ProviderEvent(
            type="delta",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=1,
            text="ok",
        )
        yield ProviderEvent(
            type="completed",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=2,
            response_id="resp_artifact",
        )


def test_project_artifact_create_patch_and_version_conflict(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / ".harnessdiff"))
    project = client.post("/api/projects", json={"name": "Canvas"}).json()

    created = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "profile_id": "baseline",
            "kind": "single_page_html",
            "title": "Demo page",
            "content": "<!doctype html><html><body>v1</body></html>",
        },
    )

    assert created.status_code == 201
    artifact = created.json()
    assert artifact["version"] == 1
    assert artifact["profile_id"] == "baseline"

    svg_created = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "profile_id": "baseline",
            "kind": "svg",
            "title": "Icon",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
        },
    )
    assert svg_created.status_code == 201
    assert svg_created.json()["kind"] == "svg"

    patched = client.patch(
        f"/api/projects/{project['id']}/artifacts/{artifact['id']}",
        json={
            "base_version": 1,
            "content": "<!doctype html><html><body>v2</body></html>",
        },
    )

    assert patched.status_code == 200
    assert patched.json()["version"] == 2

    conflict = client.patch(
        f"/api/projects/{project['id']}/artifacts/{artifact['id']}",
        json={"base_version": 1, "content": "stale"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["actual_version"] == 2


def test_run_rejects_stale_artifact_ref(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / ".harnessdiff"))
    project = client.post("/api/projects", json={"name": "Canvas"}).json()
    artifact = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "profile_id": "baseline",
            "kind": "plain_text",
            "title": "Note",
            "content": "version one",
        },
    ).json()
    client.patch(
        f"/api/projects/{project['id']}/artifacts/{artifact['id']}",
        json={"base_version": 1, "content": "version two"},
    )

    response = client.post(
        f"/api/projects/{project['id']}/runs",
        json={
            "prompt": "revise the canvas",
            "profiles": [{"id": "baseline", "label": "NoHarness", "harness_modules": {}}],
            "artifact_refs": [
                {
                    "artifact_id": artifact["id"],
                    "profile_id": "baseline",
                    "version": 1,
                    "include_mode": "full",
                }
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "Artifact version conflict"


def test_run_context_includes_only_profile_local_artifact_snapshot(tmp_path) -> None:
    provider = CapturingProvider()
    client = TestClient(
        create_app(
            data_dir=tmp_path / "data",
            harnessdiff_home=tmp_path / ".harnessdiff",
            llm_provider=provider,
        )
    )
    project = client.post("/api/projects", json={"name": "Canvas"}).json()
    baseline_artifact = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "profile_id": "baseline",
            "kind": "plain_text",
            "title": "Baseline note",
            "content": "baseline-only content",
        },
    ).json()
    harness_artifact = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "profile_id": "harness",
            "kind": "markdown",
            "title": "Harness note",
            "content": "harness-only content",
        },
    ).json()

    run = client.post(
        f"/api/projects/{project['id']}/runs",
        json={
            "prompt": "revise the active canvas",
            "profiles": [
                {"id": "baseline", "label": "NoHarness", "harness_modules": {}},
                {"id": "harness", "label": "Harness", "harness_modules": {"artifact_review": True}},
            ],
            "artifact_refs": [
                {
                    "artifact_id": baseline_artifact["id"],
                    "profile_id": "baseline",
                    "version": 1,
                    "include_mode": "full",
                },
                {
                    "artifact_id": harness_artifact["id"],
                    "profile_id": "harness",
                    "version": 1,
                    "include_mode": "full",
                },
            ],
        },
    ).json()

    client.get(f"/api/runs/{run['id']}/stream")
    requests = {request.profile_id: request for request in provider.requests}

    assert "baseline-only content" in requests["baseline"].prompt
    assert "harness-only content" not in requests["baseline"].prompt
    assert "harness-only content" in requests["harness"].prompt
    assert "baseline-only content" not in requests["harness"].prompt
    assert "correct artifact id, profile id, and base version" in requests["harness"].instructions
