from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_route_returns_stage0_metadata(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "HarnessDiff API"
    assert body["schema_version"] == "2026-05-22.1"
    assert body["data_dir"] == str(tmp_path.resolve())

