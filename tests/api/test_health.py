from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_route_returns_stage0_metadata(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, harnessdiff_home=tmp_path / ".harnessdiff"))

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "HarnessDiff API"
    assert body["schema_version"] == "2026-05-22.1"
    assert body["data_dir"] == str(tmp_path.resolve())
    assert body["harnessdiff_home"] == str((tmp_path / ".harnessdiff").resolve())
    assert body["tools"]["enabled"] is True
    assert "standard.web.search" in body["tools"]["names"]
    assert "standard.shell.bash" in body["tools"]["names"]
    assert "standard.code.container_exec" in body["tools"]["names"]
    assert "harness.subagent.run" in body["tools"]["names"]
    assert "multi_tool_use.parallel" in body["tools"]["names"]
    assert isinstance(body["tools"]["web_search_configured"], bool)
    assert isinstance(body["tools"]["container_runtime"]["docker_found"], bool)
    assert body["tools"]["container_runtime"]["image"] == "harnessdiff-code-runtime:latest"
