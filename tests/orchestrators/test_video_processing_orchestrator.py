"""Unit tests for :mod:`zebtrack.orchestrators.video_processing_orchestrator`.

Phase 3E Consolidation: VideoProcessingOrchestrator is now a thin wrapper.
Most methods have been moved to ProcessingCoordinator.
These tests verify the remaining UI orchestration functionality.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.orchestrators.video_processing_orchestrator import (
    VideoProcessingOrchestrator,
)
from zebtrack.ui.events import Events


class DummyEventBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, event: str, payload: dict):
        self.events.append((event, payload))


class DummyView:
    def __init__(self):
        self.dialog_response: dict | None = None
        self.dialog_calls: list[dict] = []
        self.file_dialog_response: list[str] | None = None

    def show_pending_videos_dialog(self, **kwargs):
        self.dialog_calls.append(kwargs)
        return self.dialog_response

    def ask_open_filenames(self, title, filetypes):
        return self.file_dialog_response


class DummyMainViewModel:
    def __init__(self):
        self.view = DummyView()
        self.ui_event_bus = DummyEventBus()
        self.cancel_event = MagicMock()
        self.project_manager = MagicMock()
        self.processing_coordinator = MagicMock()
        self.dialog_coordinator = MagicMock()
        self.ui_state_controller = MagicMock()
        self._cancel_feedback_displayed = False


@pytest.fixture()
def orchestrator_setup():
    main_view_model = DummyMainViewModel()
    orchestrator = VideoProcessingOrchestrator(main_view_model)
    return orchestrator, main_view_model


def test_register_event_handlers_is_noop(orchestrator_setup):
    """Phase 3E: register_event_handlers should be a no-op."""
    orchestrator, _ = orchestrator_setup
    # Should not raise
    orchestrator.register_event_handlers()


def test_start_project_processing_workflow_validation_fails(orchestrator_setup):
    """Workflow should stop if validation fails."""
    orchestrator, main_view_model = orchestrator_setup

    # Setup validation failure
    validation_result = MagicMock()
    validation_result.is_valid = False
    main_view_model.processing_coordinator.validate_can_start_processing.return_value = (
        validation_result
    )
    main_view_model.dialog_coordinator.handle_validation_error.return_value = False

    orchestrator.start_project_processing_workflow()

    # Should have called validation
    main_view_model.processing_coordinator.validate_can_start_processing.assert_called_once()
    # Should not have asked for files (early return)
    assert main_view_model.view.file_dialog_response is None


def test_start_project_processing_workflow_zone_validation_fails(orchestrator_setup):
    """Workflow should stop if zone validation fails."""
    orchestrator, main_view_model = orchestrator_setup

    # Setup validation success but zone validation failure
    validation_result = MagicMock()
    validation_result.is_valid = True
    main_view_model.processing_coordinator.validate_can_start_processing.return_value = (
        validation_result
    )
    main_view_model.dialog_coordinator.handle_validation_error.return_value = True
    main_view_model.dialog_coordinator.validate_zones_with_ui.return_value = False

    orchestrator.start_project_processing_workflow()

    # Should have called zone validation
    main_view_model.dialog_coordinator.validate_zones_with_ui.assert_called_once()


def test_start_project_processing_workflow_user_cancels_file_dialog(orchestrator_setup):
    """Workflow should stop if user cancels file dialog."""
    orchestrator, main_view_model = orchestrator_setup

    # Setup successful validation
    validation_result = MagicMock()
    validation_result.is_valid = True
    main_view_model.processing_coordinator.validate_can_start_processing.return_value = (
        validation_result
    )
    main_view_model.dialog_coordinator.handle_validation_error.return_value = True
    main_view_model.dialog_coordinator.validate_zones_with_ui.return_value = True

    # User cancels file dialog
    main_view_model.view.file_dialog_response = None

    orchestrator.start_project_processing_workflow()

    # Should not have scanned videos
    main_view_model.project_manager.scan_input_paths.assert_not_called()


def test_start_project_processing_workflow_no_videos_found(orchestrator_setup):
    """Workflow should warn if no videos found."""
    orchestrator, main_view_model = orchestrator_setup

    # Setup successful validation
    validation_result = MagicMock()
    validation_result.is_valid = True
    main_view_model.processing_coordinator.validate_can_start_processing.return_value = (
        validation_result
    )
    main_view_model.dialog_coordinator.handle_validation_error.return_value = True
    main_view_model.dialog_coordinator.validate_zones_with_ui.return_value = True

    # User selects files but no videos found
    main_view_model.view.file_dialog_response = ["/some/path"]
    main_view_model.project_manager.scan_input_paths.return_value = []

    orchestrator.start_project_processing_workflow()

    # Should show warning
    warning_events = [
        evt for evt in main_view_model.ui_event_bus.events if evt[0] == Events.UI_SHOW_WARNING
    ]
    assert len(warning_events) == 1
    assert "Nenhum Vídeo Encontrado" in warning_events[0][1]["title"]


def test_start_project_processing_workflow_processes_videos(orchestrator_setup, monkeypatch):
    """Workflow should process videos when all conditions are met."""
    orchestrator, main_view_model = orchestrator_setup

    # Mock ProcessingWorker to avoid actual processing
    mock_worker_instance = MagicMock()
    mock_worker_instance.start_in_thread.return_value = MagicMock()

    def mock_worker_init(*args, **kwargs):
        return mock_worker_instance

    monkeypatch.setattr(
        "zebtrack.orchestrators.video_processing_orchestrator.ProcessingWorker",
        mock_worker_init,
    )

    # Setup successful validation
    validation_result = MagicMock()
    validation_result.is_valid = True
    main_view_model.processing_coordinator.validate_can_start_processing.return_value = (
        validation_result
    )
    main_view_model.dialog_coordinator.handle_validation_error.return_value = True
    main_view_model.dialog_coordinator.validate_zones_with_ui.return_value = True

    # Videos found and processed
    main_view_model.view.file_dialog_response = ["/some/video.mp4"]
    scanned = [{"path": "/some/video.mp4"}]
    main_view_model.project_manager.scan_input_paths.return_value = scanned
    main_view_model.dialog_coordinator.handle_mixed_data_scenario.return_value = scanned
    main_view_model.project_manager.project_path = "/project"

    # Mock ProcessingWorker creation
    mock_callbacks = MagicMock()
    mock_context = MagicMock()
    main_view_model.processing_coordinator.create_processing_callbacks.return_value = mock_callbacks
    main_view_model.processing_coordinator.create_processing_context.return_value = mock_context

    orchestrator.start_project_processing_workflow()

    # Should have created callbacks and context via ProcessingCoordinator
    main_view_model.processing_coordinator.create_processing_callbacks.assert_called_once_with(
        scanned
    )
    main_view_model.processing_coordinator.create_processing_context.assert_called_once()

    # Should show success message
    info_events = [
        evt for evt in main_view_model.ui_event_bus.events if evt[0] == Events.UI_SHOW_INFO
    ]
    assert len(info_events) == 1
    assert "Sucesso" in info_events[0][1]["title"]
