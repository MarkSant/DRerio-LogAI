"""
Extended unit tests for project schemas: ROITemplateSchema and ProjectConfigSchema.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zebtrack.core.project.schemas import (
    AssetType,
    InvalidProjectConfigError,
    InvalidTemplateError,
    ProjectConfigSchema,
    ROITemplateSchema,
)


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


class TestProjectConfigSchema:
    def test_valid_prerecorded(self):
        cfg = ProjectConfigSchema(
            project_name="MyProj",
            project_type="pre-recorded",
            timestamp="2025-01-01T00:00:00",
            calibration={"px_per_cm": 10.0},
            videos=[{"path": "video.mp4"}],
        )
        assert cfg.project_name == "MyProj"

    def test_valid_live(self):
        cfg = ProjectConfigSchema(
            project_name="LiveProj",
            project_type="live",
            timestamp="2025-01-01T00:00:00",
            calibration={},
            videos=[],
        )
        assert cfg.project_type == "live"

    def test_invalid_project_type_raises(self):
        with pytest.raises(ValidationError):
            ProjectConfigSchema(
                project_name="Bad",
                project_type="invalid",
                timestamp="2025-01-01",
                calibration={},
                videos=[],
            )

    def test_extra_fields_allowed(self):
        cfg = ProjectConfigSchema.model_validate(
            {
                "project_name": "Compat",
                "project_type": "live",
                "timestamp": "2025-01-01T00:00:00",
                "calibration": {},
                "videos": [],
                "some_future_field": "hello",
            }
        )
        assert cfg.project_name == "Compat"


class TestSchemaErrors:
    def test_invalid_template_error_is_value_error(self):
        assert issubclass(InvalidTemplateError, ValueError)

    def test_invalid_project_config_error_is_value_error(self):
        assert issubclass(InvalidProjectConfigError, ValueError)
