from __future__ import annotations

import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_create_app_initializes_harnessdiff_home(tmp_path) -> None:
    home = tmp_path / "home"
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=home))

    response = client.get("/api/skills")

    assert response.status_code == 200
    body = response.json()
    assert body["home_dir"] == str(home.resolve())
    assert body["skills_dir"] == str((home / "skills").resolve())
    assert (home / "CLAUDE.md").exists()
    assert (home / "AGENTS.md").exists()
    assert (home / "agents.md").exists()
    assert (home / "agents" / "researcher.md").exists()
    assert (home / "agents" / "critic.md").exists()
    assert (home / "agents" / "summarizer.md").exists()
    assert body["skills"] == []


def test_import_skill_file_and_read_full_skill(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / "home"))
    content = b"---\nname: demo-skill\ndescription: Demo description\nversion: 1.0\n---\n# Demo\n"

    response = client.post(
        "/api/skills/import",
        json={"mode": "skill", "filename": "demo.skill", "data_base64": _b64(content)},
    )

    assert response.status_code == 201
    skill = response.json()["skill"]
    assert skill["name"] == "demo-skill"
    assert skill["description"] == "Demo description"

    detail = client.get(f"/api/skills/{skill['id']}")
    assert detail.status_code == 200
    assert "Demo description" in detail.json()["content"]


def test_import_zip_rejects_path_traversal(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / "home"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../SKILL.md", "---\nname: bad\n---\n")

    response = client.post(
        "/api/skills/import",
        json={"mode": "zip", "filename": "bad.zip", "data_base64": _b64(buffer.getvalue())},
    )

    assert response.status_code == 400
    assert "Unsafe import path" in response.json()["detail"]


def test_import_folder_requires_skill_md_and_lists_summary(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / "home"))
    response = client.post(
        "/api/skills/import",
        json={
            "mode": "folder",
            "filename": "folder",
            "files": [
                {
                    "relative_path": "my-skill/SKILL.md",
                    "data_base64": _b64(
                        b"---\nname: folder-skill\ndescription: Folder description\n---\n"
                    ),
                },
                {"relative_path": "my-skill/references/note.txt", "data_base64": _b64(b"note")},
            ],
        },
    )

    assert response.status_code == 201
    skills = client.get("/api/skills").json()["skills"]
    assert skills == [
        {
            "id": "folder-skill",
            "name": "folder-skill",
            "description": "Folder description",
            "version": "",
            "path": str((tmp_path / "home" / "skills" / "folder-skill").resolve()),
        }
    ]


def test_create_subagent_definition_and_list_it(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / "home"))

    response = client.post(
        "/api/subagents",
        json={
            "id": "fact_checker",
            "label": "Fact Checker",
            "description": "Check claims against provided evidence.",
            "instructions": "Return only supported and unsupported claims.",
            "model": "gpt-5.4-mini",
            "reasoning_effort": "low",
            "max_output_chars": 1200,
            "enabled": True,
        },
    )

    assert response.status_code == 201
    created = response.json()["subagent"]
    assert created["id"] == "fact_checker"
    assert created["label"] == "Fact Checker"
    assert (tmp_path / "home" / "agents" / "fact_checker.md").exists()

    subagents = client.get("/api/subagents").json()["subagents"]
    assert any(subagent["id"] == "fact_checker" for subagent in subagents)


def test_create_subagent_rejects_duplicate_id(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", harnessdiff_home=tmp_path / "home"))
    payload = {
        "id": "researcher",
        "label": "Researcher",
        "instructions": "Duplicate.",
    }

    response = client.post("/api/subagents", json=payload)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]
