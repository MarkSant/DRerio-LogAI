"""Unit tests for ProcessingCoordinator.start_project_processing_workflow.

Phase 0.3: Tests migrated from VideoProcessingOrchestrator to ProcessingCoordinator.
The workflow logic now lives directly in ProcessingCoordinator.
"""

from __future__ import annotations

from threading import Event as ThreadingEvent
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import Event as BusEvent
from zebtrack.ui.event_bus_v2 import UIEvents


class DummyEventBus:
    """Lightweight event bus that records published events."""

    def __init__(self):
        self.events: list[tuple[UIEvents, payloads.EventPayload | dict[str, object]]] = []
        self.handlers: dict[UIEvents, list] = {}

    def publish(
        self,
        event_type: UIEvents | BusEvent,
        payload: payloads.EventPayload | dict[str, object] | None = None,
    ) -> None:
        if isinstance(event_type, BusEvent):
            self.events.append((event_type.type, event_type.data))
            return
        self.events.append((event_type, payload or {}))

    def subscribe(self, event_type: UIEvents, handler):
        self.handlers.setdefault(event_type, []).append(handler)


class DummyView:
    """Lightweight view mock for file dialog interactions."""

    def __init__(self):
        self.file_dialog_response: list[str] | None = None
        self.root = None
        self.dialog_manager = MagicMock()
        self.dialog_manager.ask_open_filenames.side_effect = self._ask_open_filenames

    def _ask_open_filenames(self, title, filetypes):
        return tuple(self.file_dialog_response or ())


@pytest.fixture()
def coordinator_setup():
    """Create a ProcessingCoordinator with mocked dependencies for workflow tests."""
    event_bus = DummyEventBus()
    view = DummyView()
    dialog_coordinator = MagicMock()
    project_manager = MagicMock()
    ui_state_controller = MagicMock()
    cancel_event = ThreadingEvent()

    coordinator = VideoProcessingCoordinator(
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
        event_bus=event_bus,  # type: ignore[arg-type]  # DummyEventBus duck-types EventBusV2
        dialog_coordinator=dialog_coordinator,
        view=view,
    )

    return coordinator, view, dialog_coordinator, project_manager, event_bus


def test_workflow_returns_early_without_view():
    """Workflow exits if view is not set."""
    coordinator = VideoProcessingCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=ThreadingEvent(),
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
    coordinator, view, dialog_coordinator, _pm, _event_bus = coordinator_setup

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
    coordinator, _view, dialog_coordinator, _pm, _event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = False

    coordinator.start_project_processing_workflow()

    dialog_coordinator.validate_zones_with_ui.assert_called_once()


def test_workflow_validates_the_active_zone_video(coordinator_setup):
    """The project workflow must validate the video selected in the zone editor."""
    coordinator, _view, dialog_coordinator, project_manager, _event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = False
    project_manager.get_active_zone_video.return_value = "C:/videos/selected.mp4"

    coordinator.start_project_processing_workflow()

    dialog_coordinator.validate_zones_with_ui.assert_called_once_with(
        video_path="C:/videos/selected.mp4"
    )


def test_workflow_user_cancels_file_dialog(coordinator_setup):
    """Workflow should stop if user cancels file dialog."""
    coordinator, view, dialog_coordinator, pm, _event_bus = coordinator_setup

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

    warning_events = [evt for evt in event_bus.events if evt[0] == UIEvents.UI_SHOW_WARNING]
    assert len(warning_events) == 1
    assert "Nenhum Vídeo Encontrado" in warning_events[0][1].title


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
        "zebtrack.coordinators.video_processing_coordinator.ProcessingWorker",
        return_value=mock_worker_instance,
    ):
        coordinator.start_project_processing_workflow()

    # Should show success message
    info_events = [evt for evt in event_bus.events if evt[0] == UIEvents.UI_SHOW_INFO]
    assert len(info_events) == 1
    assert "Sucesso" in info_events[0][1].title


