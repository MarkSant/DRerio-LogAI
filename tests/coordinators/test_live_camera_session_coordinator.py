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


class TestValidateDependencies:
    def test_missing_live_camera_service(self, coordinator):
        from zebtrack.coordinators.base_coordinator import CoordinatorValidationError

        coordinator.live_camera_service = None
        with pytest.raises(CoordinatorValidationError, match="LiveCameraService is required"):
            coordinator.validate_dependencies()

    def test_missing_project_manager(self, coordinator):
        from zebtrack.coordinators.base_coordinator import CoordinatorValidationError

        coordinator.project_manager = None
        with pytest.raises(CoordinatorValidationError, match="ProjectManager is required"):
            coordinator.validate_dependencies()

    def test_all_present(self, coordinator):
        assert coordinator.validate_dependencies() is True


class TestResolveLiveProcessingMode:
    def test_flag_single_animal(self, coordinator, mock_project_manager):
        from zebtrack.core.video.processing_mode import ProcessingMode

        mock_project_manager.project_data = {"single_animal_per_aquarium": True}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.SINGLE_SUBJECT

        mock_project_manager.project_data = {"single_animal_per_aquarium": False}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.MULTI_TRACK

    def test_top_animals_per_aquarium(self, coordinator, mock_project_manager):
        from zebtrack.core.video.processing_mode import ProcessingMode

        mock_project_manager.project_data = {"animals_per_aquarium": 1}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.SINGLE_SUBJECT

        mock_project_manager.project_data = {"animals_per_aquarium": 3}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.MULTI_TRACK

    def test_tracking_use_single_subject_tracker(self, coordinator, mock_project_manager):
        from zebtrack.core.video.processing_mode import ProcessingMode

        mock_project_manager.project_data = {"tracking": {"use_single_subject_tracker": True}}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.SINGLE_SUBJECT

    def test_calibration_animals_per_aquarium(self, coordinator, mock_project_manager):
        from zebtrack.core.video.processing_mode import ProcessingMode

        mock_project_manager.project_data = {"calibration": {"animals_per_aquarium": 1}}
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.SINGLE_SUBJECT

    def test_animals_per_aquarium_list(self, coordinator, mock_project_manager):
        from zebtrack.core.video.processing_mode import ProcessingMode

        mock_project_manager.project_data = {
            "calibration": {"animals_per_aquarium_list": [1, 1, 1]}
        }
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.SINGLE_SUBJECT

        mock_project_manager.project_data = {
            "calibration": {"animals_per_aquarium_list": [1, 2, 1]}
        }
        assert coordinator._resolve_live_processing_mode() == ProcessingMode.MULTI_TRACK

    def test_no_keys_match(self, coordinator, mock_project_manager):
        mock_project_manager.project_data = {}
        assert coordinator._resolve_live_processing_mode() is None


class TestPublishLiveTaskStatus:
    def test_publish_with_event_bus(self, coordinator, mock_event_bus):
        coordinator._publish_live_task_status(
            experiment_id="exp1", step="Recording", progress_fraction=0.5
        )
        mock_event_bus.publish.assert_called_once()
        call_event = mock_event_bus.publish.call_args[0][0]
        assert call_event.type == UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS
        assert call_event.data.step == "Recording"
        assert call_event.data.progress_fraction == 0.5

    def test_publish_none_event_bus(self, coordinator):
        coordinator.event_bus = None
        coordinator._publish_live_task_status(step="Recording")  # Should not raise


class TestSetLiveAnalysisUIState:
    def test_set_live_analysis_ui_state_all_flags(self, coordinator):
        mock_controller = Mock()
        mock_widget = Mock()
        coordinator.view = Mock(
            analysis_view_controller=mock_controller,
            analysis_display_widget=mock_widget,
        )
        coordinator._last_live_analysis_metadata = {"group": "G1"}

        coordinator._set_live_analysis_ui_state(
            status_text="Running",
            experiment_id="exp1",
            task_step="Step 1",
            switch_to_analysis=True,
            show_progress=True,
            disable_cancel=True,
            restore_metadata=True,
        )

        mock_controller.switch_to_analysis_view.assert_called_once()
        mock_controller.set_analysis_status.assert_called_once_with("Running")
        mock_controller.update_analysis_task_status.assert_called_once_with(
            index=None, total=None, experiment_id="exp1", step="Step 1"
        )
        mock_controller.update_analysis_metadata.assert_called_once_with(metadata={"group": "G1"})
        mock_widget.show_progress.assert_called_once()
        mock_widget.disable_cancel_button.assert_called_once()

    def test_set_live_analysis_ui_state_no_view(self, coordinator):
        coordinator.view = None
        coordinator._set_live_analysis_ui_state(status_text="Running")  # Should not raise


