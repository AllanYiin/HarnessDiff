from __future__ import annotations

import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.skill_store import SkillStore


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
    assert (home / "agents" / "web-researcher.md").exists()
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


def test_codex_style_skill_discovery_scans_project_and_user_scopes(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    home = tmp_path / "home" / ".harnessdiff"
    project_skill = repo_root / ".codex" / "skills" / "project-skill"
    project_skill.mkdir(parents=True)
    (project_skill / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Project description\n---\n# Project\n",
        encoding="utf-8",
    )
    project_agents_skill = repo_root / ".agents" / "skills" / "agent-skill"
    project_agents_skill.mkdir(parents=True)
    (project_agents_skill / "SKILL.md").write_text(
        "---\nname: agent-skill\ndescription: Agent root description\n---\n# Agent\n",
        encoding="utf-8",
    )
    user_skill = tmp_path / "home" / ".agents" / "skills" / "user-skill"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: User description\n---\n# User\n",
        encoding="utf-8",
    )
    disabled_skill = repo_root / ".codex" / "skills" / "disabled-skill"
    disabled_skill.mkdir(parents=True)
    (disabled_skill / "SKILL.md").write_text(
        "---\nname: disabled-skill\ndescription: Hidden\nenabled: false\n---\n# Disabled\n",
        encoding="utf-8",
    )

    store = SkillStore(home_dir=home, repo_root=repo_root)
    skills = store.list_skills()

    assert [skill.name for skill in skills] == ["agent-skill", "shared-skill"]
    assert skills[1].id == "shared-skill"
    assert all(skill.name != "disabled-skill" for skill in skills)

    manifest = store.context_manifest()
    assert "Skill roots:" in manifest
    assert "r0 (project)" in manifest
    assert "$shared-skill" in manifest
    assert "progressive disclosure" in manifest

    detail = store.read_skill("shared-skill")
    assert "# Project" in detail["content"]
    assert detail["scope"] == "project"


def test_duplicate_user_skill_names_keep_highest_precedence_record(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    home = tmp_path / "home" / ".harnessdiff"
    legacy_skill = home / "skills" / "financial-statement-analysis"
    legacy_skill.mkdir(parents=True)
    (legacy_skill / "SKILL.md").write_text(
        "---\n"
        "name: financial-statement-analysis\n"
        "description: Legacy copy\n"
        "---\n"
        "# Legacy\n",
        encoding="utf-8",
    )
    agents_skill = tmp_path / "home" / ".agents" / "skills" / "financial-statement-analysis"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text(
        "---\n"
        "name: financial-statement-analysis\n"
        "description: Codex-compatible copy\n"
        "---\n"
        "# Agents\n",
        encoding="utf-8",
    )

    store = SkillStore(home_dir=home, repo_root=repo_root)
    skills = [
        skill
        for skill in store.list_skills()
        if skill.name == "financial-statement-analysis"
    ]

    assert [skill.id for skill in skills] == ["financial-statement-analysis"]
    assert "--user-financial-statement-analysis" not in store.context_manifest()
    detail = store.read_skill("financial-statement-analysis")
    assert "# Agents" in detail["content"]


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
            "tools": ["WebSearch", "WebFetch"],
            "enabled": True,
        },
    )

    assert response.status_code == 201
    created = response.json()["subagent"]
    assert created["id"] == "fact_checker"
    assert created["label"] == "Fact Checker"
    assert created["tools"] == ["standard.web.search", "standard.web.fetch"]
    created_path = tmp_path / "home" / "agents" / "fact_checker.md"
    assert created_path.exists()
    assert "tools: standard.web.search, standard.web.fetch" in created_path.read_text(
        encoding="utf-8"
    )

    subagents = client.get("/api/subagents").json()["subagents"]
    assert any(
        subagent["id"] == "fact_checker"
        and subagent["tools"] == ["standard.web.search", "standard.web.fetch"]
        for subagent in subagents
    )


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
