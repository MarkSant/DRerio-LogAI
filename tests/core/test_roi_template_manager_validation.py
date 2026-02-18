"""Tests for Pydantic validation in ROITemplateManager."""

import json

import pytest

from zebtrack.core.project.roi_template_manager import ROITemplateManager
from zebtrack.core.project.schemas import InvalidTemplateError


@pytest.fixture
def roi_manager(tmp_path, monkeypatch):
    """Cria ROITemplateManager com diretório temporário."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    manager = ROITemplateManager()
    return manager


class TestROITemplateValidation:
    """Testes de validação de templates."""

    def test_load_template_with_invalid_json(self, roi_manager, tmp_path):
        """Template com JSON inválido deve falhar."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("{invalid json}", encoding="utf-8")

        with pytest.raises(InvalidTemplateError, match="JSON inválido"):
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

        with pytest.raises(InvalidTemplateError, match="pelo menos arena"):
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

        with pytest.raises(InvalidTemplateError, match="pelo menos arena"):
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