class TestOnLiveServiceSessionStopped:
    def test_suppressed(self, coordinator):
        coordinator._suppress_service_stop_callback = True
        coordinator._finalize_live_session_ui = Mock()
        coordinator._on_live_service_session_stopped(cancelled=False)
        coordinator._finalize_live_session_ui.assert_not_called()

    def test_not_active(self, coordinator):
        coordinator._suppress_service_stop_callback = False
        coordinator._active_live_session_id = None
        coordinator._finalize_live_session_ui = Mock()
        coordinator._on_live_service_session_stopped(cancelled=False)
        coordinator._finalize_live_session_ui.assert_not_called()

    def test_active_finalizes(self, coordinator):
        coordinator._suppress_service_stop_callback = False
        coordinator._active_live_session_id = "sess1"
        coordinator._finalize_live_session_ui = Mock()
        coordinator._on_live_service_session_stopped(cancelled=False)
        coordinator._finalize_live_session_ui.assert_called_once_with(
            cancelled=False, publish_refresh=True, service_success=True
        )


class TestPendingAndResumeFlows:
    def test_publish_pending_with_calibration_source(
        self, coordinator, mock_live_calibration_coordinator, mock_event_bus
    ):
        mock_live_calibration_coordinator.last_polygon_source = "auto"
        ctx = {"experiment_id": "exp_1", "group": "G1", "day": "D1", "subject": "S1"}

        coordinator._publish_pending(ctx)

        mock_event_bus.publish.assert_called_once()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.LIVE_RECORDING_PENDING
        assert event_obj.data.polygon_source == "auto"

    def test_publish_pending_no_event_bus(self, coordinator):
        coordinator.event_bus = None
        coordinator._publish_pending({})  # Should not raise

    def test_on_resume_requested_no_pending_context(self, coordinator):
        coordinator._pending_live_context = None
        coordinator._pending_live_kind = None
        coordinator._on_resume_requested()  # Should return safely

    def test_on_resume_requested_project_kind(self, coordinator):
        coordinator._pending_live_context = {
            "day_int": 1,
            "group": "G1",
            "subject": "S1",
            "duration_s": 60.0,
            "camera_index_override": 0,
            "camera_friendly_name_override": "Cam1",
        }
        coordinator._pending_live_kind = "project"
        coordinator.start_live_project_session = Mock()

        coordinator._on_resume_requested()

        coordinator.start_live_project_session.assert_called_once_with(
            day=1,
            group="G1",
            subject="S1",
            duration_s=60.0,
            camera_index_override=0,
            camera_friendly_name_override="Cam1",
            zones_validated=True,
        )

    def test_on_resume_requested_config_kind(self, coordinator):
        coordinator._pending_live_context = {"config": {"key": "val"}}
        coordinator._pending_live_kind = "config"
        coordinator.start_session_from_config = Mock()

        coordinator._on_resume_requested()

        coordinator.start_session_from_config.assert_called_once_with(
            config={"key": "val"},
            zones_validated=True,
        )

    def test_on_resume_requested_exception_shows_error(self, coordinator, mock_event_bus):
        coordinator._pending_live_context = {"day_int": 1, "group": "G", "subject": "S"}
        coordinator._pending_live_kind = "project"
        coordinator.start_live_project_session = Mock(side_effect=RuntimeError("Hardware issue"))

        coordinator._on_resume_requested()

        mock_event_bus.publish.assert_called_once()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.UI_SHOW_ERROR


class TestSessionInfo:
    def test_get_live_session_info_not_active(self, coordinator):
        coordinator._active_live_session_id = None
        assert coordinator.get_live_session_info() is None

    def test_get_live_session_info_active(self, coordinator, mock_state_manager):
        coordinator._active_live_session_id = "sess_123"
        mock_proc = Mock(camera_index=0, experiment_id="exp_1", duration_s=100.0)
        mock_state_manager.get_processing_state.return_value = mock_proc

        info = coordinator.get_live_session_info()
        assert info is not None
        assert info["session_id"] == "sess_123"
        assert info["is_active"] is True
        assert info["camera_index"] == 0


