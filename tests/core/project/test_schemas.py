"""Tests for core Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zebtrack.core.project.schemas import (
    AssetType,
    InvalidTemplateError,
    ROITemplateSchema,
)


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
    with pytest.raises(ValueError, match="Template must contain"):
        ROITemplateSchema(version=1, name="Test", data={})


def test_roi_template_schema_rejects_partial_roi_keys():
    with pytest.raises(ValueError, match="Template must contain"):
        ROITemplateSchema(
            version=1,
            name="Test",
            data={"roi_polygons": [[[0, 0], [1, 0], [1, 1]]]},
        )


def test_roi_template_schema_rejects_future_version():
    with pytest.raises(ValueError, match="is not supported"):
        ROITemplateSchema(version=2, name="Test", data={"polygon": [[0, 0], [1, 0]]})


class TestAssetTypeEnum:
    def test_enum_members(self):
        assert AssetType.ROI_TEMPLATE is not None
        assert AssetType.ANALYSIS_PROFILE is not None
        assert AssetType.CALIBRATION is not None
        assert AssetType.MODEL_WEIGHTS is not None

    def test_unique_values(self):
        vals = [e.value for e in AssetType]
        assert len(vals) == len(set(vals))


class TestROITemplateSchema:
    def test_valid_polygon_only(self):
        schema = ROITemplateSchema(
            version=1,
            name="TestTemplate",
            data={"polygon": [[0, 0], [100, 0], [100, 100], [0, 100]]},
        )
        assert schema.name == "TestTemplate"
        assert schema.version == 1

    def test_valid_rois_only(self):
        schema = ROITemplateSchema(
            version=1,
            name="ROI Template",
            data={
                "roi_polygons": [[[0, 0], [10, 0], [10, 10]]],
                "roi_names": ["Zone A"],
                "roi_colors": ["#FF0000"],
            },
        )
        assert "roi_polygons" in schema.data

    def test_empty_data_raises(self):
        with pytest.raises(ValidationError, match="arena"):
            ROITemplateSchema(version=1, name="Bad", data={})

    def test_partial_roi_keys_raises(self):
        # Only 2 of 3 ROI keys -> fails has_polygon AND has_rois check
        with pytest.raises(ValidationError):
            ROITemplateSchema(
                version=1,
                name="Bad",
                data={"roi_polygons": [], "roi_names": []},  # Missing roi_colors
            )

    def test_version_too_high_raises(self):
        with pytest.raises(ValidationError):
            ROITemplateSchema(
                version=2,
                name="Future",
                data={"polygon": [[0, 0], [1, 0], [1, 1]]},
            )

    def test_version_out_of_bounds_raises(self):
        with pytest.raises(ValidationError):
            ROITemplateSchema(version=0, name="Bad", data={"polygon": []})


class TestSchemaErrors:
    def test_invalid_template_error_is_value_error(self):
        assert issubclass(InvalidTemplateError, ValueError)
