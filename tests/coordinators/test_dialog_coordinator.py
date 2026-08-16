"""Testes para DialogCoordinator.

Testes unitários para o coordenador de diálogos,
extraído do MainViewModel na Fase 1 da refatoração.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.dialog_coordinator import DialogCoordinator


@pytest.fixture
def mock_ui_coordinator():
    """Cria UIScheduler mockado."""
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
def dialog_coordinator(
    mock_ui_coordinator, mock_event_bus, mock_state_manager, mock_project_manager
):
    """Cria instância de DialogCoordinator para testes."""
    return DialogCoordinator(
        mock_ui_coordinator, mock_event_bus, mock_state_manager, mock_project_manager
    )


class TestDialogCoordinatorInitialization:
    """Testes de inicialização do coordenador."""

    def test_init_stores_dependencies(
        self, mock_ui_coordinator, mock_event_bus, mock_state_manager
    ):
        """Testa que dependências são armazenadas corretamente."""
        coordinator = DialogCoordinator(mock_ui_coordinator, mock_event_bus, mock_state_manager)

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
            "Exit", "Do you really want to exit?"
        )

    def test_confirm_exit_no(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação de saída quando usuário cancela."""
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.confirm_exit()

        assert result is False


class TestHandleMixedDataScenario:
    """Testes de tratamento de cenário de dados mistos."""

    def test_mixed_case_reprocess_all(self, dialog_coordinator, mock_ui_coordinator):
        """Testa caso misto quando usuário escolhe reprocessar todos."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": False},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)

        assert result == scanned_videos
        assert len(result) == 2

    def test_mixed_case_skip_existing(self, dialog_coordinator, mock_ui_coordinator):
        """Testa caso misto quando usuário escolhe pular existentes."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": False},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)

        assert len(result) == 1
        assert result[0]["path"] == "video2.mp4"

    def test_all_have_data_reprocess(self, dialog_coordinator, mock_ui_coordinator):
        """Testa quando todos têm dados e usuário escolhe reprocessar."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": True},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)

        assert result == scanned_videos
        assert len(result) == 2

    def test_all_have_data_skip(
        self,
        dialog_coordinator,
        mock_ui_coordinator,
        mock_event_bus,
    ):
        """Testa quando todos têm dados e usuário escolhe não reprocessar."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": True},
            {"path": "video2.mp4", "has_data": True},
        ]
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)

        assert result is None
        # Verifica que evento foi publicado
        mock_event_bus.publish.assert_called_once()

    def test_none_have_data(self, dialog_coordinator):
        """Testa quando nenhum vídeo tem dados."""
        scanned_videos = [
            {"path": "video1.mp4", "has_data": False},
            {"path": "video2.mp4", "has_data": False},
        ]

        result = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)

        assert result == scanned_videos
        assert len(result) == 2


class TestShowInfo:
    """Testes de exibição de informações."""

    def test_show_info(self, dialog_coordinator, mock_ui_coordinator):
        """Testa exibição de diálogo informativo."""
        dialog_coordinator.show_info("Test Title", "Test Message")

        mock_ui_coordinator.show_info.assert_called_once_with("Test Title", "Test Message")


class TestShowError:
    """Testes de exibição de erros."""

    def test_show_error(self, dialog_coordinator, mock_ui_coordinator):
        """Testa exibição de diálogo de erro."""
        dialog_coordinator.show_error("Error Title", "Error Message")

        mock_ui_coordinator.show_error.assert_called_once_with("Error Title", "Error Message")