class TestBatchSessionRegistration:
    def test_register_batch_session_no_wizard_data(self, coordinator):
        coordinator._active_wizard_data = None
        coordinator._register_batch_session()  # Should not raise

    def test_register_batch_session_incomplete_fields(self, coordinator):
        coordinator._active_wizard_data = {"experimental_group": "G1"}  # missing day and subject
        coordinator._register_batch_session()
        assert coordinator._active_wizard_data is None

    def test_register_batch_session_with_batch_coordinator(self, coordinator):
        coordinator._active_wizard_data = {
            "experimental_group": "G1",
            "experiment_day": "D1",
            "subject_id": "S1",
            "recording_duration_s": 60.0,
            "camera_index": 0,
            "is_batch_last_session": True,
        }
        coordinator._active_live_session_id = "exp_batch"
        coordinator._find_video_in_live_session = Mock(return_value=Path("/tmp/live.mp4"))

        mock_batch_coord = Mock()
        mock_batch_coord.register_session.return_value = "batch_001"
        coordinator.live_batch_coordinator = mock_batch_coord

        coordinator._register_batch_session()

        mock_batch_coord.register_session.assert_called_once()
        mock_batch_coord.mark_batch_complete.assert_called_once_with("batch_001")
        assert coordinator._active_wizard_data is None


class TestArduinoExternalTriggerFlows:
    def test_on_arduino_event_start_with_pending_context(self, coordinator, mock_event_bus):
        coordinator._pending_trigger_context = {
            "experiment_id": "exp_arduino_1",
            "day_int": 1,
            "group": "Control",
            "subject": "Fish1",
            "duration_s": 120.0,
            "camera_index_override": 0,
            "camera_friendly_name_override": "Cam 0",
        }
        coordinator.start_live_project_session = Mock()

        coordinator.on_arduino_event(1)

        assert coordinator._pending_trigger_context is None
        coordinator.start_live_project_session.assert_called_once_with(
            day=1,
            group="Control",
            subject="Fish1",
            duration_s=120.0,
            camera_index_override=0,
            camera_friendly_name_override="Cam 0",
            zones_validated=True,
            external_trigger_armed=True,
        )

    def test_on_arduino_event_start_without_context(self, coordinator):
        coordinator._pending_trigger_context = None
        coordinator.start_live_project_session = Mock()

        coordinator.on_arduino_event(1)

        coordinator.start_live_project_session.assert_not_called()

    def test_on_arduino_event_stop_with_pending_context(self, coordinator):
        coordinator._pending_trigger_context = {"dummy": True}
        coordinator.clear_pending_external_trigger = Mock()

        coordinator.on_arduino_event(0)

        coordinator.clear_pending_external_trigger.assert_called_once()

    def test_on_arduino_event_stop_active_session(self, coordinator):
        coordinator._pending_trigger_context = None
        coordinator.is_live_session_active = Mock(return_value=True)
        coordinator.stop_live_session = Mock()

        coordinator.on_arduino_event(0)

        coordinator.stop_live_session.assert_called_once()

    def test_on_arduino_event_other_code_ignored(self, coordinator):
        coordinator.start_live_project_session = Mock()
        coordinator.stop_live_session = Mock()

        coordinator.on_arduino_event(42)

        coordinator.start_live_project_session.assert_not_called()
        coordinator.stop_live_session.assert_not_called()

    def test_clear_pending_external_trigger(self, coordinator, mock_event_bus):
        coordinator._pending_trigger_context = {"dummy": True}
        coordinator.clear_pending_external_trigger()

        assert coordinator._pending_trigger_context is None
        mock_event_bus.publish.assert_called()


class TestFindVideoInLiveSession:
    def test_find_video_when_present(self, coordinator, tmp_path):
        session_dir = tmp_path / "live_session"
        session_dir.mkdir()
        video_file = session_dir / "recorded.mp4"
        video_file.write_text("dummy")

        coordinator.live_camera_service.current_output_dir = str(session_dir)
        found = coordinator._find_video_in_live_session()

        assert found is not None
        assert found.name == "recorded.mp4"

    def test_find_video_when_dir_missing(self, coordinator):
        coordinator.live_camera_service.current_output_dir = None
        assert coordinator._find_video_in_live_session() is None
