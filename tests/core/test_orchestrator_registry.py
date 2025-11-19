"""Testes para OrchestratorRegistry.

Testes unitários para o registry de orchestrators,
criado na Fase 2 da refatoração do MainViewModel.
"""

from unittest.mock import MagicMock

import pytest

from zebtrack.core.orchestrator_registry import OrchestratorRegistry


@pytest.fixture
def mock_orchestrators():
    """Cria mocks de todos os orchestrators."""
    return {
        "recording_session": MagicMock(),
        "project": MagicMock(),
        "ui_state": MagicMock(),
        "video_processing": MagicMock(),
        "analysis": MagicMock(),
        "processing_config": MagicMock(),
        "model_diagnostics": MagicMock(),
        "zone_arena": MagicMock(),
        "calibration": MagicMock(),
        "live_camera": MagicMock(),
    }


@pytest.fixture
def registry(mock_orchestrators):
    """Cria instância do registry para testes."""
    return OrchestratorRegistry(
        recording_session_orchestrator=mock_orchestrators["recording_session"],
        project_orchestrator=mock_orchestrators["project"],
        ui_state_controller=mock_orchestrators["ui_state"],
        video_processing_orchestrator=mock_orchestrators["video_processing"],
        analysis_orchestrator=mock_orchestrators["analysis"],
        processing_config_orchestrator=mock_orchestrators["processing_config"],
        model_diagnostics_orchestrator=mock_orchestrators["model_diagnostics"],
        zone_arena_orchestrator=mock_orchestrators["zone_arena"],
        calibration_orchestrator=mock_orchestrators["calibration"],
        live_camera_coordinator=mock_orchestrators["live_camera"],
    )


class TestOrchestratorRegistryInitialization:
    """Testes de inicialização do registry."""

    def test_init(self, registry, mock_orchestrators):
        """Testa inicialização com todos os orchestrators."""
        assert registry.recording is mock_orchestrators["recording_session"]
        assert registry.project is mock_orchestrators["project"]
        assert registry.ui_state is mock_orchestrators["ui_state"]
        assert registry.video_processing is mock_orchestrators["video_processing"]
        assert registry.analysis is mock_orchestrators["analysis"]
        assert registry.processing_config is mock_orchestrators["processing_config"]
        assert registry.model_diagnostics is mock_orchestrators["model_diagnostics"]
        assert registry.zone_arena is mock_orchestrators["zone_arena"]
        assert registry.calibration is mock_orchestrators["calibration"]
        assert registry.live_camera is mock_orchestrators["live_camera"]


class TestOrchestratorRegistryAccess:
    """Testes de acesso aos orchestrators."""

    def test_recording_access(self, registry):
        """Testa acesso ao RecordingSessionOrchestrator."""
        assert registry.recording is not None
        registry.recording.start_recording()
        registry.recording.start_recording.assert_called_once()

    def test_project_access(self, registry):
        """Testa acesso ao ProjectOrchestrator."""
        assert registry.project is not None
        registry.project.close_project()
        registry.project.close_project.assert_called_once()

    def test_ui_state_access(self, registry):
        """Testa acesso ao UIStateController."""
        assert registry.ui_state is not None
        registry.ui_state.update_status("test")
        registry.ui_state.update_status.assert_called_once_with("test")

    def test_video_processing_access(self, registry):
        """Testa acesso ao VideoProcessingOrchestrator."""
        assert registry.video_processing is not None
        registry.video_processing.process_video("test.mp4")
        registry.video_processing.process_video.assert_called_once_with("test.mp4")

    def test_analysis_access(self, registry):
        """Testa acesso ao AnalysisOrchestrator."""
        assert registry.analysis is not None
        registry.analysis.run_analysis()
        registry.analysis.run_analysis.assert_called_once()

    def test_processing_config_access(self, registry):
        """Testa acesso ao ProcessingConfigOrchestrator."""
        assert registry.processing_config is not None
        registry.processing_config.get_config()
        registry.processing_config.get_config.assert_called_once()

    def test_model_diagnostics_access(self, registry):
        """Testa acesso ao ModelDiagnosticsOrchestrator."""
        assert registry.model_diagnostics is not None
        registry.model_diagnostics.run_diagnostics()
        registry.model_diagnostics.run_diagnostics.assert_called_once()

    def test_zone_arena_access(self, registry):
        """Testa acesso ao ZoneArenaOrchestrator."""
        assert registry.zone_arena is not None
        registry.zone_arena.setup_zones()
        registry.zone_arena.setup_zones.assert_called_once()

    def test_calibration_access(self, registry):
        """Testa acesso ao CalibrationOrchestrator."""
        assert registry.calibration is not None
        registry.calibration.calibrate()
        registry.calibration.calibrate.assert_called_once()

    def test_live_camera_access(self, registry):
        """Testa acesso ao LiveCameraCoordinator."""
        assert registry.live_camera is not None
        registry.live_camera.start()
        registry.live_camera.start.assert_called_once()


class TestOrchestratorRegistryGetAll:
    """Testes do método get_all_orchestrators."""

    def test_get_all_orchestrators(self, registry, mock_orchestrators):
        """Testa que get_all_orchestrators retorna todos os orchestrators."""
        all_orch = registry.get_all_orchestrators()

        assert len(all_orch) == 10
        assert all_orch["recording"] is mock_orchestrators["recording_session"]
        assert all_orch["project"] is mock_orchestrators["project"]
        assert all_orch["ui_state"] is mock_orchestrators["ui_state"]
        assert all_orch["video_processing"] is mock_orchestrators["video_processing"]
        assert all_orch["analysis"] is mock_orchestrators["analysis"]
        assert all_orch["processing_config"] is mock_orchestrators["processing_config"]
        assert all_orch["model_diagnostics"] is mock_orchestrators["model_diagnostics"]
        assert all_orch["zone_arena"] is mock_orchestrators["zone_arena"]
        assert all_orch["calibration"] is mock_orchestrators["calibration"]
        assert all_orch["live_camera"] is mock_orchestrators["live_camera"]

    def test_get_all_returns_dict(self, registry):
        """Testa que get_all_orchestrators retorna um dict."""
        all_orch = registry.get_all_orchestrators()

        assert isinstance(all_orch, dict)
        assert all(isinstance(key, str) for key in all_orch.keys())
