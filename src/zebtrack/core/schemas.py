"""Pydantic schemas para validação de dados JSON."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


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
            raise ValueError(
                f"Template version {v} não suportado. Versão atual: {CURRENT_VERSION}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: dict) -> dict:
        """Valida estrutura básica dos dados."""
        required_keys = {"polygon", "roi_polygons", "roi_names", "roi_colors"}
        missing = required_keys - set(v.keys())
        if missing:
            raise ValueError(f"Chaves obrigatórias ausentes: {missing}")
        return v


class ProjectConfigSchema(BaseModel):
    """Schema para project_config.json."""

    project_name: str = Field(min_length=1, max_length=300)
    project_type: str = Field(pattern=r"^(pre-recorded|live)$")
    timestamp: str
    calibration: dict[str, Any]
    videos: list[dict[str, Any]]

    model_config = {"extra": "allow"}  # Permitir campos adicionais para compatibilidade


class InvalidTemplateError(ValueError):
    """Erro quando template é inválido."""

    pass


class InvalidProjectConfigError(ValueError):
    """Erro quando configuração de projeto é inválida."""

    pass
