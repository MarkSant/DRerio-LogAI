"""Extended unit tests for core/project/asset_manager.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended:
    """Test AssetManager helper functions, slugification, and ROI template resolution."""

    def test_slugify(self):
        assert AssetManager._slugify("Standard 2x2 Arena") == "standard-2x2-arena"
        assert AssetManager._slugify("Área Central (10cm)") == "area-central-10cm"
        assert AssetManager._slugify("---Test---") == "test"
        assert AssetManager._slugify("") == "template"

    def test_ensure_roi_template_dir(self, tmp_path: Path):
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        template_dir = AssetManager.ensure_roi_template_dir(project_dir)
        assert template_dir.exists()
        assert template_dir.name == "roi_templates"

        with pytest.raises(ValueError, match="Project not initialised"):
            AssetManager.ensure_roi_template_dir("")

    def test_resolve_roi_template_entry(self):
        project_data = {
            "roi_templates": [
                {"name": "TemplateA", "file": "tmpl_a.json"},
                {"name": "TemplateB", "file": "tmpl_b.json"},
                "corrupted_entry",
            ]
        }
        idx, entry = AssetManager._resolve_roi_template_entry(project_data, "TemplateB")
        assert idx == 1
        assert entry is not None
        assert entry["file"] == "tmpl_b.json"

        idx_none, entry_none = AssetManager._resolve_roi_template_entry(project_data, "NonExistent")
        assert idx_none is None
        assert entry_none is None

    def test_list_roi_templates(self):
        manager = AssetManager()
        manager.roi_template_manager = MagicMock()
        manager.roi_template_manager.list_global_templates.return_value = [
            {"name": "GlobalTemplate", "file": "global.json"}
        ]

        project_data = {"roi_templates": [{"name": "ProjectTemplate", "file": "proj.json"}]}

        templates = manager.list_roi_templates(project_data, include_global=True)
        assert len(templates) == 2
        assert templates[0]["name"] == "ProjectTemplate"
        assert templates[0]["location"] == "project"
        assert templates[1]["name"] == "GlobalTemplate"
        assert templates[1]["location"] == "global"

    def test_profile_synonyms_structure(self):
        synonyms = AssetManager._PROFILE_SYNONYMS
        assert "group" in synonyms
        assert "day" in synonyms
        assert "subject" in synonyms
        assert "experiment_id" in synonyms
        assert "cobaia" in synonyms["subject"]
        assert "video_name" in synonyms["experiment_id"]

    def test_save_roi_template_validations(self):
        manager = AssetManager()
        project_data: dict = {}

        # 1. Empty name
        with pytest.raises(ValueError, match="cannot be empty"):
            manager.save_roi_template(project_data, "/proj", "", MagicMock(), MagicMock())

        # 2. None zone_data
        with pytest.raises(ValueError, match="Invalid zone data"):
            manager.save_roi_template(
                project_data,
                "/proj",
                "Name",
                None,  # type: ignore[arg-type]
                MagicMock(),
            )

        # 3. Neither arena nor ROIs
        mock_zones = MagicMock()
        with pytest.raises(ValueError, match="Select at least"):
            manager.save_roi_template(
                project_data,
                "/proj",
                "Name",
                mock_zones,
                MagicMock(),
                save_arena=False,
                save_rois=False,
            )

        # 4. No project path when saving to project
        with pytest.raises(ValueError, match="no project loaded"):
            manager.save_roi_template(
                project_data, "", "Name", mock_zones, MagicMock(), save_location="project"
            )

    def test_import_roi_template_file_not_found(self, tmp_path: Path):
        manager = AssetManager()
        project_data: dict = {}
        missing_file = tmp_path / "nonexistent_tmpl.json"

        with pytest.raises(FileNotFoundError):
            manager.import_roi_template(
                project_data=project_data,
                project_path=tmp_path,
                file_path=missing_file,
                zone_data_from_dict_fn=MagicMock(),
                zone_data_to_dict_fn=MagicMock(),
            )

    def test_load_roi_template_missing_file_in_project(self, tmp_path: Path):
        manager = AssetManager()
        project_data = {
            "roi_templates": [{"name": "TemplateMissing", "file": "roi_templates/missing.json"}]
        }

        with pytest.raises(FileNotFoundError):
            manager.load_roi_template(
                project_data=project_data,
                project_path=tmp_path,
                name="TemplateMissing",
                zone_data_from_dict_fn=MagicMock(),
            )