class TestAskYesNo:
    """Testes de confirmação sim/não."""

    def test_ask_yes_no_yes(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação quando usuário responde sim."""
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.ask_yes_no("Confirm", "Are you sure?")

        assert result is True
        mock_ui_coordinator.ask_ok_cancel.assert_called_once_with("Confirm", "Are you sure?")

    def test_ask_yes_no_no(self, dialog_coordinator, mock_ui_coordinator):
        """Testa confirmação quando usuário responde não."""
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.ask_yes_no("Confirm", "Are you sure?")

        assert result is False


class TestValidateZonesWithUi:
    """Tests for video-specific arena validation."""

    def test_uses_selected_video_zones_without_prompt(
        self, dialog_coordinator, mock_project_manager
    ):
        selected_video = "C:/videos/selected.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[[0, 0], [100, 0], [100, 100]],
            roi_polygons=[[[10, 10], [20, 10], [20, 20]]],
        )

        result = dialog_coordinator.validate_zones_with_ui(video_path=selected_video)

        assert result is True
        mock_project_manager.get_multi_aquarium_zone_data.assert_called_once_with(selected_video)
        mock_project_manager.get_zone_data.assert_called_once_with(video_path=selected_video)
        dialog_coordinator.ui_coordinator.ask_ok_cancel.assert_not_called()


class TestShowProcessingSkippedInfo:
    """Testes de exibição de informação de processamento ignorado."""

    def test_show_processing_skipped_with_event_bus(self, dialog_coordinator, mock_event_bus):
        """Testa exibição via EventBus quando disponível."""
        dialog_coordinator._show_processing_skipped_info()

        mock_event_bus.publish.assert_called_once()

    def test_show_processing_skipped_without_event_bus(
        self, mock_ui_coordinator, mock_state_manager
    ):
        """Testa exibição via UIScheduler quando EventBus não disponível."""
        coordinator = DialogCoordinator(mock_ui_coordinator, None, mock_state_manager)

        coordinator._show_processing_skipped_info()

        mock_ui_coordinator.show_info.assert_called_once_with(
            "Processing Skipped",
            "No new video was processed.",
        )


class TestShowWarning:
    def test_show_warning(self, dialog_coordinator, mock_ui_coordinator):
        dialog_coordinator.show_warning("Warning Title", "Warning Message")
        mock_ui_coordinator.show_warning.assert_called_once_with("Warning Title", "Warning Message")


class TestValidateZonesWithUiExtended:
    def test_no_project_manager(self, mock_ui_coordinator, mock_event_bus, mock_state_manager):
        coord = DialogCoordinator(mock_ui_coordinator, mock_event_bus, mock_state_manager, None)
        assert coord.validate_zones_with_ui() is False

    def test_no_main_arena_user_defines_now(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator, mock_event_bus
    ):
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[], roi_polygons=[]
        )
        mock_project_manager.get_next_video.return_value = "video.mp4"

        # User chooses to define now
        mock_ui_coordinator.ask_ok_cancel.return_value = True

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is False
        assert mock_event_bus.publish.call_count >= 2

    def test_no_main_arena_user_declines_default_arena(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[], roi_polygons=[]
        )

        # First ask: define now? -> False. Second ask: use default? -> False.
        mock_ui_coordinator.ask_ok_cancel.side_effect = [False, False]

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is False

    def test_no_main_arena_creates_default_arena_success(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator, mock_event_bus
    ):
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        zone_data = SimpleNamespace(polygon=[], roi_polygons=[[[0, 0], [10, 0], [10, 10]]])
        mock_project_manager.get_zone_data.return_value = zone_data
        mock_project_manager.get_next_video.return_value = "video.mp4"

        # First ask: define now? -> False. Second ask: use default? -> True.
        mock_ui_coordinator.ask_ok_cancel.side_effect = [False, True]

        dialog_coordinator.video_metadata_service.get_video_dimensions = MagicMock(
            return_value=(640, 480)
        )

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is True
        assert zone_data.polygon == [[0, 0], [640, 0], [640, 480], [0, 480]]
        mock_project_manager.save_zone_data.assert_called_once_with(
            zone_data, video_path="video.mp4"
        )

    def test_no_main_arena_creates_default_arena_no_dimensions(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[], roi_polygons=[]
        )
        mock_project_manager.get_next_video.return_value = "video.mp4"

        mock_ui_coordinator.ask_ok_cancel.side_effect = [False, True]
        dialog_coordinator.video_metadata_service.get_video_dimensions = MagicMock(
            return_value=None
        )

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is False
        mock_ui_coordinator.show_error.assert_called_once()

    def test_no_main_arena_creates_default_arena_no_video(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        mock_project_manager.get_active_zone_video.return_value = None
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[], roi_polygons=[]
        )
        mock_project_manager.get_next_video.return_value = None

        mock_ui_coordinator.ask_ok_cancel.side_effect = [False, True]

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is False
        mock_ui_coordinator.show_error.assert_called_once()

    def test_no_rois_user_declines(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[[0, 0], [10, 0], [10, 10]], roi_polygons=[]
        )

        # Prompt for no ROI: user cancels -> False
        mock_ui_coordinator.ask_ok_cancel.return_value = False

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is False

    def test_multi_aquarium_zones_valid(
        self, dialog_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        aq1 = SimpleNamespace(polygon=[(0, 0), (10, 0), (10, 10)])
        aq2 = SimpleNamespace(polygon=[(20, 0), (30, 0), (30, 10)])
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.get_multi_aquarium_zone_data.return_value = SimpleNamespace(
            aquariums=[aq1, aq2]
        )
        mock_project_manager.get_zone_data.return_value = SimpleNamespace(
            polygon=[], roi_polygons=[[[0, 0], [1, 1], [2, 2]]]
        )

        result = dialog_coordinator.validate_zones_with_ui()
        assert result is True


class TestHandleValidationError:
    def test_validation_is_valid(self, dialog_coordinator):
        val = SimpleNamespace(is_valid=True)
        assert dialog_coordinator.handle_validation_error(val) is True

    def test_error_processing_already_active_with_event_bus(
        self, dialog_coordinator, mock_event_bus
    ):
        val = SimpleNamespace(
            is_valid=False,
            error_code="processing_already_active",
            error_message="Already running",
        )
        assert dialog_coordinator.handle_validation_error(val) is False
        mock_event_bus.publish.assert_called_once()

    def test_error_no_project_loaded(self, dialog_coordinator, mock_event_bus):
        val = SimpleNamespace(
            is_valid=False,
            error_code="no_project_loaded",
            error_message="No project",
        )
        assert dialog_coordinator.handle_validation_error(val) is False
        mock_event_bus.publish.assert_called_once()

    def test_error_no_videos(self, dialog_coordinator, mock_event_bus):
        val = SimpleNamespace(
            is_valid=False,
            error_code="no_videos",
            error_message="No videos",
        )
        assert dialog_coordinator.handle_validation_error(val) is False
        mock_event_bus.publish.assert_called_once()

    def test_error_no_weight_selected(self, dialog_coordinator, mock_event_bus):
        val = SimpleNamespace(
            is_valid=False,
            error_code="no_weight_selected",
            error_message="No weight",
        )
        assert dialog_coordinator.handle_validation_error(val) is False
        mock_event_bus.publish.assert_called_once()

    def test_error_generic(self, dialog_coordinator, mock_event_bus):
        val = SimpleNamespace(
            is_valid=False,
            error_code="other_code",
            error_message="Generic error",
        )
        assert dialog_coordinator.handle_validation_error(val) is False
        mock_event_bus.publish.assert_called_once()

    def test_error_without_event_bus(self, mock_ui_coordinator, mock_state_manager):
        coord = DialogCoordinator(mock_ui_coordinator, None, mock_state_manager)

        val_active = SimpleNamespace(
            is_valid=False,
            error_code="processing_already_active",
            error_message="Already running",
        )
        assert coord.handle_validation_error(val_active) is False
        mock_ui_coordinator.show_warning.assert_called_once()

        val_other = SimpleNamespace(
            is_valid=False,
            error_code="other_code",
            error_message="Other error",
        )
        assert coord.handle_validation_error(val_other) is False
        mock_ui_coordinator.show_error.assert_called_once()
