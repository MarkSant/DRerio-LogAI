"""Unit tests for ProcessingCoordinator.start_project_processing_workflow.

Phase 0.3: Tests migrated from VideoProcessingOrchestrator to ProcessingCoordinator.
The workflow logic now lives directly in ProcessingCoordinator.
"""

from __future__ import annotations

from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
from zebtrack.ui.events import Events


class DummyEventBus:
    """Lightweight event bus that records published events."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}

    def publish_event(self, event: str, payload: dict | None = None):
        self.events.append((event, payload or {}))

    def subscribe(self, event: str, handler):
        self.handlers.setdefault(event, []).append(handler)


class DummyView:
    """Lightweight view mock for file dialog interactions."""

    def __init__(self):
        self.file_dialog_response: list[str] | None = None

    def ask_open_filenames(self, title, filetypes):
        return self.file_dialog_response


@pytest.fixture()
def coordinator_setup():
    """Create a ProcessingCoordinator with mocked dependencies for workflow tests."""
    event_bus = DummyEventBus()
    view = DummyView()
    dialog_coordinator = MagicMock()
    project_manager = MagicMock()
    ui_state_controller = MagicMock()
    cancel_event = Event()

    coordinator = ProcessingCoordinator(
        state_manager=MagicMock(),
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        ui_state_controller=ui_state_controller,
        cancel_event=cancel_event,
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        event_bus=event_bus,
        dialog_coordinator=dialog_coordinator,
        view=view,
    )

    return coordinator, view, dialog_coordinator, project_manager, event_bus


def test_workflow_returns_early_without_view():
    """Workflow exits if view is not set."""
    coordinator = ProcessingCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=Event(),
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        dialog_coordinator=MagicMock(),
        view=None,
    )
    # Should not raise
    coordinator.start_project_processing_workflow()


def test_workflow_validation_fails(coordinator_setup):
    """Workflow should stop if validation fails."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = False
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = False

    coordinator.start_project_processing_workflow()

    coordinator.validate_can_start_processing.assert_called_once()
    # Should not have asked for files (early return)
    assert view.file_dialog_response is None


def test_workflow_zone_validation_fails(coordinator_setup):
    """Workflow should stop if zone validation fails."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = False

    coordinator.start_project_processing_workflow()

    dialog_coordinator.validate_zones_with_ui.assert_called_once()


def test_workflow_user_cancels_file_dialog(coordinator_setup):
    """Workflow should stop if user cancels file dialog."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = True

    # User cancels
    view.file_dialog_response = None

    coordinator.start_project_processing_workflow()

    pm.scan_input_paths.assert_not_called()


def test_workflow_no_videos_found(coordinator_setup):
    """Workflow should warn if no videos found."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = True

    view.file_dialog_response = ["/some/path"]
    pm.scan_input_paths.return_value = []

    coordinator.start_project_processing_workflow()

    warning_events = [
        evt for evt in event_bus.events if evt[0] == Events.UI_SHOW_WARNING
    ]
    assert len(warning_events) == 1
    assert "Nenhum Vídeo Encontrado" in warning_events[0][1]["title"]


def test_workflow_processes_videos(coordinator_setup):
    """Workflow should process videos when all conditions are met."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = True

    view.file_dialog_response = ["/some/video.mp4"]
    scanned = [{"path": "/some/video.mp4"}]
    pm.scan_input_paths.return_value = scanned
    dialog_coordinator.handle_mixed_data_scenario.return_value = scanned
    pm.project_path = "/project"

    # Mock ProcessingWorker to avoid actual processing
    mock_worker_instance = MagicMock()
    mock_worker_instance.start_in_thread.return_value = MagicMock()

    with patch(
        "zebtrack.coordinators.processing_coordinator.ProcessingWorker",
        return_value=mock_worker_instance,
    ):
        coordinator.start_project_processing_workflow()

    # Should show success message
    info_events = [
        evt for evt in event_bus.events if evt[0] == Events.UI_SHOW_INFO
    ]
    assert len(info_events) == 1
    assert "Sucesso" in info_events[0][1]["title"]
