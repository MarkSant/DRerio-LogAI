"""Testes para OrchestratorRegistry.

Testes unitários para o registry de orchestrators,
criado na Fase 2 da refatoração do MainViewModel.

Phase 3A/3B/3C/3D: Removed orchestrators superseded by Super Coordinators.
Phase 3 Structural Unification: Removed video_processing (dead stub).
Phase 4.7: Removed live_camera (superseded by LiveCameraSessionCoordinator).
"""

from unittest.mock import MagicMock

import pytest

from zebtrack.core.orchestrator_registry import OrchestratorRegistry


@pytest.fixture
def mock_orchestrators():
    """Cria mocks de todos os orchestrators."""
    return {
        "ui_state": MagicMock(),
    }


@pytest.fixture
def registry(mock_orchestrators):
    """Cria instância do registry para testes."""
    return OrchestratorRegistry(
        ui_state_controller=mock_orchestrators["ui_state"],
    )


class TestOrchestratorRegistryInitialization:
    """Testes de inicialização do registry."""

    def test_init(self, registry, mock_orchestrators):
        """Testa inicialização com todos os orchestrators."""
        assert registry.ui_state is mock_orchestrators["ui_state"]


class TestOrchestratorRegistryAccess:
    """Testes de acesso aos orchestrators."""

    def test_ui_state_access(self, registry):
        """Testa acesso ao UIStateController."""
        assert registry.ui_state is not None
        registry.ui_state.update_status("test")
        registry.ui_state.update_status.assert_called_once_with("test")


class TestOrchestratorRegistryGetAll:
    """Testes do método get_all_orchestrators."""

    def test_get_all_orchestrators(self, registry, mock_orchestrators):
        """Testa que get_all_orchestrators retorna todos os orchestrators."""
        all_orch = registry.get_all_orchestrators()

        assert len(all_orch) == 1  # Phase 4.7: Reduced from 2 to 1
        assert all_orch["ui_state"] is mock_orchestrators["ui_state"]

    def test_get_all_returns_dict(self, registry):
        """Testa que get_all_orchestrators retorna um dict."""
        all_orch = registry.get_all_orchestrators()

        assert isinstance(all_orch, dict)
        assert all(isinstance(key, str) for key in all_orch.keys())
