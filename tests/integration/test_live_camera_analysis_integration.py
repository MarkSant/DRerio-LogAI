"""
Integration tests for live camera analysis feature.

Tests the complete flow: Dialog → RecordingService → Camera → Recorder → Auto-stop
"""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import numpy as np
import pytest


@pytest.fixture
def mock_camera():
    """Create a mock camera that returns fake frames."""
    camera = Mock()
    camera.camera_index = 0
    camera._camera_index = 0  # Private attribute used by LiveCameraService validation
    camera.actual_width = 640
    camera.actual_height = 480
    camera.is_opened.return_value = True
    camera.connect.return_value = True

    # Generate fake frames
    def get_frame():
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        return True, fake_frame

    camera.get_frame = get_frame
    camera.release = Mock()

    return camera


@pytest.fixture
def mock_detector():
    """Create a mock detector."""
    detector = Mock()
    detector.detect.return_value = ([], None)  # No detections, no Arduino command
    detector.draw_overlay = Mock()
    return detector


@pytest.fixture
def mock_recorder():
    """Create a mock recorder."""
    recorder = Mock()
    recorder.start_recording.return_value = True
    recorder.stop_recording.return_value = None
    recorder.start_time = time.time()
    recorder.write_detection_data = Mock()
    return recorder


@pytest.fixture
def mock_settings():
    """Create mock settings with proper attribute values for Camera and LiveCameraService.

    Phase 3.4: Fixed to provide actual values instead of Mock objects
    to prevent TypeError in comparisons (e.g., max_reconnect_attempts > 0).
    Also configures model_copy() to return a copy with real values.
    """
    settings = Mock()

    # Live analysis settings
    settings.live_analysis.default_duration_s = 5
    settings.live_analysis.max_duration_s = 300
    settings.live_analysis.auto_stop_on_limit = True

    # Camera settings (used by Camera class)
    settings.camera.index = 0
    settings.camera.desired_width = 640
    settings.camera.desired_height = 480
    settings.camera.max_reconnect_attempts = 3  # Must be int, not Mock
    settings.camera.reconnect_timeout_seconds = 5.0
    settings.camera.max_frame_lag_ms = 1000.0

    # Video processing settings
    settings.video_processing.fps = 30.0

    # Logging settings (used by structlog in threads)
    settings.logging.level = "INFO"
    settings.logging.file_path = "analysis.log"

    # Configure model_copy() to return a settings object with same real values
    # This is called by LiveCameraService to create a temporary copy
    def model_copy_side_effect(**kwargs):
        copy_mock = Mock()
        # Apply any overrides from kwargs
        copy_mock.camera.index = kwargs.get("camera_index", 0)
        copy_mock.camera.desired_width = 1280  # LiveCameraService forces this
        copy_mock.camera.desired_height = 720  # LiveCameraService forces this
        copy_mock.camera.max_reconnect_attempts = 3
        copy_mock.camera.reconnect_timeout_seconds = 5.0
        copy_mock.camera.max_frame_lag_ms = 1000.0
        copy_mock.video_processing.fps = 30.0
        copy_mock.logging.level = "INFO"
        copy_mock.logging.file_path = "analysis.log"
        return copy_mock

    settings.model_copy.side_effect = model_copy_side_effect

    return settings


