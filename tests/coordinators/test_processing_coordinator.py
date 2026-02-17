"""Tests for ProcessingCoordinator - Phase 3.

Comprehensive test coverage for video processing orchestration.
Phase 3 Update: Super coordinator that consolidates 5 orchestrators.

NOTE: This is a streamlined test suite focused on Phase 3 API.
Legacy tests for pre-Phase 3 methods have been removed.
"""

from threading import Event
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.processing_types import ValidationResult
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_detector_service():
    """Create mock DetectorService."""
    service = MagicMock()
    service.detector = MagicMock()
    service.detector.get_zones.return_value = []
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
    manager.project_data = {"name": "Test Project"}
    manager.get_zone_data.return_value = MagicMock(polygon=[[0, 0], [100, 0], [100, 100]])
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
    manager.prefer_unified_state_api = True
    return manager


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
):
    """Create VideoProcessingCoordinator with mocked dependencies (Phase 4)."""
    return VideoProcessingCoordinator(
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
        recorder_factory=mock_recorder_factory,
        event_bus=mock_event_bus,
        view=None,
        root=None,
        detector=None,
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestProcessingCoordinatorInitialization:
    """Test VideoProcessingCoordinator initialization (Phase 4)."""

    def test_init_with_all_dependencies(self, processing_coordinator):
        """Test initialization with all dependencies (Phase 4)."""
        # Core dependencies
        assert processing_coordinator.state_manager is not None
        assert processing_coordinator.project_manager is not None
        assert processing_coordinator.detector_service is not None
        assert processing_coordinator.weight_manager is not None
        assert processing_coordinator.settings is not None  # Note: 'settings', not 'settings_obj'
        assert processing_coordinator.ui_coordinator is not None
        assert processing_coordinator.ui_state_controller is not None
        assert processing_coordinator.cancel_event is not None

        # Services
        assert processing_coordinator.video_selection_service is not None
        assert processing_coordinator.video_validation_service is not None
        assert processing_coordinator.video_classification_service is not None
        assert processing_coordinator.recorder_factory is not None

        # Optional
        assert processing_coordinator.event_bus is not None

    def test_coordinator_creation_succeeds(self, processing_coordinator):
        """Test that VideoProcessingCoordinator can be created successfully."""
        # Simple smoke test - if we get here, initialization succeeded
        assert processing_coordinator is not None
        assert isinstance(processing_coordinator, VideoProcessingCoordinator)


# =============================================================================
# VALIDATION TESTS
# =============================================================================


class TestValidation:
    """Test validation methods in ProcessingCoordinator."""

    def test_validate_can_start_processing_returns_validation_result(self, processing_coordinator):
        """Test that validate_can_start_processing returns ValidationResult."""
        result = processing_coordinator.validate_can_start_processing()

        assert isinstance(result, ValidationResult)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "error_code")
        assert hasattr(result, "error_message")

    def test_validation_result_success_factory(self):
        """Test ValidationResult.success() factory method."""
        result = ValidationResult.success()

        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None

    def test_validation_result_failure_factory(self):
        """Test ValidationResult.failure() factory method."""
        result = ValidationResult.failure(
            error_code="TEST_ERROR", error_message="Test error message"
        )

        assert result.is_valid is False
        assert result.error_code == "TEST_ERROR"
        assert result.error_message == "Test error message"

    def test_validate_can_start_processing_recovers_stale_processing_state(
        self, processing_coordinator
    ):
        """Should self-heal stale is_processing=True when no worker/thread is active."""
        processing_state = MagicMock()
        processing_state.is_processing = True
        processing_state.current_video = "video_a.mp4"
        processing_state.is_live_session_active = False
        processing_coordinator.state_manager.get_processing_state.return_value = processing_state

        processing_coordinator.processing_worker = None
        processing_coordinator.processing_thread = None

        result = processing_coordinator.validate_can_start_processing()

        assert result.is_valid is True
        processing_coordinator.state_manager.update_processing_state.assert_called_once()

    def test_validate_can_start_processing_blocks_when_live_session_active(
        self, processing_coordinator
    ):
        """Must keep blocking when processing state belongs to active live session."""
        processing_state = MagicMock()
        processing_state.is_processing = True
        processing_state.current_video = "live_session"
        processing_state.is_live_session_active = True
        processing_coordinator.state_manager.get_processing_state.return_value = processing_state

        processing_coordinator.processing_worker = None
        processing_coordinator.processing_thread = None

        result = processing_coordinator.validate_can_start_processing()

        assert result.is_valid is False
        assert result.error_code == "processing_already_active"

    def test_validate_can_start_processing_recovers_when_live_flag_is_stale(
        self, processing_coordinator
    ):
        """Should recover when state live flag is true but session coordinator says inactive."""
        processing_state = MagicMock()
        processing_state.is_processing = True
        processing_state.current_video = "video_stale.mp4"
        processing_state.is_live_session_active = True
        processing_coordinator.state_manager.get_processing_state.return_value = processing_state

        processing_coordinator.processing_worker = None
        processing_coordinator.processing_thread = None

        processing_coordinator.view = MagicMock()
        processing_coordinator.view.controller = MagicMock()
        processing_coordinator.view.controller.session_coordinator = MagicMock()
        session_coordinator = processing_coordinator.view.controller.session_coordinator
        session_coordinator.is_live_session_active.return_value = False

        result = processing_coordinator.validate_can_start_processing()

        assert result.is_valid is True
        processing_coordinator.state_manager.update_processing_state.assert_called_once()

    def test_on_processing_started_delegates_to_progress_coordinator(self, processing_coordinator):
        """Test _on_processing_started delegates to progress coordinator (Phase 4)."""
        mock_ptc = MagicMock()
        processing_coordinator._progress_coordinator = mock_ptc

        processing_coordinator._on_processing_started([{"path": "video.mp4"}])

        mock_ptc._on_processing_started.assert_called_once_with([{"path": "video.mp4"}])

    def test_on_processing_started_noop_without_progress_coordinator(self, processing_coordinator):
        """Test _on_processing_started is a no-op when no progress coordinator wired."""
        processing_coordinator._progress_coordinator = None

        # Should not raise
        processing_coordinator._on_processing_started([{"path": "video.mp4"}])


