import json
from pathlib import Path

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.roi_template_manager import ROITemplateManager


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