@pytest.fixture
def mock_main_view_model(mock_camera, mock_detector, mock_recorder, mock_settings):
    """Create a mock MainViewModel with necessary dependencies."""
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.live_camera_service import LiveCameraService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.recording_service import RecordingService
    from zebtrack.core.state_manager import StateManager

    controller = Mock()
    controller.settings = mock_settings
    controller.detector = mock_detector
    controller.recorder = mock_recorder
    controller.active_frame_source = None
    controller.program_exit_event = Mock()
    controller.program_exit_event.is_set.return_value = False

    # Mock view
    controller.view = Mock()
    controller.view.root = Mock()

    # Mock camera (stored in controller, not view)
    controller.camera = None  # Will be created by method if needed

    # Mock StateManager
    state_manager = Mock(spec=StateManager)
    state_manager.get_recording_state.return_value = Mock(is_recording=False)
    controller.state_manager = state_manager

    # Mock ProjectManager
    project_manager = Mock(spec=ProjectManager)
    project_manager.get_zone_data.return_value = None
    project_manager.project_data = {}
    controller.project_manager = project_manager

    # Mock UI Event Bus
    ui_event_bus = Mock()
    controller.ui_event_bus = ui_event_bus

    # Create real DetectorService with mock detector
    detector_service = Mock(spec=DetectorService)
    detector_service.detector = mock_detector
    detector_service.configure_zones = Mock()
    controller.detector_service = detector_service

    # Create real RecordingService
    recording_service = RecordingService(
        controller=controller,
        state_manager=state_manager,
        project_manager=project_manager,
        root=controller.view.root,
    )
    controller.recording_service = recording_service

    # Create real LiveCameraService
    live_camera_service = LiveCameraService(
        controller=controller,
        state_manager=state_manager,
        project_manager=project_manager,
        recording_service=recording_service,
        detector_service=detector_service,
        root=controller.view.root,
    )
    controller.live_camera_service = live_camera_service

    # Mock setup methods
    controller.setup_detector = Mock(return_value=True)
    controller.setup_detector_zones = Mock()

    # Phase 2.3: Mock RecordingSessionOrchestrator since start_live_camera_analysis delegates to it
    import structlog

    from zebtrack.orchestrators.recording_session_orchestrator import RecordingSessionOrchestrator
    from zebtrack.ui.events import Events

    log = structlog.get_logger()

    def mock_start_live_camera_analysis(camera_index=None):
        """Mock implementation that calls live_camera_service and handles errors.

        Phase 3.4: Updated to check return value from start_session() and publish
        error event when it returns False, mimicking RecordingSessionOrchestrator.
        Also checks if dialog was cancelled (dialog.result = None).
        """
        # If no camera_index provided, need to show dialog (will be mocked in tests)
        if camera_index is None:
            from zebtrack.ui.dialogs import LiveAnalysisDialog

            dialog = LiveAnalysisDialog(controller.view.root, settings_obj=controller.settings)

            # Mimic RecordingSessionOrchestrator dialog cancellation check (lines 626-628)
            if not dialog.result:
                log.info("controller.live_analysis.cancelled")
                return

            config = dialog.result
            camera_index = config["camera_index"]
            duration_s = config["duration_s"]
            experiment_id = config["experiment_id"]
            analysis_interval_frames = config.get("analysis_interval_frames", 1)
            display_interval_frames = config.get("display_interval_frames", 1)
            record_video = config.get("record_video", True)
        else:
            # Use defaults when camera_index is provided directly
            duration_s = 5
            experiment_id = "test"
            analysis_interval_frames = 1
            display_interval_frames = 30
            record_video = True

        try:
            success = live_camera_service.start_session(
                camera_index=camera_index,
                duration_s=duration_s,
                experiment_id=experiment_id,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                record_video=record_video,
            )

            # Mimic RecordingSessionOrchestrator error handling (lines 653-660)
            if not success and controller.ui_event_bus:
                controller.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro na Análise",
                        "message": "Falha ao iniciar análise de câmera.",
                    },
                )

            return success

        except Exception as e:
            # Mimic error handling from real RecordingSessionOrchestrator
            if controller.ui_event_bus:
                controller.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro na Análise",
                        "message": f"Falha ao iniciar análise de câmera: {e}",
                    },
                )
            return False

    recording_session_orchestrator = Mock(spec=RecordingSessionOrchestrator)
    recording_session_orchestrator.start_live_camera_analysis.side_effect = (
        mock_start_live_camera_analysis
    )
    controller.recording_session_orchestrator = recording_session_orchestrator

    return controller


def test_live_camera_analysis_uses_recording_service(mock_main_view_model, mock_camera):
    """Test that LiveCameraService calls recorder.start_recording directly."""
    from zebtrack.core.main_view_model import MainViewModel

    # Patch the dialog, Camera, and LivePreviewWindow to return config
    with (
        patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class,
        patch("zebtrack.io.camera.Camera") as mock_camera_class,
        patch("zebtrack.ui.dialogs.LivePreviewWindow") as _mock_preview_class,
    ):
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 5,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "test_experiment",
        }
        mock_dialog_class.return_value = mock_dialog
        mock_camera_class.return_value = mock_camera

        # Create MainViewModel instance (partial mock)
        controller = mock_main_view_model

        # Mock recorder.start_recording to return True
        controller.recorder.start_recording.return_value = True

        # Manually call the method (since we're using Mock, we need to bind it)
        MainViewModel.start_live_camera_analysis(controller)

        # Verify recorder.start_recording was called by LiveCameraService
        assert controller.recorder.start_recording.called

        # Verify context passed contains expected keys
        call_args = controller.recorder.start_recording.call_args
        assert call_args is not None

        # Check that output_folder was passed
        assert "output_folder" in call_args[1] or len(call_args[0]) > 0


def test_live_camera_analysis_sets_active_frame_source(mock_main_view_model, mock_camera):
    """Test that active_frame_source is set to camera for live loops to consume."""
    from zebtrack.core.main_view_model import MainViewModel

    with (
        patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class,
        patch("zebtrack.io.camera.Camera") as mock_camera_class,
        patch("zebtrack.ui.dialogs.LivePreviewWindow") as _mock_preview_class,
    ):
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 3,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": False,
            "experiment_id": "test_source",
        }
        mock_dialog_class.return_value = mock_dialog
        mock_camera_class.return_value = mock_camera

        controller = mock_main_view_model

        MainViewModel.start_live_camera_analysis(controller)

        # Verify active_frame_source points to camera
        assert controller.active_frame_source is controller.camera


