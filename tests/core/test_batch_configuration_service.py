"""Testes para BatchConfigurationService.

Testes unitários para o serviço de aplicação de configurações em lote,
extraído do MainViewModel na Fase 1 da refatoração.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from zebtrack.core.batch_configuration_service import BatchConfigurationService
from zebtrack.core.detector import ZoneData


@pytest.fixture
def mock_project_manager():
    """Cria um ProjectManager mockado para testes."""
    manager = MagicMock()
    manager.project_path = Path("/test/project")
    manager.project_data = {
        "active_weight": "yolo11n",
        "use_openvino": True,
        "calibration": {"scale_cm_per_pixel": 0.5},
        "timestamp": "2025-01-19T10:00:00",
        "analysis_interval_frames": 5,
        "display_interval_frames": 10,
    }
    manager.get_project_name.return_value = "test_project"
    manager.get_detector_state.return_value = {"model": "yolo11n", "device": "cpu"}
    manager.resolve_results_directory.return_value = Path("/test/results/video1_results")
    return manager


@pytest.fixture
def mock_zone_data():
    """Cria dados de zona reais para testes."""
    return ZoneData(
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        roi_polygons=[[[10, 10], [50, 10], [50, 50], [10, 50]]],
        roi_names=["ROI1"],
        roi_colors=[(255, 0, 0)],
    )


@pytest.fixture
def mock_settings():
    """Cria Settings mockado."""
    settings = MagicMock()
    return settings


@pytest.fixture
def batch_service(mock_project_manager, mock_settings):
    """Cria instância de BatchConfigurationService para testes."""
    return BatchConfigurationService(mock_project_manager, mock_settings)


class TestBatchConfigurationServiceInitialization:
    """Testes de inicialização do serviço."""

    def test_init_stores_dependencies(self, mock_project_manager, mock_settings):
        """Testa que dependências são armazenadas corretamente."""
        service = BatchConfigurationService(mock_project_manager, mock_settings)

        assert service.project_manager is mock_project_manager
        assert service.settings is mock_settings
        assert service.log is not None


class TestValidateProject:
    """Testes de validação de projeto."""

    def test_validate_project_success(self, batch_service):
        """Testa validação bem-sucedida quando projeto está carregado."""
        result = batch_service._validate_project()

        assert result is True

    def test_validate_project_no_project_path(self, batch_service):
        """Testa falha quando projeto não está carregado."""
        batch_service.project_manager.project_path = None

        result = batch_service._validate_project()

        assert result is False


class TestBuildConfiguration:
    """Testes de construção de configuração."""

    def test_build_configuration_with_zones(self, batch_service, mock_zone_data):
        """Testa construção de configuração com zonas."""
        batch_service.project_manager.get_zone_data.return_value = mock_zone_data

        config = batch_service._build_configuration()

        assert "zone_data" in config
        assert "calibration" in config
        assert "project_data" in config
        assert config["has_zones"] is True
        assert config["has_calibration"] is True
        assert config["has_rois"] == 1

    def test_build_configuration_without_zones(self, batch_service):
        """Testa construção de configuração sem zonas."""
        batch_service.project_manager.get_zone_data.return_value = None

        config = batch_service._build_configuration()

        assert config["has_zones"] is False
        assert config["has_rois"] == 0

    def test_build_configuration_without_calibration(self, batch_service, mock_zone_data):
        """Testa construção de configuração sem calibração."""
        batch_service.project_manager.project_data = {}
        batch_service.project_manager.get_zone_data.return_value = mock_zone_data

        config = batch_service._build_configuration()

        assert config["calibration"] == {}
        assert config["has_calibration"] is False


class TestApplyToSingleVideo:
    """Testes de aplicação a vídeo único."""

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_apply_to_single_video_success(
        self, mock_mkdir, mock_file, batch_service, mock_zone_data
    ):
        """Testa aplicação bem-sucedida de configurações a um vídeo."""
        video_info = {"path": "/test/video1.mp4"}
        config = {
            "zone_data": mock_zone_data,
            "calibration": {"scale_cm_per_pixel": 0.5},
            "project_data": batch_service.project_manager.project_data,
            "has_zones": True,
            "has_calibration": True,
            "has_rois": 1,
        }

        result = batch_service._apply_to_single_video(video_info, config)

        assert result is True
        mock_mkdir.assert_called()
        assert mock_file.call_count >= 2  # project_settings.json + zones.json

    def test_apply_to_single_video_no_path(self, batch_service):
        """Testa falha quando vídeo não tem path."""
        video_info: dict[str, object] = {}
        config: dict[str, object] = {}

        result = batch_service._apply_to_single_video(video_info, config)

        assert result is False

    @patch("builtins.open", side_effect=OSError("Write error"))
    @patch("pathlib.Path.mkdir")
    def test_apply_to_single_video_error(self, mock_mkdir, mock_file, batch_service):
        """Testa tratamento de erro ao salvar configurações."""
        video_info: dict[str, object] = {"path": "/test/video1.mp4"}
        config: dict[str, object] = {
            "zone_data": None,
            "calibration": {},
            "project_data": {},
            "has_zones": False,
            "has_calibration": False,
            "has_rois": 0,
        }

        result = batch_service._apply_to_single_video(video_info, config)

        assert result is False


class TestSaveProjectSettings:
    """Testes de salvamento de configurações do projeto."""

    @patch("builtins.open", new_callable=mock_open)
    def test_save_project_settings(self, mock_file, batch_service):
        """Testa salvamento de project_settings.json."""
        results_path = Path("/test/results")
        video_info = {"path": "/test/video1.mp4", "fps": 30}
        config = {
            "calibration": {"scale_cm_per_pixel": 0.5},
            "project_data": batch_service.project_manager.project_data,
        }

        batch_service._save_project_settings(results_path, video_info, config)

        mock_file.assert_called_once()
        handle = mock_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        data = json.loads(written_data)

        assert data["project_name"] == "test_project"
        assert data["active_weight"] == "yolo11n"
        assert data["use_openvino"] is True
        assert data["calibration"] == {"scale_cm_per_pixel": 0.5}
        assert data["video_settings"] == video_info


class TestSaveZoneData:
    """Testes de salvamento de dados de zona."""

    @patch("builtins.open", new_callable=mock_open)
    def test_save_zone_data_with_zones(self, mock_file, batch_service, mock_zone_data):
        """Testa salvamento de zones.json quando há zonas."""
        results_path = Path("/test/results")
        experiment_id = "video1"
        config = {"zone_data": mock_zone_data}

        batch_service._save_zone_data(results_path, experiment_id, config)

        mock_file.assert_called_once()

    def test_save_zone_data_without_zones(self, batch_service):
        """Testa que zones.json não é salvo quando não há zonas."""
        results_path = Path("/test/results")
        experiment_id = "video1"

        zone_data = ZoneData(polygon=[], roi_polygons=[], roi_names=[], roi_colors=[])
        config = {"zone_data": zone_data}

        with patch("builtins.open", new_callable=mock_open) as mock_file:
            batch_service._save_zone_data(results_path, experiment_id, config)
            mock_file.assert_not_called()

    def test_save_zone_data_no_zone_data(self, batch_service):
        """Testa que zones.json não é salvo quando zone_data é None."""
        results_path = Path("/test/results")
        experiment_id = "video1"
        config = {"zone_data": None}

        with patch("builtins.open", new_callable=mock_open) as mock_file:
            batch_service._save_zone_data(results_path, experiment_id, config)
            mock_file.assert_not_called()


class TestApplySettings:
    """Testes de aplicação de configurações ao lote."""

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_apply_settings_success_all_videos(
        self, mock_mkdir, mock_file, batch_service, mock_zone_data
    ):
        """Testa aplicação bem-sucedida a todos os vídeos."""
        batch_service.project_manager.get_zone_data.return_value = mock_zone_data
        videos: list[dict[str, object]] = [
            {"path": "/test/video1.mp4"},
            {"path": "/test/video2.mp4"},
        ]

        result = batch_service.apply_settings(videos)

        assert result is True

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_apply_settings_partial_success(
        self, mock_mkdir, mock_file, batch_service, mock_zone_data
    ):
        """Testa quando apenas alguns vídeos têm configurações aplicadas."""
        batch_service.project_manager.get_zone_data.return_value = mock_zone_data
        videos: list[dict[str, object]] = [
            {"path": "/test/video1.mp4"},
            {},  # Sem path - vai falhar
        ]

        result = batch_service.apply_settings(videos)

        assert result is False

    def test_apply_settings_no_project(self, batch_service):
        """Testa falha quando não há projeto carregado."""
        batch_service.project_manager.project_path = None
        videos: list[dict[str, object]] = [{"path": "/test/video1.mp4"}]

        result = batch_service.apply_settings(videos)

        assert result is False

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_apply_settings_empty_list(self, mock_mkdir, mock_file, batch_service):
        """Testa aplicação com lista vazia de vídeos."""
        videos: list[dict[str, object]] = []

        result = batch_service.apply_settings(videos)

        assert result is True  # Nenhum vídeo para processar = sucesso


class TestPrepareResultsDirectory:
    """Testes de preparação de diretório de resultados."""

    @patch("pathlib.Path.mkdir")
    def test_prepare_results_directory(self, mock_mkdir, batch_service):
        """Testa criação de diretório de resultados."""
        results_path = Path("/test/results")

        batch_service._prepare_results_directory(results_path)

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
