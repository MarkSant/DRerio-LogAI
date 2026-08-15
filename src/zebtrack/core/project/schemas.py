"""Pydantic schemas para validação de dados JSON."""

from enum import Enum, auto
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetType(Enum):
    """Tipos de assets gerenciados pelo sistema."""

    ROI_TEMPLATE = auto()
    ANALYSIS_PROFILE = auto()
    CALIBRATION = auto()
    MODEL_WEIGHTS = auto()


class ROITemplateSchema(BaseModel):
    """Schema para templates de ROI."""

    # Field descriptions are Pydantic metadata evaluated at class-body
    # time, so they can never be _() calls. They are developer-facing
    # schema documentation, not interface copy.
    version: int = Field(ge=1, le=2, description="Template version")
    name: str = Field(min_length=1, max_length=200, description="Template name")
    data: dict[str, Any] = Field(description="Template data")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Validate that the version is supported."""
        CURRENT_VERSION = 1
        if v > CURRENT_VERSION:
            raise ValueError(
                f"Template version {v} is not supported. Current version: {CURRENT_VERSION}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: dict) -> dict:
        """Validate basic data structure."""
        # Template must have at least arena (polygon) OR ROIs (roi_polygons, roi_names, roi_colors)
        has_polygon = "polygon" in v
        has_rois = all(k in v for k in ("roi_polygons", "roi_names", "roi_colors"))

        if not has_polygon and not has_rois:
            raise ValueError(
                "Template must contain at least an arena (polygon) or ROIs "
                "(roi_polygons, roi_names, roi_colors)"
            )

        # If ROIs are present, all three keys must be present together
        roi_keys = {"roi_polygons", "roi_names", "roi_colors"}
        present_roi_keys = roi_keys & set(v.keys())
        if present_roi_keys and present_roi_keys != roi_keys:
            missing = roi_keys - present_roi_keys
            raise ValueError(f"If ROIs are included, every key must be present. Missing: {missing}")

        return v


class ProjectConfigSchema(BaseModel):
    """Schema para project_config.json."""

    project_name: str = Field(min_length=1, max_length=300)
    project_type: str = Field(pattern=r"^(pre-recorded|live)$")
    timestamp: str
    calibration: dict[str, Any]
    videos: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")  # Allow additional fields for compatibility


class InvalidTemplateError(ValueError):
    """Error when template is invalid."""


class InvalidProjectConfigError(ValueError):
    """Error when project configuration is invalid."""
