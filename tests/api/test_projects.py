from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_project_crud_round_trip(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))

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
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/api/projects/bad$id")

    assert response.status_code == 400


def test_corrupt_project_writes_repair_report(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
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