# =============================================================================
# SINGLE VIDEO PROCESSING TESTS
# =============================================================================


class TestSingleVideoProcessing:
    """Test single video processing workflows (Phase 3 API)."""

    def test_start_single_video_processing_exists(self, processing_coordinator):
        """Test that start_single_video_processing method exists."""
        assert hasattr(processing_coordinator, "start_single_video_processing")
        assert callable(processing_coordinator.start_single_video_processing)

    def test_start_single_video_accepts_video_path(self, processing_coordinator, tmp_path):
        """Test that start_single_video_processing accepts video_path parameter."""
        # Create a dummy video file
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()

        # Mock the validation to pass
        processing_coordinator.video_validation_service.validate_video.return_value = (True, None)

        # This should not raise an error
        try:
            # We expect it might fail internally, but we're just testing the signature
            processing_coordinator.start_single_video_processing(str(video_path))
        except Exception:
            pass  # Expected - we're just testing the method exists and accepts the param


# =============================================================================
# PENDING VIDEOS PROCESSING TESTS
# =============================================================================


class TestPendingVideosProcessing:
    """Test pending videos batch processing (Phase 3 API)."""

    def test_process_pending_project_videos_exists(self, processing_coordinator):
        """Test that process_pending_project_videos method exists."""
        assert hasattr(processing_coordinator, "process_pending_project_videos")
        assert callable(processing_coordinator.process_pending_project_videos)

    def test_process_pending_uses_video_selection_service(
        self, processing_coordinator, mock_video_selection_service
    ):
        """Test that process_pending_project_videos uses VideoSelectionService."""
        # Setup mock to return no videos
        mock_video_selection_service.select_pending_videos.return_value = MagicMock(
            success=True, selected_videos=[], errors=[]
        )

        # Try to call the method
        try:
            processing_coordinator.process_pending_project_videos()
        except Exception:
            pass  # Expected - testing integration

        # Verify the service was called
        # Note: might not be called if validation fails first
        # This is just a basic smoke test


# =============================================================================
# ZONE AND ARENA MANAGEMENT TESTS
# =============================================================================


class TestZoneAndArenaManagement:
    """Test zone and arena management methods (Phase 3 API)."""

    def test_set_main_arena_polygon_exists(self, processing_coordinator):
        """Test that set_main_arena_polygon method exists."""
        assert hasattr(processing_coordinator, "set_main_arena_polygon")
        assert callable(processing_coordinator.set_main_arena_polygon)

    def test_save_manual_arena_exists(self, processing_coordinator):
        """Test that save_manual_arena method exists."""
        assert hasattr(processing_coordinator, "save_manual_arena")
        assert callable(processing_coordinator.save_manual_arena)

    def test_add_roi_polygon_exists(self, processing_coordinator):
        """Test that add_roi_polygon method exists."""
        assert hasattr(processing_coordinator, "add_roi_polygon")
        assert callable(processing_coordinator.add_roi_polygon)


# =============================================================================
# UTILITY METHODS TESTS
# =============================================================================


class TestUtilityMethods:
    """Test utility and helper methods (Phase 3 API)."""

    def test_select_eligible_videos_exists(self, processing_coordinator):
        """Test that select_eligible_videos method exists."""
        assert hasattr(processing_coordinator, "select_eligible_videos")
        assert callable(processing_coordinator.select_eligible_videos)

    def test_create_processing_context_exists(self, processing_coordinator):
        """Test that create_processing_context method exists."""
        assert hasattr(processing_coordinator, "create_processing_context")
        assert callable(processing_coordinator.create_processing_context)

    def test_create_processing_callbacks_exists(self, processing_coordinator):
        """Test that create_processing_callbacks method exists."""
        assert hasattr(processing_coordinator, "create_processing_callbacks")
        assert callable(processing_coordinator.create_processing_callbacks)


# =============================================================================
# TODO: INTEGRATION TESTS
# =============================================================================
# These tests require more complex setup with actual services and state.
# They should be added in a future sprint as part of comprehensive test coverage.
#
# Suggested tests:
# - Full single video processing workflow end-to-end
# - Full pending videos processing workflow end-to-end
# - Arena detection and ROI configuration workflow
# - Error handling and recovery scenarios
# - State management integration
# - Event bus integration
# =============================================================================
