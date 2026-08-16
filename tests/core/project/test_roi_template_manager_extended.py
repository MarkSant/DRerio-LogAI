"""
Extended unit tests for ROITemplateManager in project/roi_template_manager.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.roi_template_manager import ROITemplateManager
from zebtrack.core.project.schemas import InvalidTemplateError


class TestROITemplateManagerExtended:
    """Test ROITemplateManager saving, loading, listing, and validation."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> ROITemplateManager:
        mgr = ROITemplateManager()
        # Override global dir to isolated tmp_path
        mgr.global_templates_dir = tmp_path / "global_templates"
        mgr.global_templates_dir.mkdir(parents=True, exist_ok=True)
        return mgr

    def test_slugify(self):
        assert ROITemplateManager._slugify("Arena 1 / Setup") == "arena-1-setup"
        assert ROITemplateManager._slugify("Coração & Teste") == "coracao-teste"
        assert ROITemplateManager._slugify("") == "template"

    def test_save_template_validation_guards(self, manager: ROITemplateManager):
        # Empty name
        with pytest.raises(ValueError, match="name cannot be empty"):
            manager.save_template("", ZoneData())

        # No arena and no ROIs
        with pytest.raises(ValueError, match="at least the arena or the ROIs"):
            manager.save_template("T1", ZoneData(), save_arena=False, save_rois=False)

        # Empty zone data for arena
        with pytest.raises(ValueError, match="Invalid arena"):
            manager.save_template("T1", ZoneData(polygon=[[0, 0]]), save_arena=True)

        # Missing project_path for project location
        with pytest.raises(ValueError, match="project path is required"):
            manager.save_template(
                "T1",
                ZoneData(polygon=[[0, 0], [10, 0], [10, 10]]),
                save_location="project",
                project_path=None,
                save_rois=False,
            )

        # Missing custom_path for custom location
        with pytest.raises(ValueError, match="custom path is required"):
            manager.save_template(
                "T1",
                ZoneData(polygon=[[0, 0], [10, 0], [10, 10]]),
                save_location="custom",
                custom_path=None,
                save_rois=False,
            )

    def test_save_and_load_template_global(self, manager: ROITemplateManager):
        zd = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
            roi_names=["Zone1"],
            roi_colors=[(255, 0, 0)],
        )
        meta = manager.save_template("Standard Tank", zd, save_location="global")
        assert meta["name"] == "Standard Tank"
        assert meta["includes_arena"] is True
        assert meta["includes_rois"] is True
        assert meta["roi_count"] == 1

        # Load template
        loaded_zd = manager.load_template(meta["file"])
        assert loaded_zd.polygon == [[0, 0], [100, 0], [100, 100], [0, 100]]
        assert len(loaded_zd.roi_polygons) == 1
        assert loaded_zd.roi_names == ["Zone1"]
        assert loaded_zd.roi_colors == [(255, 0, 0)]

    def test_save_template_project_location(self, manager: ROITemplateManager, tmp_path: Path):
        proj_dir = tmp_path / "my_project"
        proj_dir.mkdir()
        zd = ZoneData(polygon=[[0, 0], [50, 0], [50, 50]])
        meta = manager.save_template(
            "Project Template",
            zd,
            save_location="project",
            project_path=str(proj_dir),
            save_rois=False,
        )
        assert Path(meta["file"]).parent == proj_dir / "roi_templates"

    def test_load_template_file_not_found(self, manager: ROITemplateManager, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            manager.load_template(tmp_path / "nonexistent.json")

    def test_load_template_invalid_json(self, manager: ROITemplateManager, tmp_path: Path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("invalid json content")
        with pytest.raises(InvalidTemplateError):
            manager.load_template(bad_json)

    def test_list_global_templates(self, manager: ROITemplateManager):
        zd = ZoneData(polygon=[[0, 0], [50, 0], [50, 50]])
        manager.save_template("Template B", zd, save_location="global", save_rois=False)
        manager.save_template("Template A", zd, save_location="global", save_rois=False)

        templates = manager.list_global_templates()
        assert len(templates) == 2
        assert templates[0]["name"] == "Template A"
        assert templates[1]["name"] == "Template B"

    def test_delete_template(self, manager: ROITemplateManager):
        zd = ZoneData(polygon=[[0, 0], [50, 0], [50, 50]])
        meta = manager.save_template("To Delete", zd, save_location="global", save_rois=False)
        assert Path(meta["file"]).exists()

        assert manager.delete_template(meta["file"]) is True
        assert not Path(meta["file"]).exists()

        # Deleting non-existent returns False
        assert manager.delete_template(meta["file"]) is False

    def test_cleanup_orphaned_templates(self, manager: ROITemplateManager, tmp_path: Path):
        # Create a valid template and an invalid JSON file
        zd = ZoneData(polygon=[[0, 0], [50, 0], [50, 50]])
        manager.save_template("Good Template", zd, save_location="global", save_rois=False)

        bad_file = manager.global_templates_dir / "corrupted.json"
        bad_file.write_text("{corrupt")

        stats = manager.cleanup_orphaned_templates()
        assert stats["kept"] == 1
        assert stats["removed"] == 1
        assert not bad_file.exists()
