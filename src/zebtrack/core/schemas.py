"""Pydantic schemas para validação de dados JSON."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ROITemplateSchema(BaseModel):
    """Schema para templates de ROI."""

    version: int = Field(ge=1, le=2, description="Versão do template")
    name: str = Field(min_length=1, max_length=200, description="Nome do template")
    data: dict[str, Any] = Field(description="Dados do template")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Valida que a versão é suportada."""
        CURRENT_VERSION = 1
        if v > CURRENT_VERSION:
            raise ValueError(f"Template version {v} não suportado. Versão atual: {CURRENT_VERSION}")
        return v

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: dict) -> dict:
        """Valida estrutura básica dos dados."""
        # Template deve ter pelo menos arena (polygon) OU ROIs (roi_polygons, roi_names, roi_colors)
        has_polygon = "polygon" in v
        has_rois = all(k in v for k in ("roi_polygons", "roi_names", "roi_colors"))

        if not has_polygon and not has_rois:
            raise ValueError(
                "Template deve conter pelo menos arena (polygon) ou ROIs "
                "(roi_polygons, roi_names, roi_colors)"
            )

        # Se tem ROIs, valida que as três chaves estão juntas
        roi_keys = {"roi_polygons", "roi_names", "roi_colors"}
        present_roi_keys = roi_keys & set(v.keys())
        if present_roi_keys and present_roi_keys != roi_keys:
            missing = roi_keys - present_roi_keys
            raise ValueError(
                f"Se incluir ROIs, todas as chaves devem estar presentes. Faltam: {missing}"
            )

        return v


class ProjectConfigSchema(BaseModel):
    """Schema para project_config.json."""

    project_name: str = Field(min_length=1, max_length=300)
    project_type: str = Field(pattern=r"^(pre-recorded|live)$")
    timestamp: str
    calibration: dict[str, Any]
    videos: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")  # Permitir campos adicionais para compatibilidade


class InvalidTemplateError(ValueError):
    """Erro quando template é inválido."""


class InvalidProjectConfigError(ValueError):
    """Erro quando configuração de projeto é inválida."""
