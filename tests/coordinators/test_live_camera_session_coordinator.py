"""Tests for LiveCameraSessionCoordinator.

Focuses on the live camera session lifecycle and configuration.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
)
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.recording.live_camera_service import LiveCameraService
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.state_manager import StateManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@pytest.fixture
def mock_state_manager():
    return Mock(spec=StateManager)


@pytest.fixture
def mock_live_camera_service():
    service = Mock(spec=LiveCameraService)
    return service


@pytest.fixture
def mock_project_manager():
    manager = Mock(spec=ProjectManager)
    manager.project_path = "/mock/project"
    manager.get_active_zone_video.return_value = None
    manager.find_video_entry.return_value = None
    return manager


@pytest.fixture
def mock_detector_service():
    return Mock(spec=DetectorService)


@pytest.fixture
def mock_settings():
    return Mock(spec=Settings)


@pytest.fixture
def mock_live_calibration_coordinator():
    return Mock()


@pytest.fixture
def mock_event_bus():
    return Mock(spec=EventBusV2)


@pytest.fixture
def coordinator(
    mock_state_manager,
    mock_live_camera_service,
    mock_project_manager,
    mock_detector_service,
    mock_settings,
    mock_live_calibration_coordinator,
    mock_event_bus,
):
    return LiveCameraSessionCoordinator(
        state_manager=mock_state_manager,
        live_camera_service=mock_live_camera_service,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        settings_obj=mock_settings,
        live_calibration_coordinator=mock_live_calibration_coordinator,
        event_bus=mock_event_bus,
    )


class TestLiveCameraSessionCoordinatorInitialization:
    def test_initialization(self, coordinator, mock_event_bus, mock_live_camera_service):
        """Should initialize and subscribe to events."""
        assert coordinator.event_bus is mock_event_bus
        assert coordinator.live_camera_service is mock_live_camera_service

        # Check event subscriptions
        subscribe_calls = mock_event_bus.subscribe.call_args_list
        event_types = [call[0][0] for call in subscribe_calls]
        assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED in event_types
        assert UIEvents.LIVE_RECORDING_CANCELLED in event_types


class TestLiveCameraSessionCoordinatorHelpers:
    def test_format_day_label_for_metadata(self):
        """Test day label formatting logic."""
        format_fn = LiveCameraSessionCoordinator._format_day_label_for_metadata

        assert format_fn(None) is None
        assert format_fn("") is None
        assert format_fn("   ") is None

        # It should prepend the localized prefix. We mock it or assume "Day" from `day_prefix`
        # Because we don't mock `day_prefix` here, we'll just check it contains the input text.
        res = format_fn("12")
        assert res is not None
        assert "12" in res

        res = format_fn("Dia_12")
        assert res is not None
        assert "12" in res
        assert "Dia_12" not in res  # Prefix should be stripped

    def test_resolve_session_paths_with_override(self, coordinator):
        """Should return override directly."""
        path, name = coordinator._resolve_session_paths(override=Path("/custom/path"))
        assert path == Path("/custom/path")
        assert name is None

    def test_resolve_session_paths_hierarchical(self, coordinator, mock_project_manager):
        """Should use hierarchical layout if all metadata is present."""
        mock_project_manager.resolve_results_directory.return_value = "/mock/project/G/D/S"

        path, name = coordinator._resolve_session_paths(
            experiment_id="exp1", group="G", day="D", subject="S"
        )

        assert path == Path("/mock/project/G/D/S")
        assert name and name.startswith("live_")

    def test_resolve_session_paths_fallback(self, coordinator, mock_project_manager):
        """Should fallback to live_analysis_sessions if metadata is incomplete."""
        path, name = coordinator._resolve_session_paths(
            experiment_id="exp1",
            group="G",  # missing day/subject
        )

        assert path == Path("/mock/project/live_analysis_sessions")
        assert name is None

    def test_resolve_session_paths_no_project(self, coordinator, mock_project_manager):
        """Should return None if no project path."""
        mock_project_manager.project_path = None
        path, name = coordinator._resolve_session_paths(experiment_id="exp1")
        assert path is None
        assert name is None


class TestLiveCameraSessionCoordinatorResumeCancelled:
    def test_on_resume_cancelled(self, coordinator, mock_live_calibration_coordinator):
        """Should clear pending contexts when cancelled."""
        coordinator._pending_live_context = {"experiment_id": "test"}
        coordinator._pending_live_kind = "project"

        coordinator._on_resume_cancelled()

        assert coordinator._pending_live_context is None
        assert coordinator._pending_live_kind is None
        assert mock_live_calibration_coordinator.pending_zone_confirmation is False
        mock_live_calibration_coordinator.clear_last_polygon_source.assert_called_once()


class TestLiveCameraSessionCoordinatorUIState:
    def test_apply_live_analysis_metadata_to_ui(self, coordinator):
        """Should apply metadata via view controller and widget."""
        mock_controller = Mock()
        mock_widget = Mock()

        # Setup view
        coordinator.view = Mock()
        coordinator.view.analysis_view_controller = mock_controller
        coordinator.view.analysis_display_widget = mock_widget

        metadata = {
            "group": "A",
            "day_label": "Day 1",
            "subject": "Fish 1",
            "profile": "custom",
        }

        # Call directly (no root, so it executes synchronously)
        coordinator._apply_live_analysis_metadata_to_ui(metadata)

        mock_controller.update_analysis_metadata.assert_called_once_with(metadata=metadata)
        mock_widget.set_metadata.assert_called_once_with(
            group="A", day="Day 1", subject="Fish 1", profile="custom"
        )

    def test_finalize_live_session_ui_success(
        self, coordinator, mock_state_manager, mock_event_bus
    ):
        """Test finalization logic on success."""
        coordinator._active_live_session_id = "test_sess"
        coordinator._last_live_experiment_id = "exp_1"

        res = coordinator._finalize_live_session_ui(
            cancelled=False, publish_refresh=True, service_success=True
        )

        assert res is True
        assert coordinator._active_live_session_id is None

        # Event published
        event_types = [call[0][0].type for call in mock_event_bus.publish.call_args_list]
        assert UIEvents.LIVE_SESSION_STOPPED in event_types
        assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_types
        assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in event_types


class TestLiveCameraSessionCoordinatorLifecycle:
    def test_publish_live_analysis_metadata(
        self, coordinator, mock_project_manager, mock_event_bus
    ):
        """Should merge active video metadata with args and publish."""
        mock_project_manager.get_active_zone_video.return_value = "video.mp4"
        mock_project_manager.find_video_entry.return_value = {
            "metadata": {"profile": "from_entry"},
            "group": "G_entry",
            "day": "D_entry",
        }
        mock_project_manager.resolve_analysis_profile.return_value = {"name": "resolved_profile"}

        coordinator._publish_live_analysis_metadata(
            experiment_id="exp_123",
            camera_index=0,
            group="G_arg",
            subject="S_arg",
        )

        assert coordinator._last_live_experiment_id == "exp_123"
        assert coordinator._last_live_analysis_metadata["experiment_id"] == "exp_123"
        assert coordinator._last_live_analysis_metadata["camera_index"] == 0
        assert coordinator._last_live_analysis_metadata["group"] == "G_entry"  # from entry
        assert coordinator._last_live_analysis_metadata["day"] == "D_entry"  # from entry
        assert coordinator._last_live_analysis_metadata["subject"] == "S_arg"  # from arg
        assert coordinator._last_live_analysis_metadata["profile"] == "from_entry"

        mock_event_bus.publish.assert_called()

    def test_start_live_session_success(
        self, coordinator, mock_live_camera_service, mock_event_bus, mock_state_manager
    ):
        """Should start session via service and publish events."""
        mock_live_camera_service.start_session.return_value = True

        res = coordinator.start_live_session(
            camera_index=1,
            duration_s=10.0,
            experiment_id="test_exp",
            wizard_data={"experimental_group": "G1", "animals_per_aquarium": 2},
        )

        assert res is True
        assert coordinator.is_live_session_active()
        assert coordinator._active_live_session_id == "test_exp"
        # State updated
        # State updated
        calls = mock_state_manager.update_processing_state.call_args_list
        assert len(calls) > 0, "update_processing_state was not called"
        start_kwargs = next(
            (c.kwargs for c in calls if c.kwargs.get("experiment_id") == "test_exp"), None
        )
        assert start_kwargs is not None, (
            "update_processing_state with experiment_id='test_exp' not found"
        )
        assert start_kwargs.get("is_live_session_active") is True
        assert start_kwargs.get("source") == "LiveCameraSessionCoordinator.start_live_session"

        # Service called
        mock_live_camera_service.start_session.assert_called_once()
        kwargs = mock_live_camera_service.start_session.call_args[1]
        assert kwargs["camera_index"] == 1
        assert kwargs["animals_per_aquarium"] == 2

    def test_start_live_session_active(self, coordinator):
        """Should raise error if already active."""
        coordinator._active_live_session_id = "already"

        with pytest.raises(LiveCameraSessionCoordinatorError, match="already active"):
            coordinator.start_live_session()

    def test_stop_live_session(self, coordinator, mock_live_camera_service):
        """Should stop session via service."""
        coordinator._active_live_session_id = "test_exp"
        mock_live_camera_service.stop_session.return_value = True

        res = coordinator.stop_live_session()

        assert res is True
        assert not coordinator.is_live_session_active()
        mock_live_camera_service.stop_session.assert_called_once_with(cancelled=True)
