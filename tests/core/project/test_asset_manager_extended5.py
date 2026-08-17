"""Extended unit tests for core/project/test_asset_manager.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended5:
    """Test AssetManager save_roi_template validation logic."""

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
