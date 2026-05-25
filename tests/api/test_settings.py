from __future__ import annotations

from pathlib import Path

from app.core.settings import REPO_ROOT, resolve_harnessdiff_home
from app.services.skill_store import SkillStore


def test_harnessdiff_home_defaults_to_user_home() -> None:
    assert resolve_harnessdiff_home(None) == (Path.home() / ".harnessdiff").resolve()


def test_harnessdiff_home_ignores_legacy_project_local_home() -> None:
    assert resolve_harnessdiff_home(REPO_ROOT / ".harnessdiff") == (
        Path.home() / ".harnessdiff"
    ).resolve()


def test_harnessdiff_home_ignores_legacy_project_root_home() -> None:
    assert resolve_harnessdiff_home(REPO_ROOT) == (Path.home() / ".harnessdiff").resolve()


def test_harnessdiff_home_still_allows_non_project_override(tmp_path) -> None:
    custom_home = tmp_path / "harness-home"

    assert resolve_harnessdiff_home(custom_home) == custom_home.resolve()


def test_skill_store_normalizes_legacy_project_root_home() -> None:
    assert SkillStore(home_dir=REPO_ROOT).home_dir == (Path.home() / ".harnessdiff").resolve()
