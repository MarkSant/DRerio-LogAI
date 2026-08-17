"""Extended unit tests for core/project/asset_manager.py (Part 4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended4:
    """Test AssetManager slugification, template listing, and directory helpers."""

    def test_slugify_string(self):
        assert AssetManager._slugify("Simple Name") == "simple-name"
        assert AssetManager._slugify("Ação & Reação 123") == "acao-reacao-123"
        assert AssetManager._slugify("---") == "template"
        assert AssetManager._slugify("") == "template"

    def test_ensure_roi_template_dir(self, tmp_path: Path):
        project_dir = tmp_path / "project_root"
        res = AssetManager.ensure_roi_template_dir(project_dir)
        assert res.exists()
        assert res == project_dir / "roi_templates"

    def test_ensure_roi_template_dir_empty_raises(self):
        with pytest.raises(ValueError, match="Project not initialised"):
            AssetManager.ensure_roi_template_dir("")

    def test_list_roi_templates_project_and_global_sorting(self):
        manager = AssetManager()
        manager.roi_template_manager = MagicMock()
        manager.roi_template_manager.list_global_templates.return_value = [
            {"name": "GlobalTemplateZ"},
            {"name": "GlobalTemplateA"},
        ]

        project_data = {
            "roi_templates": [
                {"name": "ProjectTemplateB"},
                {"name": "ProjectTemplateA"},
            ]
        }

        templates = manager.list_roi_templates(project_data, include_global=True)
        # Project templates come first, sorted by name; then global templates
        assert len(templates) == 4
        assert templates[0]["name"] == "ProjectTemplateA"
        assert templates[0]["location"] == "project"
        assert templates[1]["name"] == "ProjectTemplateB"
        assert templates[1]["location"] == "project"
        assert templates[2]["name"] == "GlobalTemplateA"
        assert templates[2]["location"] == "global"
        assert templates[3]["name"] == "GlobalTemplateZ"
        assert templates[3]["location"] == "global"

    def test_resolve_roi_template_entry(self):
        project_data = {
            "roi_templates": [
                {"name": "First"},
                {"name": "TargetTemplate"},
            ]
        }

        idx, entry = AssetManager._resolve_roi_template_entry(project_data, "TargetTemplate")
        assert idx == 1
        assert entry is not None
        assert entry["name"] == "TargetTemplate"

        idx_miss, entry_miss = AssetManager._resolve_roi_template_entry(project_data, "NonExistent")
        assert idx_miss is None
        assert entry_miss is None
