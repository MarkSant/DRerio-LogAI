"""Extended unit tests for core/project/asset_manager.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended2:
    """Test AssetManager slugification, synonyms, and directory creation."""

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
