"""Testes para DialogCoordinator.

Testes unitários para o coordenador de diálogos,
extraído do MainViewModel na Fase 1 da refatoração.
"""

from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.dialog_coordinator import DialogCoordinator


@pytest.fixture
def mock_ui_coordinator():
    """Cria UICoordinator mockado."""
    coordinator = MagicMock()
    coordinator.ask_ok_cancel.return_value = True
    coordinator.show_info.return_value = None
    coordinator.show_error.return_value = None
    return coordinator


@pytest.fixture
def mock_event_bus():
    """Cria EventBus mockado."""
    bus = MagicMock()
    return bus


@pytest.fixture
def mock_state_manager():
    """Cria StateManager mockado."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_project_manager():
    """Cria ProjectManager mockado."""
    manager = MagicMock()
    manager.add_video_batch.return_value = None
    return manager


@pytest.fixture
def dialog_coordinator(mock_ui_coordinator, mock_event_bus, mock_state_manager):
    """Cria instância de DialogCoordinator para testes."""
    return DialogCoordinator(
        mock_ui_coordinator, mock_event_bus, mock_state_manager
    )


class TestDialogCoordinatorInitialization:
    """Testes de inicialização do coordenador."""

    def test_init_stores_dependencies(
        self, mock_ui_coordinator, mock_event_bus, mock_state_manager
    ):
        """Testa que dependências são armazenadas corretamente."""
        coordinator = DialogCoordinator(
            mock_ui_coordinator, mock_event_bus, mock_state_manager
        )

        assert coordinator.ui_coordinator is mock_ui_coordinator
        assert coordinator.event_bus is mock_event_bus
        assert coordinator.state_manager is mock_state_manager
        assert coordinator.log is not None


class TestConfirmExit:
    """Testes de confirmação de saída."""

    def test_confirm_exit_yes(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação de saída quando usuário aceita."""
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.confirm_exit()

        assert result is True
        mock_ui_coordinator.ask_ok_cancel.assert_called_once_with(
            "Sair", "Deseja realmente sair?"
        )

    def test_confirm_exit_no(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação de saída quando usuário cancela."""
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.confirm_exit()

        assert result is False


class TestHandleMixedDataScenario:
    """Testes de tratamento de cenário de dados mistos."""

    def test_mixed_case_reprocess_all(
        self, dialog_coordinator, mock_ui_coordinator, mock_project_manager
    ):
        """Testa caso misto quando usuário escolhe reprocessar todos."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": False},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, mock_project_manager
        )

        assert result == scanned_videos
        assert len(result) == 2

    def test_mixed_case_skip_existing(
        self, dialog_coordinator, mock_ui_coordinator, mock_project_manager
    ):
        """Testa caso misto quando usuário escolhe pular existentes."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": False},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, mock_project_manager
        )

        assert len(result) == 1
        assert result[0]["path"] == "video2.mp4"

    def test_all_have_data_reprocess(
        self, dialog_coordinator, mock_ui_coordinator, mock_project_manager
    ):
        """Testa quando todos têm dados e usuário escolhe reprocessar."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": True},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, mock_project_manager
        )

        assert result == scanned_videos
        assert len(result) == 2

    def test_all_have_data_skip(
        self,
        dialog_coordinator,
        mock_ui_coordinator,
        mock_event_bus,
        mock_project_manager,
    ):
        """Testa quando todos têm dados e usuário escolhe não reprocessar."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": True},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, mock_project_manager
        )

        assert result is None
        mock_project_manager.add_video_batch.assert_called_once_with(
            scanned_videos
        )
        # Verifica que evento foi publicado
        mock_event_bus.publish_event.assert_called_once()

    def test_none_have_data(
        self, dialog_coordinator, mock_project_manager
    ):
        """Testa quando nenhum vídeo tem dados."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": False},
            {"path": "video2.mp4", "has_data": False},
        ]

        result = dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, mock_project_manager
        )

        assert result == scanned_videos
        assert len(result) == 2


class TestShowInfo:
    """Testes de exibição de informações."""

    def test_show_info(self, dialog_coordinator, mock_ui_coordinator):
        """Testa exibição de diálogo informativo."""
        dialog_coordinator.show_info("Test Title", "Test Message")

        mock_ui_coordinator.show_info.assert_called_once_with(
            "Test Title", "Test Message"
        )


class TestShowError:
    """Testes de exibição de erros."""

    def test_show_error(self, dialog_coordinator, mock_ui_coordinator):
        """Testa exibição de diálogo de erro."""
        dialog_coordinator.show_error("Error Title", "Error Message")

        mock_ui_coordinator.show_error.assert_called_once_with(
            "Error Title", "Error Message"
        )


class TestAskYesNo:
    """Testes de confirmação sim/não."""

    def test_ask_yes_no_yes(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação quando usuário responde sim."""
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.ask_yes_no("Confirm", "Are you sure?")

        assert result is True
        mock_ui_coordinator.ask_ok_cancel.assert_called_once_with(
            "Confirm", "Are you sure?"
        )

    def test_ask_yes_no_no(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação quando usuário responde não."""
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.ask_yes_no("Confirm", "Are you sure?")

        assert result is False


class TestShowProcessingSkippedInfo:
    """Testes de exibição de informação de processamento ignorado."""

    def test_show_processing_skipped_with_event_bus(
        self, dialog_coordinator, mock_event_bus
    ):
        """Testa exibição via EventBus quando disponível."""
        dialog_coordinator._show_processing_skipped_info()

        mock_event_bus.publish_event.assert_called_once()

    def test_show_processing_skipped_without_event_bus(
        self, mock_ui_coordinator, mock_state_manager
    ):
        """Testa exibição via UICoordinator quando EventBus não disponível."""
        coordinator = DialogCoordinator(
            mock_ui_coordinator, None, mock_state_manager
        )

        coordinator._show_processing_skipped_info()

        mock_ui_coordinator.show_info.assert_called_once_with(
            "Processamento Ignorado",
            "Nenhum novo vídeo foi processado.",
        )
