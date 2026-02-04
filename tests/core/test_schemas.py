"""Tests for core Pydantic schemas."""

import pytest

from zebtrack.core.schemas import ProjectConfigSchema, ROITemplateSchema


def test_roi_template_schema_accepts_polygon():
    schema = ROITemplateSchema(
        version=1,
        name="Test",
        data={"polygon": [[0, 0], [1, 0], [1, 1]]},
    )
    assert schema.version == 1


def test_roi_template_schema_accepts_rois():
    schema = ROITemplateSchema(
        version=1,
        name="Test",
        data={
            "roi_polygons": [[[0, 0], [1, 0], [1, 1]]],
            "roi_names": ["ROI1"],
            "roi_colors": [[255, 0, 0]],
        },
    )
    assert schema.data["roi_names"] == ["ROI1"]


def test_roi_template_schema_rejects_missing_data():
    with pytest.raises(ValueError, match="Template deve conter"):
        ROITemplateSchema(version=1, name="Test", data={})


def test_roi_template_schema_rejects_partial_roi_keys():
    with pytest.raises(ValueError, match="Template deve conter"):
        ROITemplateSchema(
            version=1,
            name="Test",
            data={"roi_polygons": [[[0, 0], [1, 0], [1, 1]]] },
        )


def test_roi_template_schema_rejects_future_version():
    with pytest.raises(ValueError, match="não suportado"):
        ROITemplateSchema(version=2, name="Test", data={"polygon": [[0, 0], [1, 0]]})


def test_project_config_schema_allows_extra_fields():
    schema = ProjectConfigSchema.model_validate(
        {
            "project_name": "Test Project",
            "project_type": "live",
            "timestamp": "2026-02-03T00:00:00",
            "calibration": {},
            "videos": [],
            "extra_field": "ok",
        }
    )

    assert schema.project_name == "Test Project"
    assert schema.model_dump()["extra_field"] == "ok"
