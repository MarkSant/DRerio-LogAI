"""Testes para OrchestratorRegistry.

Testes unitários para o registry de orchestrators,
criado na Fase 2 da refatoração do MainViewModel.

Phase 3A/3B/3C/3D: Removed orchestrators superseded by Super Coordinators:
- analysis, processing_config, zone_arena, calibration, model_diagnostics, project, recording
"""

from unittest.mock import MagicMock

import pytest

from zebtrack.core.orchestrator_registry import OrchestratorRegistry


@pytest.fixture
def mock_orchestrators():
    """Cria mocks de todos os orchestrators."""
    return {
        "ui_state": MagicMock(),
        "video_processing": MagicMock(),
        "live_camera": MagicMock(),
    }


@pytest.fixture
def registry(mock_orchestrators):
    """Cria instância do registry para testes."""
    return OrchestratorRegistry(
        ui_state_controller=mock_orchestrators["ui_state"],
        video_processing_orchestrator=mock_orchestrators["video_processing"],
        live_camera_coordinator=mock_orchestrators["live_camera"],
    )


class TestOrchestratorRegistryInitialization:
    """Testes de inicialização do registry."""

    def test_init(self, registry, mock_orchestrators):
        """Testa inicialização com todos os orchestrators."""
        assert registry.ui_state is mock_orchestrators["ui_state"]
        assert registry.video_processing is mock_orchestrators["video_processing"]
        assert registry.live_camera is mock_orchestrators["live_camera"]


class TestOrchestratorRegistryAccess:
    """Testes de acesso aos orchestrators."""

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

        assert len(all_orch) == 3  # Phase 3A/3B/3C/3D: Reduced from 10 to 3
        assert all_orch["ui_state"] is mock_orchestrators["ui_state"]
        assert all_orch["video_processing"] is mock_orchestrators["video_processing"]
        assert all_orch["live_camera"] is mock_orchestrators["live_camera"]

    def test_get_all_returns_dict(self, registry):
        """Testa que get_all_orchestrators retorna um dict."""
        all_orch = registry.get_all_orchestrators()

        assert isinstance(all_orch, dict)
        assert all(isinstance(key, str) for key in all_orch.keys())
