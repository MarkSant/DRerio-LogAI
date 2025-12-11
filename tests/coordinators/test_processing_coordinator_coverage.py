"""Tests for ProcessingCoordinator - Coverage.

Comprehensive test coverage for video processing orchestration.
Consolidates coverage for Phase 3 Super Coordinator including:
- Video processing workflows
- Analysis workflows
- Zone and arena management
- Processing configuration
- Validation logic
"""

from threading import Event
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from zebtrack.coordinators.processing_coordinator import (
    ProcessingCoordinator,
)
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.ui.events import Events

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_detector_service():
    """Create mock DetectorService."""
    service = MagicMock()
    service.detector = MagicMock()
    service.detector.get_zones.return_value = []
    # Ensure is_single_subject_mode returns a boolean, not a Mock (which is truthy)
    service.detector.is_single_subject_mode.return_value = False
    service._resolve_single_subject_tracker_preference.return_value = None
    return service


@pytest.fixture
def mock_weight_manager():
    """Create mock WeightManager."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    """Create mock Settings."""
    settings = MagicMock()
    settings.processing = MagicMock()
    settings.processing.enable_parallel_analysis = False
    settings.processing.max_parallel_videos = 1

    settings.tracking = MagicMock()
    settings.tracking.use_single_subject_tracker = False

    settings.video_processing = MagicMock()
    settings.video_processing.single_animal_per_aquarium = False
    settings.video_processing.batch_retry_strategy = "retry"
    settings.video_processing.fps = 30
    settings.video_processing.sharp_turn_threshold_deg_s = 45
    settings.video_processing.freezing_velocity_threshold = 0.5
    settings.video_processing.freezing_min_duration_s = 1.0

    settings.trajectory_smoothing = MagicMock()
    settings.trajectory_smoothing.window_length = 51
    settings.trajectory_smoothing.polyorder = 3

    settings.model_selection = MagicMock()
    settings.model_selection.aquarium_method = "mask"

    return settings


@pytest.fixture
def mock_ui_coordinator():
    """Create mock UIScheduler."""
    return MagicMock()


@pytest.fixture
def mock_ui_state_controller():
    """Create mock UIStateController."""
    return MagicMock()


@pytest.fixture
def mock_cancel_event():
    """Create mock threading.Event."""
    return Event()


@pytest.fixture
def mock_video_selection_service():
    """Create mock VideoSelectionService."""
    service = MagicMock()
    service.select_pending_videos.return_value = MagicMock(
        success=True, selected_videos=[], errors=[]
    )
    return service


@pytest.fixture
def mock_video_validation_service():
    """Create mock VideoValidationService."""
    service = MagicMock()
    service.validate_video.return_value = (True, None)
    return service


@pytest.fixture
def mock_video_classification_service():
    """Create mock VideoClassificationService."""
    return MagicMock()


@pytest.fixture
def mock_analysis_service():
    """Create mock AnalysisService."""
    return MagicMock()


@pytest.fixture
def mock_project_manager():
    """Create mock ProjectManager."""
    manager = MagicMock()
    manager.project_path = "/path/to/project"
    manager.project_data = {
        "name": "Test Project",
        "calibration": {
            "aquarium_width_cm": 100,
            "aquarium_height_cm": 50,
            "animals_per_aquarium": 1,
        },
        "analysis_interval_frames": 5,
        "display_interval_frames": 5,
    }
    manager.get_zone_data.return_value = ZoneData(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])
    manager.get_all_videos.return_value = []
    manager.resolve_results_directory.return_value = "/path/to/results"
    return manager


@pytest.fixture
def mock_recorder_factory():
    """Create mock RecorderFactory."""
    return MagicMock()


@pytest.fixture
def mock_event_bus():
    """Create mock EventBus."""
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    manager = MagicMock()
    manager.get_state.return_value = {}
    manager.get_processing_state.return_value = MagicMock(is_processing=False)
    return manager


@pytest.fixture
def mock_view():
    """Create mock View."""
    view = MagicMock()
    return view


@pytest.fixture
def mock_detector():
    """Create mock Detector."""
    detector = MagicMock()
    detector.plugin = MagicMock()
    detector.plugin.get_name.return_value = "TestPlugin"
    # Ensure is_single_subject_mode returns a boolean, not a Mock (which is truthy)
    detector.is_single_subject_mode.return_value = False
    return detector


@pytest.fixture
def processing_coordinator(
    mock_state_manager,
    mock_project_manager,
    mock_detector_service,
    mock_weight_manager,
    mock_settings,
    mock_ui_coordinator,
    mock_ui_state_controller,
    mock_cancel_event,
    mock_video_selection_service,
    mock_video_validation_service,
    mock_video_classification_service,
    mock_analysis_service,
    mock_recorder_factory,
    mock_event_bus,
    mock_view,
    mock_detector,
):
    """Create ProcessingCoordinator with mocked dependencies."""
    return ProcessingCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        weight_manager=mock_weight_manager,
        settings_obj=mock_settings,
        ui_coordinator=mock_ui_coordinator,
        ui_state_controller=mock_ui_state_controller,
        cancel_event=mock_cancel_event,
        video_selection_service=mock_video_selection_service,
        video_validation_service=mock_video_validation_service,
        video_classification_service=mock_video_classification_service,
        analysis_service=mock_analysis_service,
        recorder_factory=mock_recorder_factory,
        event_bus=mock_event_bus,
        view=mock_view,
        root=MagicMock(),
        detector=mock_detector,
    )


# =============================================================================
# TESTS
# =============================================================================


class TestProcessingIntervals:
    """Test determination of processing intervals."""

    def test_determine_processing_intervals_uses_settings(
        self, processing_coordinator, mock_project_manager
    ):
        """Test that intervals are determined correctly from project settings."""
        # Setup project manager with specific interval
        mock_project_manager.project_data = {
            "analysis_interval_frames": 5,
            "display_interval_frames": 5,
        }

        # Call the method (private, so accessing via underscore)
        analysis, display = processing_coordinator._determine_processing_intervals(None)

        # Expectation
        assert analysis == 5
        assert display == 5

    def test_determine_processing_intervals_uses_config(self, processing_coordinator):
        """Test that intervals are determined from single video config."""
        config = {"analysis_interval_frames": 2, "display_interval_frames": 4}

        analysis, display = processing_coordinator._determine_processing_intervals(config)

        assert analysis == 2
        assert display == 4

    def test_determine_processing_intervals_defaults(
        self, processing_coordinator, mock_project_manager
    ):
        """Test default values when no settings are present."""
        mock_project_manager.project_data = {}

        analysis, display = processing_coordinator._determine_processing_intervals(None)

        # Default is 10
        assert analysis == 10
        assert display == 10


class TestValidation:
    """Test validation logic."""

    def test_validate_can_start_processing_success(self, processing_coordinator):
        """Test successful validation."""
        result = processing_coordinator.validate_can_start_processing()
        assert result.is_valid is True

    def test_validate_already_processing(self, processing_coordinator, mock_state_manager):
        """Test validation fails when already processing."""
        mock_state_manager.get_processing_state.return_value = MagicMock(is_processing=True)

        result = processing_coordinator.validate_can_start_processing()

        assert result.is_valid is False
        assert result.error_code == "processing_already_active"

    def test_validate_no_project(self, processing_coordinator, mock_project_manager):
        """Test validation fails when no project is loaded."""
        mock_project_manager.project_path = None

        result = processing_coordinator.validate_can_start_processing(check_project_loaded=True)

        assert result.is_valid is False
        assert result.error_code == "no_project_loaded"

    def test_validate_no_zones(self, processing_coordinator, mock_project_manager):
        """Test validation fails when no zones are defined."""
        mock_project_manager.get_zone_data.return_value = ZoneData()  # Empty

        result = processing_coordinator.validate_can_start_processing(check_zones=True)

        assert result.is_valid is False
        assert result.error_code == "no_main_arena"


class TestProcessingMode:
    """Test processing mode determination."""

    def test_determine_processing_mode_single(self, processing_coordinator, mock_settings):
        """Test single subject mode determination."""
        mock_settings.tracking.use_single_subject_tracker = True

        mode = processing_coordinator._determine_processing_mode()
        assert mode == ProcessingMode.SINGLE_SUBJECT

    def test_determine_processing_mode_multi(self, processing_coordinator, mock_settings):
        """Test multi track mode determination."""
        mock_settings.tracking.use_single_subject_tracker = False

        mode = processing_coordinator._determine_processing_mode()
        assert mode == ProcessingMode.MULTI_TRACK

    def test_publish_processing_mode(self, processing_coordinator, mock_ui_state_controller):
        """Test publishing processing mode."""
        processing_coordinator._publish_processing_mode(source="test", force=True)

        assert mock_ui_state_controller._schedule_on_ui.called


class TestZoneManagement:
    """Test zone and arena management."""

    def test_set_main_arena_polygon(
        self, processing_coordinator, mock_project_manager, mock_event_bus
    ):
        """Test setting main arena polygon."""
        points = [[0, 0], [10, 0], [10, 10], [0, 10]]

        success = processing_coordinator.set_main_arena_polygon(points)

        assert success is True
        mock_project_manager.update_main_polygon.assert_called_with(points)
        mock_event_bus.publish_event.assert_called()

    def test_add_roi_polygon_valid(self, processing_coordinator, mock_project_manager):
        """Test adding a valid ROI."""
        # Main arena is 100x100
        roi_points = [[10, 10], [20, 10], [20, 20], [10, 20]]

        success = processing_coordinator.add_roi_polygon(roi_points, "ROI 1", (255, 0, 0))

        assert success is True
        mock_project_manager.save_zone_data.assert_called()

    def test_add_roi_outside_arena_rejected(
        self, processing_coordinator, mock_project_manager, mock_view
    ):
        """Test adding ROI outside arena."""
        # ROI completely outside 100x100 arena
        roi_points = [[200, 200], [210, 200], [210, 210], [200, 210]]

        # User rejects overlap
        mock_view.ask_ok_cancel.return_value = False

        success = processing_coordinator.add_roi_polygon(roi_points, "Outside ROI", (255, 0, 0))

        assert success is False


class TestVideoProcessingWorkflow:
    """Test video processing workflows."""

    def test_start_single_video_processing_validation_failure(
        self, processing_coordinator, mock_state_manager
    ):
        """Test that single video processing stops if validation fails."""
        # Fail validation by being already processing
        mock_state_manager.get_processing_state.return_value = MagicMock(is_processing=True)

        processing_coordinator.start_single_video_processing("video.mp4", {}, ZoneData())

        # Should not start worker
        assert processing_coordinator.processing_worker is None

    def test_process_pending_project_videos_no_eligible(
        self,
        processing_coordinator,
        mock_video_selection_service,
        mock_event_bus,
        mock_project_manager,
    ):
        """Test processing pending videos when none are eligible."""
        # Setup: Project must have videos to pass validation
        mock_project_manager.get_all_videos.return_value = [{"path": "video.mp4"}]

        # Mock selection to return nothing
        mock_result = MagicMock()
        mock_result.candidate_count = 0
        mock_result.selection_mode = "pending"
        mock_video_selection_service.select_candidates.return_value = mock_result

        processing_coordinator.process_pending_project_videos()

        # Verify UI info shown (should be INFO because validation passed but selection failed)
        args = mock_event_bus.publish_event.call_args[0]
        assert args[0] == Events.UI_SHOW_INFO


class TestCallbacks:
    """Test processing callbacks."""

    def test_create_processing_callbacks(self, processing_coordinator):
        """Test creation of callbacks structure."""
        callbacks = processing_coordinator.create_processing_callbacks([])

        assert callbacks.on_started is not None
        assert callbacks.on_progress is not None
        assert callbacks.on_completed is not None
        assert callbacks.on_error is not None

    def test_on_completed_callback(
        self, processing_coordinator, mock_project_manager, mock_ui_coordinator
    ):
        """Test on_completed callback."""
        callbacks = processing_coordinator.create_processing_callbacks([])

        # Simulate completion
        callbacks.on_completed(False, "/output/dir")

        # Should hide progress
        mock_ui_coordinator.hide_progress_bar.assert_called()
        # Should refresh views
        assert processing_coordinator.event_bus.publish_event.called


class TestReportGeneration:
    """Test report generation logic."""

    @patch("zebtrack.coordinators.processing_coordinator.pd.read_parquet")
    @patch("zebtrack.coordinators.processing_coordinator.Reporter")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_process_summary_video_success(
        self,
        mock_makedirs,
        mock_exists,
        mock_reporter,
        mock_read_parquet,
        processing_coordinator,
        mock_project_manager,
    ):
        """Test successful summary generation for a video."""
        mock_exists.return_value = True
        mock_read_parquet.return_value = pd.DataFrame({"x": [1, 2], "y": [1, 2]})

        video = {
            "path": "/path/to/video.mp4",
            "metadata": {"group": "A"},
            "parquet_files": {"trajectory": "/path/to/traj.parquet"},
        }

        state, eid, path, changed = processing_coordinator._process_summary_video(
            video, processing_coordinator.settings
        )

        if state != "completed":
            print(f"DEBUG: Failure reason: {eid}")  # eid contains error message in failure case

        assert state == "completed"
        assert changed is True
        mock_reporter.return_value.export_summary_data.assert_called()

    def test_process_summary_video_no_path(self, processing_coordinator):
        """Test summary fails if video has no path."""
        video = {}
        state, msg, _, _ = processing_coordinator._process_summary_video(video, None)
        assert state == "skipped"


class TestAquariumDetection:
    """Test aquarium detection workflow."""

    @patch("zebtrack.coordinators.processing_coordinator.AquariumDetector")
    def test_run_aquarium_detection_success(
        self, mock_detector_cls, processing_coordinator, mock_project_manager, mock_event_bus
    ):
        """Test successful aquarium detection."""
        # Setup mocks
        mock_instance = mock_detector_cls.return_value
        mock_instance.detect_aquariums.return_value = [[[0, 0], [10, 0], [10, 10], [0, 10]]]

        mock_project_manager.get_next_video.return_value = "/path/video.mp4"

        processing_coordinator.run_aquarium_detection()

        # Verify polygon setup event
        args = mock_event_bus.publish_event.call_args_list
        # Should have published SETUP_INTERACTIVE_POLYGON
        assert any(call[0][0] == Events.UI_SETUP_INTERACTIVE_POLYGON for call in args)