def test_live_camera_analysis_enables_timed_recording(mock_main_view_model, mock_camera):
    """Test that timed recording is enabled in project_data."""
    from zebtrack.core.main_view_model import MainViewModel

    with (
        patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class,
        patch("zebtrack.io.camera.Camera") as mock_camera_class,
        patch("zebtrack.ui.dialogs.LivePreviewWindow") as _mock_preview_class,
    ):
        mock_dialog = Mock()
        duration_s = 10
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": duration_s,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "timed_test",
        }
        mock_dialog_class.return_value = mock_dialog
        mock_camera_class.return_value = mock_camera

        controller = mock_main_view_model

        # Spy on RecordingService.start_session
        original_start = controller.recording_service.start_session

        def spy_start_session(context, project_data, trigger_source):
            # Verify timed recording is enabled
            assert project_data["use_timed_recording"] is True
            assert project_data["recording_duration_s"] == duration_s
            assert project_data["use_countdown"] is False
            assert trigger_source == "live_analysis"
            return original_start(context, project_data, trigger_source)

        controller.recording_service.start_session = spy_start_session

        MainViewModel.start_live_camera_analysis(controller)


def test_live_camera_analysis_creates_output_directory(mock_main_view_model, mock_camera, tmp_path):
    """Test that output directory is created in live_analysis_sessions/."""
    from pathlib import Path

    from zebtrack.core.main_view_model import MainViewModel

    with (
        patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class,
        patch("zebtrack.io.camera.Camera") as mock_camera_class,
        patch("zebtrack.ui.dialogs.LivePreviewWindow") as _mock_preview_class,
    ):
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 5,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "output_test",
        }
        mock_dialog_class.return_value = mock_dialog
        mock_camera_class.return_value = mock_camera

        controller = mock_main_view_model

        MainViewModel.start_live_camera_analysis(controller)

        # Verify output directory was created in live_analysis_sessions/
        live_analysis_dir = Path("live_analysis_sessions")
        assert live_analysis_dir.exists()

        # Find directories containing the experiment_id
        output_dirs = list(live_analysis_dir.glob("output_test_*"))
        assert len(output_dirs) > 0, "No output directory created with experiment_id"
        assert "output_test" in str(output_dirs[0])


def test_live_camera_analysis_dialog_cancelled(mock_main_view_model):
    """Test that cancelling dialog does not start recording."""
    from zebtrack.core.main_view_model import MainViewModel

    with patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class:
        mock_dialog = Mock()
        mock_dialog.result = None  # User cancelled
        mock_dialog_class.return_value = mock_dialog

        controller = mock_main_view_model

        MainViewModel.start_live_camera_analysis(controller)

        # Verify recorder was NOT started
        assert not controller.recorder.start_recording.called


def test_live_camera_analysis_camera_unavailable(mock_main_view_model):
    """Test error handling when camera is unavailable."""
    from zebtrack.core.main_view_model import MainViewModel

    with patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class:
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 5,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "error_test",
        }
        mock_dialog_class.return_value = mock_dialog

        controller = mock_main_view_model
        controller.camera = None  # No camera available

        # Patch Camera to raise an exception
        with patch("zebtrack.io.camera.Camera") as mock_camera_class:
            mock_camera_class.side_effect = OSError("Cannot open camera")

            MainViewModel.start_live_camera_analysis(controller)

            # Verify error event was published
            assert controller.ui_event_bus.publish_event.called

            # Verify recorder was NOT started
            assert not controller.recorder.start_recording.called


def test_live_camera_analysis_detector_setup_fails(mock_main_view_model):
    """Test error handling when detector setup fails.

    Phase 3.4: Fixed to properly configure detector_service.detector,
    which is what LiveCameraService actually checks.
    """
    from zebtrack.core.main_view_model import MainViewModel

    with patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class:
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 5,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "detector_fail",
        }
        mock_dialog_class.return_value = mock_dialog

        controller = mock_main_view_model
        # Phase 3.4: Set detector_service.detector to None (not controller.detector)
        # because LiveCameraService checks detector_service.detector
        controller.detector_service.detector = None
        controller.setup_detector.return_value = False  # Setup fails

        MainViewModel.start_live_camera_analysis(controller)

        # Verify error event was published
        assert controller.ui_event_bus.publish_event.called

        # Verify recorder was NOT started
        assert not controller.recorder.start_recording.called


def test_live_camera_analysis_no_arduino(mock_main_view_model, mock_camera):
    """Test that live analysis starts recorder directly without Arduino support."""
    from zebtrack.core.main_view_model import MainViewModel

    with (
        patch("zebtrack.ui.dialogs.LiveAnalysisDialog") as mock_dialog_class,
        patch("zebtrack.io.camera.Camera") as mock_camera_class,
        patch("zebtrack.ui.dialogs.LivePreviewWindow") as _mock_preview_class,
    ):
        mock_dialog = Mock()
        mock_dialog.result = {
            "camera_index": 0,
            "duration_s": 5,
            "analysis_interval_frames": 1,
            "display_interval_frames": 30,
            "record_video": True,
            "experiment_id": "no_arduino",
        }
        mock_dialog_class.return_value = mock_dialog
        mock_camera_class.return_value = mock_camera

        controller = mock_main_view_model

        MainViewModel.start_live_camera_analysis(controller)

        # Verify recorder was started directly by LiveCameraService
        # (Arduino is implicitly not used since RecordingService is bypassed)
        assert controller.recorder.start_recording.called
