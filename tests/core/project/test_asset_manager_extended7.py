"""Extended unit tests for core/project/asset_manager.py (Part 7)."""

from __future__ import annotations

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended7:
    """Test AssetManager ROI template manager integration and slugify punctuation."""

    def test_asset_manager_roi_template_manager_instantiated(self):
        am = AssetManager()
        assert am.roi_template_manager is not None

    def test_slugify_with_special_characters(self):
        assert AssetManager._slugify("Arena #1 @ Lab (Main)") == "arena-1-lab-main"
        assert AssetManager._slugify("---test---") == "test"

    def test_slugify_numbers_and_underscores(self):
        assert AssetManager._slugify("arena_123_test") == "arena_123_test"
