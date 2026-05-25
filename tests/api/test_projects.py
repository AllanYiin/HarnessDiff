from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_project_crud_round_trip(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))

    create_response = client.post("/api/projects", json={"name": "Chat comparison"})

    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["name"] == "Chat comparison"
    assert created["surface_type"] == "chat"
    assert created["schema_version"] == "2026-05-22.1"

    project_path = tmp_path / "projects" / project_id / "project.json"
    config_path = tmp_path / "projects" / project_id / "config" / "harness.default.json"
    assert project_path.exists()
    assert config_path.exists()

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    assert [project["id"] for project in list_response.json()["projects"]] == [project_id]

    update_response = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Updated comparison", "config_profile": "harness.default"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated comparison"

    get_response = client.get(f"/api/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Updated comparison"

    delete_response = client.delete(f"/api/projects/{project_id}")
    assert delete_response.status_code == 204
    assert not (tmp_path / "projects" / project_id).exists()


def test_invalid_project_id_is_rejected(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))

    response = client.get("/api/projects/bad$id")

    assert response.status_code == 400


def test_project_transcript_returns_runs_and_outputs(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))
    project_id = client.post("/api/projects", json={"name": "Transcript"}).json()["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={
            "prompt": "hello",
            "input_mode": "integrated",
            "model": "fake-model",
            "reasoning_effort": "medium",
            "profiles": [{"id": "baseline", "label": "NoHarness", "harness_modules": {}}],
        },
    ).json()
    run_dir = tmp_path / "projects" / project_id / "runs" / run["id"] / "baseline"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "output.json").write_text(
        json.dumps({"profile_id": "baseline", "profile_label": "NoHarness", "text": "answer"}, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_id}/transcript")

    assert response.status_code == 200
    doc = response.json()
    assert doc["project"]["id"] == project_id
    assert doc["runs"][0]["prompt"] == "hello"
    assert doc["runs"][0]["profiles"][0]["id"] == "baseline"
    assert doc["runs"][0]["profiles"][0]["output_text"] == "answer"


def test_corrupt_project_writes_repair_report(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))
    create_response = client.post("/api/projects", json={"name": "Corrupt me"})
    project_id = create_response.json()["id"]
    project_dir = tmp_path / "projects" / project_id
    project_path = project_dir / "project.json"
    project_path.write_text("{not-json", encoding="utf-8")

    response = client.get(f"/api/projects/{project_id}")

    assert response.status_code == 409
    report_path = project_dir / "repair-report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["project_id"] == project_id
    assert report["status"] == "corrupt"
