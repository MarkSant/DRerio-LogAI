"""
Extended unit tests for AssetManager in core/project/asset_manager.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended:
    """Test AssetManager slugification, ROI template discovery, and asset removal."""

    def test_slugify(self):
        assert AssetManager._slugify("Arena 1 Test") == "arena-1-test"
        assert AssetManager._slugify("Aquário Médio") == "aquario-medio"
        assert AssetManager._slugify("---") == "template"
        assert AssetManager._slugify("   ") == "template"

    def test_ensure_roi_template_dir(self, tmp_path: Path):
        target = AssetManager.ensure_roi_template_dir(tmp_path)
        assert target == tmp_path / "roi_templates"
        assert target.exists()

        with pytest.raises(ValueError, match="Project not initialised"):
            AssetManager.ensure_roi_template_dir("")

    def test_list_roi_templates_empty_and_sorted(self):
        am = AssetManager()
        project_data: dict = {}
        templates = am.list_roi_templates(project_data, include_global=False)
        assert templates == []
        assert "roi_templates" in project_data

        project_data["roi_templates"] = [
            {"name": "Template B", "location": "project"},
            {"name": "Template A", "location": "project"},
        ]
        sorted_templates = am.list_roi_templates(project_data, include_global=False)
        assert len(sorted_templates) == 2
        assert sorted_templates[0]["name"] == "Template A"
        assert sorted_templates[1]["name"] == "Template B"

    def test_resolve_roi_template_entry(self):
        project_data = {
            "roi_templates": [
                {"name": "Arena_Standard", "path": "/p1"},
                {"name": "Arena_Circular", "path": "/p2"},
            ]
        }
        idx, entry = AssetManager._resolve_roi_template_entry(project_data, "Arena_Circular")
        assert idx == 1
        assert entry is not None
        assert entry["path"] == "/p2"

        idx_none, entry_none = AssetManager._resolve_roi_template_entry(project_data, "NonExistent")
        assert idx_none is None
        assert entry_none is None

    def test_save_and_remove_roi_template(self, tmp_path: Path):
        am = AssetManager()
        project_data: dict = {}
        zone_data = ZoneData(
            polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
            roi_polygons=[[(1, 1), (2, 1), (2, 2), (1, 2)]],
            roi_names=["ROI_1"],
        )

        def serialize_zone(zd: ZoneData | None) -> dict:
            return {
                "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)],
                "rois": {"ROI_1": [(1, 1), (2, 1), (2, 2), (1, 2)]},
            }

        saved_entry = am.save_roi_template(
            project_data=project_data,
            project_path=tmp_path,
            name="TestTemplate",
            zone_data=zone_data,
            zone_data_to_dict_fn=serialize_zone,
        )
        assert saved_entry["name"] == "TestTemplate"
        assert len(project_data["roi_templates"]) == 1
