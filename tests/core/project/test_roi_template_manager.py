"""Tests for Pydantic validation in ROITemplateManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.roi_template_manager import ROITemplateManager
from zebtrack.core.project.schemas import InvalidTemplateError


@pytest.fixture
def roi_manager(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    manager = ROITemplateManager()
    return manager


def _example_zone_data(*, include_arena=True, include_rois=True) -> ZoneData:
    polygon = []
    roi_polygons = []
    roi_names = []
    roi_colors = []

    if include_arena:
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]

    if include_rois:
        roi_polygons = [
            [[10, 10], [40, 10], [40, 40], [10, 40]],
        ]
        roi_names = ["Zona-1"]
        roi_colors = [(255, 0, 0)]

    return ZoneData(
        polygon=polygon,
        roi_polygons=roi_polygons,
        roi_names=roi_names,
        roi_colors=roi_colors,
    )


def test_save_template_global_creates_file_and_metadata(
    roi_manager: ROITemplateManager,
):
    zone = _example_zone_data()

    metadata = roi_manager.save_template(
        "Template Global",
        zone,
        save_location="global",
        save_arena=True,
        save_rois=True,
    )

    saved_path = Path(metadata["file"])
    assert saved_path.exists()
    assert metadata["location"] == "global"
    assert metadata["includes_arena"] is True
    assert metadata["includes_rois"] is True

    loaded = roi_manager.load_template(saved_path)
    assert loaded.polygon == zone.polygon
    assert loaded.roi_polygons == zone.roi_polygons


def test_save_template_project_honors_destination(
    tmp_path,
    roi_manager: ROITemplateManager,
):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    zone = _example_zone_data()

    metadata = roi_manager.save_template(
        "Template Projeto",
        zone,
        save_location="project",
        project_path=project_dir,
        save_arena=True,
        save_rois=False,
    )

    template_path = project_dir / "roi_templates" / f"{metadata['slug']}.json"
    assert template_path.exists()

    payload = json.loads(template_path.read_text(encoding="utf-8"))
    assert payload["includes_arena"] is True
    assert payload["includes_rois"] is False
    assert "roi_polygons" not in payload["data"]


def test_save_template_roi_only_requires_roi_data(roi_manager: ROITemplateManager):
    zone = _example_zone_data(include_arena=False, include_rois=True)

    metadata = roi_manager.save_template(
        "Somente ROIs",
        zone,
        save_location="global",
        save_arena=False,
        save_rois=True,
    )

    saved_path = Path(metadata["file"])
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))

    assert "polygon" not in saved_payload["data"]
    assert saved_payload["data"]["roi_polygons"]
    assert metadata["roi_count"] == len(zone.roi_polygons)


def test_save_template_requires_component_selection(roi_manager: ROITemplateManager):
    zone = _example_zone_data()

    with pytest.raises(ValueError):
        roi_manager.save_template(
            "Inválido",
            zone,
            save_location="global",
            save_arena=False,
            save_rois=False,
        )


def test_list_global_templates_sorted_by_name(roi_manager: ROITemplateManager):
    zone = _example_zone_data()
    roi_manager.save_template("Beta", zone, save_location="global")
    roi_manager.save_template("alfa", zone, save_location="global")

    names = [item["name"] for item in roi_manager.list_global_templates()]
    assert names == ["alfa", "Beta"]


class TestROITemplateValidation:
    """Testes de validação de templates."""

    def test_load_template_with_invalid_json(self, roi_manager, tmp_path):
        """A template with invalid JSON must fail."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("{invalid json}", encoding="utf-8")

        with pytest.raises(InvalidTemplateError, match="Invalid JSON"):
            roi_manager.load_template(invalid_file)

    def test_load_template_with_missing_fields(self, roi_manager, tmp_path):
        """Template com campos obrigatórios faltando deve falhar."""
        incomplete_file = tmp_path / "incomplete.json"
        incomplete_file.write_text(
            json.dumps({"version": 1, "name": "Test"}),  # Falta 'data'
            encoding="utf-8",
        )

        with pytest.raises(InvalidTemplateError, match="Field required"):
            roi_manager.load_template(incomplete_file)

    def test_load_template_with_future_version(self, roi_manager, tmp_path):
        """Template com versão futura deve falhar."""
        future_file = tmp_path / "future.json"
        future_file.write_text(
            json.dumps(
                {
                    "version": 999,
                    "name": "Future Template",
                    "data": {
                        "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                        "roi_polygons": [],
                        "roi_names": [],
                        "roi_colors": [],
                    },
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(InvalidTemplateError, match="less than or equal"):
            roi_manager.load_template(future_file)

    def test_load_template_with_invalid_data_structure(self, roi_manager, tmp_path):
        """Template com estrutura de dados inválida deve falhar."""
        # Caso 1: Template sem arena NEM ROIs
        empty_template = tmp_path / "empty_structure.json"
        empty_template.write_text(
            json.dumps(
                {
                    "version": 1,
                    "name": "Empty Template",
                    "data": {},  # Não tem arena nem ROIs
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(InvalidTemplateError, match="at least an arena"):
            roi_manager.load_template(empty_template)

        # Caso 2: Template com ROIs incompletas (faltam roi_names e roi_colors)
        incomplete_rois = tmp_path / "incomplete_rois.json"
        incomplete_rois.write_text(
            json.dumps(
                {
                    "version": 1,
                    "name": "Incomplete ROIs",
                    "data": {
                        "roi_polygons": [[[10, 10], [20, 10], [20, 20]]],
                        # Faltam: roi_names, roi_colors
                    },
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(InvalidTemplateError, match="at least an arena"):
            roi_manager.load_template(incomplete_rois)

    def test_load_valid_template_succeeds(self, roi_manager, tmp_path):
        """Template válido deve carregar com sucesso."""
        valid_file = tmp_path / "valid.json"
        valid_data = {
            "version": 1,
            "name": "Valid Template",
            "data": {
                "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "roi_polygons": [[[10, 10], [20, 10], [20, 20], [10, 20]]],
                "roi_names": ["ROI1"],
                "roi_colors": [[255, 0, 0]],
            },
        }
        valid_file.write_text(json.dumps(valid_data), encoding="utf-8")

        result = roi_manager.load_template(valid_file)

        assert result.polygon == [[0, 0], [100, 0], [100, 100], [0, 100]]
        assert len(result.roi_polygons) == 1
        assert result.roi_names == ["ROI1"]
        assert len(result.roi_colors) == 1


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


# ---------------------------------------------------------------------------
# TASK-087: save guards, custom destinations and a corrupt global folder.
# ---------------------------------------------------------------------------


class TestSaveTemplateDestinations:
    def test_guards_name_the_missing_piece(self, roi_manager, tmp_path):
        two_points = ZoneData(polygon=[[0, 0], [1, 1]], roi_polygons=[[[0, 0], [1, 0], [1, 1]]])

        with pytest.raises(ValueError, match="at least 3 points"):
            roi_manager.save_template("T", two_points)
        with pytest.raises(ValueError, match="No ROI available"):
            roi_manager.save_template("T", ZoneData(polygon=[[0, 0], [1, 0], [1, 1]]))
        with pytest.raises(ValueError, match="project path is required"):
            roi_manager.save_template("T", two_points, save_arena=False, save_location="project")
        with pytest.raises(ValueError, match="custom path is required"):
            roi_manager.save_template("T", two_points, save_arena=False, save_location="custom")
        with pytest.raises(ValueError, match="Invalid save_location"):
            roi_manager.save_template(
                "T",
                two_points,
                save_arena=False,
                save_location="remote",  # type: ignore[arg-type]
            )

    def test_custom_file_path_saves_next_to_it_and_refuses_to_overwrite(
        self, roi_manager, tmp_path
    ):
        zone = ZoneData(roi_polygons=[[[0, 0], [1, 0], [1, 1]]], roi_names=["r"])
        target = tmp_path / "out" / "chosen.json"

        meta = roi_manager.save_template(
            "Ação!", zone, save_arena=False, save_location="custom", custom_path=target, slug=""
        )

        saved = tmp_path / "out" / "acao.json"
        assert meta["file"] == str(saved)
        assert json.loads(saved.read_text(encoding="utf-8"))["data"] == {
            "roi_polygons": [[[0, 0], [1, 0], [1, 1]]],
            "roi_names": ["r"],
            "roi_colors": [],
        }
        with pytest.raises(ValueError, match="already exists"):
            roi_manager.save_template(
                "Ação!",
                zone,
                save_arena=False,
                save_location="custom",
                custom_path=tmp_path / "out",
                overwrite=False,
            )

    def test_unreadable_global_entries_are_skipped(self, roi_manager):
        folder = roi_manager.global_templates_dir
        (folder / "broken.json").write_text("{nope", encoding="utf-8")
        (folder / "dir.json").mkdir()
        (folder / "ok.json").write_text(
            json.dumps({"name": "Ok", "data": {"roi_polygons": [[], []]}}), encoding="utf-8"
        )

        listed = roi_manager.list_global_templates()

        assert [(t["name"], t["roi_count"]) for t in listed] == [("Ok", 2)]