def test_workflow_adds_existing_data_without_reprocessing(coordinator_setup):
    """Legacy add/process workflow should still allow add-only when reprocessing is declined."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True
    dialog_coordinator.validate_zones_with_ui.return_value = True

    scanned = [{"path": "/some/video.mp4", "has_data": True, "has_trajectory": True}]
    view.file_dialog_response = ["/some/video.mp4"]
    pm.scan_input_paths.return_value = scanned
    dialog_coordinator.handle_mixed_data_scenario.return_value = None

    coordinator.start_project_processing_workflow()

    pm.add_video_batch.assert_called_once_with(scanned)
    info_events = [evt for evt in event_bus.events if evt[0] == UIEvents.UI_SHOW_INFO]
    assert len(info_events) == 1
    assert "Vídeos Adicionados" in info_events[0][1].title


def test_import_workflow_adds_videos_without_processing(coordinator_setup):
    """Import workflow should persist reviewed videos without starting processing."""
    coordinator, view, dialog_coordinator, pm, event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True

    scanned = [{"path": "/some/video.mp4", "has_arena": False, "has_rois": False}]
    reviewed = [
        {
            "path": "/some/video.mp4",
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
            "metadata": {"group": "Controle", "day": 2, "subject": "S01"},
            "group": "Controle",
            "day": 2,
            "subject": "S01",
        }
    ]

    view.file_dialog_response = ["/some/video.mp4"]
    pm.scan_input_paths.return_value = scanned
    pm.get_all_videos.return_value = []
    pm.get_available_groups.return_value = ["Controle"]
    pm.get_last_session_details.return_value = (1, "Controle")
    pm.project_data = {"calibration": {"num_aquariums": 1, "animals_per_aquarium": 1}}

    coordinator.process_pending_project_videos = MagicMock()

    with patch(
        "zebtrack.ui.dialogs.project_video_import_dialog.ProjectVideoImportDialog"
    ) as mock_dialog:
        mock_dialog.return_value.result = {
            "confirmed": True,
            "videos": reviewed,
            "process_mode": "add_only",
            "last_group": "Controle",
            "last_day": 2,
        }

        coordinator.start_project_import_workflow()

    pm.add_video_batch.assert_called_once_with(reviewed)
    coordinator.process_pending_project_videos.assert_not_called()
    refresh_events = [
        evt for evt in event_bus.events if evt[0] == UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED
    ]
    assert len(refresh_events) == 1


def test_import_workflow_processes_only_pending_after_import(coordinator_setup):
    """Import workflow should process only imported videos without trajectory in pending mode."""
    coordinator, view, dialog_coordinator, pm, _event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True

    scanned = [
        {"path": "/some/video1.mp4", "has_trajectory": False},
        {"path": "/some/video2.mp4", "has_trajectory": True},
    ]
    reviewed = [
        {
            "path": "/some/video1.mp4",
            "has_trajectory": False,
            "metadata": {"group": "Controle", "day": 1, "subject": "S01"},
            "group": "Controle",
            "day": 1,
            "subject": "S01",
        },
        {
            "path": "/some/video2.mp4",
            "has_trajectory": True,
            "metadata": {"group": "Controle", "day": 1, "subject": "S02"},
            "group": "Controle",
            "day": 1,
            "subject": "S02",
        },
    ]

    view.file_dialog_response = ["/some/video1.mp4", "/some/video2.mp4"]
    pm.scan_input_paths.return_value = scanned
    pm.get_all_videos.return_value = []
    pm.get_available_groups.return_value = ["Controle"]
    pm.get_last_session_details.return_value = (1, "Controle")
    pm.project_data = {"calibration": {"num_aquariums": 1, "animals_per_aquarium": 1}}

    coordinator.process_pending_project_videos = MagicMock()

    with patch(
        "zebtrack.ui.dialogs.project_video_import_dialog.ProjectVideoImportDialog"
    ) as mock_dialog:
        mock_dialog.return_value.result = {
            "confirmed": True,
            "videos": reviewed,
            "process_mode": "process_pending",
            "last_group": "Controle",
            "last_day": 1,
        }

        coordinator.start_project_import_workflow()

    coordinator.process_pending_project_videos.assert_called_once_with(["/some/video1.mp4"])


def test_import_workflow_uses_dialog_manager_when_view_has_no_file_picker(coordinator_setup):
    """ApplicationGUI-backed imports should read file selections via dialog manager."""
    coordinator, view, dialog_coordinator, pm, _event_bus = coordinator_setup

    validation_result = MagicMock()
    validation_result.is_valid = True
    coordinator.validate_can_start_processing = MagicMock(return_value=validation_result)
    dialog_coordinator.handle_validation_error.return_value = True

    view.file_dialog_response = ["/some/video.mp4"]
    pm.scan_input_paths.return_value = []

    coordinator.start_project_import_workflow()

    view.dialog_manager.ask_open_filenames.assert_called_once()
    pm.scan_input_paths.assert_called_once_with(["/some/video.mp4"])
