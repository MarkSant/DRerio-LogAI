"""Extended unit tests for core/project/asset_manager.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended:
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


class TestAssetManagerExtended2:
    def test_profile_synonyms(self):
        assert "group" in AssetManager._PROFILE_SYNONYMS
        assert "day" in AssetManager._PROFILE_SYNONYMS
        assert "subject" in AssetManager._PROFILE_SYNONYMS
        assert "experiment_id" in AssetManager._PROFILE_SYNONYMS

    def test_slugify(self):
        assert AssetManager._slugify("My Test Template!") == "my-test-template"
        assert AssetManager._slugify("Arena_1-TopDown") == "arena_1-topdown"
        assert AssetManager._slugify("   ") == "template"
        assert AssetManager._slugify("Água & Peixe") == "agua-peixe"

    def test_ensure_roi_template_dir(self, tmp_path: Path):
        project_dir = tmp_path / "project_root"
        project_dir.mkdir()

        template_dir = AssetManager.ensure_roi_template_dir(project_dir)
        assert template_dir.exists()
        assert template_dir.is_dir()
        assert template_dir.name == "roi_templates"

    def test_slugify_numbers_and_underscores(self):
        assert AssetManager._slugify("Batch_123_456") == "batch_123_456"
        assert AssetManager._slugify("---test---") == "test"


class TestAssetManagerExtended4:
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


class TestAssetManagerExtended5:
    def test_save_roi_template_empty_name_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="cannot be empty"):
            am.save_roi_template({}, "/path", "", MagicMock(), MagicMock())

    def test_save_roi_template_none_zone_data_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="Invalid zone data"):
            am.save_roi_template({}, "/path", "MyTemplate", None, MagicMock())  # type: ignore[arg-type]

    def test_save_roi_template_neither_arena_nor_rois_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="at least the arena or the ROIs"):
            am.save_roi_template(
                {},
                "/path",
                "MyTemplate",
                MagicMock(),
                MagicMock(),
                save_arena=False,
                save_rois=False,
            )

    def test_save_roi_template_no_project_loaded_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="no project loaded"):
            am.save_roi_template(
                {}, "", "MyTemplate", MagicMock(), MagicMock(), save_location="project"
            )


class TestAssetManagerExtended6:
    def test_asset_manager_slugify(self):
        assert AssetManager._slugify("My Test Arena 01!") == "my-test-arena-01"
        assert AssetManager._slugify("Grupo_Controle #2") == "grupo_controle-2"
        assert AssetManager._slugify("  simple  ") == "simple"


class TestAssetManagerExtended7:
    def test_asset_manager_roi_template_manager_instantiated(self):
        am = AssetManager()
        assert am.roi_template_manager is not None

    def test_slugify_with_special_characters(self):
        assert AssetManager._slugify("Arena #1 @ Lab (Main)") == "arena-1-lab-main"
        assert AssetManager._slugify("---test---") == "test"

    def test_slugify_numbers_and_underscores(self):
        assert AssetManager._slugify("arena_123_test") == "arena_123_test"
