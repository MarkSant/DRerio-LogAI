"""Basic tests for AssetManager utilities and asset removal logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.asset_manager import AssetManager


def test_slugify_normalizes_text():
    assert AssetManager._slugify("Meu Template Ç") == "meu-template-c"
    assert AssetManager._slugify("  ###  ") == "template"


def test_ensure_roi_template_dir(tmp_path):
    target = AssetManager.ensure_roi_template_dir(tmp_path)
    assert target.exists()
    assert target.name == "roi_templates"

    with pytest.raises(ValueError, match="Projeto não inicializado"):
        AssetManager.ensure_roi_template_dir("")


def test_list_roi_templates_aggregates_and_sorts(monkeypatch):
    manager = AssetManager()
    manager.roi_template_manager = MagicMock()
    manager.roi_template_manager.list_global_templates.return_value = [
        {"name": "Global B"},
        {"name": "Global A"},
    ]

    project_data = {
        "roi_templates": [
            {"name": "Project Z", "location": "project"},
            {"name": "Project A"},
        ]
    }

    result = manager.list_roi_templates(project_data, include_global=True)

    assert [item["name"] for item in result][:2] == ["Project A", "Project Z"]
    assert any(item.get("location") == "global" for item in result)


def test_resolve_roi_template_entry():
    project_data = {"roi_templates": [{"name": "Template A"}, {"name": "Template B"}]}
    idx, entry = AssetManager._resolve_roi_template_entry(project_data, "Template B")
    assert idx == 1
    assert entry is not None
    assert entry["name"] == "Template B"

    idx, entry = AssetManager._resolve_roi_template_entry(project_data, "Missing")
    assert idx is None
    assert entry is None


def test_get_analysis_profiles_default():
    manager = AssetManager()
    project_data: dict[str, Any] = {}

    profiles = manager.get_analysis_profiles(project_data)

    assert profiles[0]["name"] == "default"
    assert project_data["analysis_profiles"] == profiles


def test_resolve_analysis_profile_matches_synonym():
    manager = AssetManager()
    project_data = {
        "analysis_profiles": [
            {"name": "fallback", "criteria": {}},
            {"name": "subject_profile", "criteria": {"subject": ["alpha"]}},
        ]
    }

    selected = manager.resolve_analysis_profile(project_data, {"animal": "Alpha"})
    assert selected["name"] == "subject_profile"


def test_profile_matches_with_list_metadata():
    manager = AssetManager()
    criteria = {"day": ["d1", "d2"]}
    metadata = {"day_label": ["D2", "D3"]}

    assert manager._profile_matches(criteria, metadata) is True


def test_video_has_asset():
    manager = AssetManager()
    video_entry = {
        "has_arena": True,
        "has_rois": False,
        "has_trajectory": False,
        "has_summary": False,
        "path": "video.mp4",
        "parquet_files": {"rois": "rois.parquet", "summary_excel": "sum.xlsx"},
    }

    assert manager.video_has_asset(video_entry, "arena") is True
    assert manager.video_has_asset(video_entry, "rois") is True
    assert manager.video_has_asset(video_entry, "trajectory") is False
    assert manager.video_has_asset(video_entry, "summary") is True
    assert manager.video_has_asset(video_entry, "video") is True

    with pytest.raises(ValueError, match="desconhecido"):
        manager.video_has_asset(video_entry, cast(Any, "unknown"))


def test_can_remove_asset_summary_dependency():
    manager = AssetManager()
    video_entry = {"has_summary": True, "parquet_files": {"summary": "sum.parquet"}}

    can_remove, message = manager.can_remove_asset(video_entry, "arena")
    assert can_remove is False
    assert "Remova os relatórios" in (message or "")


def test_remove_summary_asset(monkeypatch, tmp_path):
    manager = AssetManager()

    delete_calls = []

    def _delete(path: Path | str) -> bool:
        delete_calls.append(str(path))
        return True

    monkeypatch.setattr(manager, "delete_file_if_exists", _delete)

    video_entry = {
        "has_summary": True,
        "parquet_files": {
            "summary": str(tmp_path / "sum.parquet"),
            "summary_excel": str(tmp_path / "sum.xlsx"),
            "report_docx": str(tmp_path / "sum.docx"),
        },
    }

    changed = manager.remove_summary_asset(video_entry, delete_files=True)

    assert changed is True
    assert video_entry["has_summary"] is False
    assert video_entry["parquet_files"] == {}
    assert len(delete_calls) == 3


def test_remove_trajectory_asset(monkeypatch, tmp_path):
    manager = AssetManager()

    monkeypatch.setattr(manager, "delete_file_if_exists", lambda _: True)

    video_entry = {
        "has_arena": True,
        "has_rois": True,
        "has_trajectory": True,
        "has_complete_data": True,
        "parquet_files": {"trajectory": str(tmp_path / "traj.parquet")},
    }

    changed = manager.remove_trajectory_asset(video_entry, delete_files=True)

    assert changed is True
    assert video_entry["has_trajectory"] is False
    assert video_entry["has_complete_data"] is False
    parquet_files = cast(dict[str, str], video_entry["parquet_files"])
    assert "trajectory" not in parquet_files


def test_delete_file_if_exists(tmp_path):
    manager = AssetManager()
    target = tmp_path / "file.txt"
    target.write_text("data")

    assert manager.delete_file_if_exists(target) is True
    assert not target.exists()

    assert manager.delete_file_if_exists(target) is False
