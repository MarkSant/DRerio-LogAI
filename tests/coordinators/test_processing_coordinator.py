"""Tests for ProcessingCoordinator - Sprint 6.

Comprehensive test coverage for video processing orchestration.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.base import CoordinatorValidationError
from zebtrack.coordinators.processing_coordinator import (
    ProcessingCoordinator,
    ProcessingCoordinatorError,
)
from zebtrack.core.state_manager import StateCategory, StateManager


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_video_orchestrator():
    """Create mock VideoOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.start_project_processing_workflow.return_value = None
    orchestrator.process_pending_project_videos.return_value = None
    orchestrator.cancel_current_analysis.return_value = None
    return orchestrator


@pytest.fixture
def mock_video_processing_service():
    """Create mock VideoProcessingService."""
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
    return manager


@pytest.fixture
def processing_coordinator(
    mock_state_manager,
    mock_video_orchestrator,
    mock_video_processing_service,
    mock_analysis_service,
    mock_project_manager,
    mock_recorder_factory,
    mock_event_bus,
):
    """Create ProcessingCoordinator with mocked dependencies."""
    return ProcessingCoordinator(
        state_manager=mock_state_manager,
        video_orchestrator=mock_video_orchestrator,
        video_processing_service=mock_video_processing_service,
        analysis_service=mock_analysis_service,
        project_manager=mock_project_manager,
        recorder_factory=mock_recorder_factory,
        event_bus=mock_event_bus,
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestProcessingCoordinatorInitialization:
    """Test ProcessingCoordinator initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_video_orchestrator,
        mock_video_processing_service,
        mock_analysis_service,
        mock_project_manager,
        mock_recorder_factory,
        mock_event_bus,
    ):
        """Test initialization with all dependencies."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            video_orchestrator=mock_video_orchestrator,
            video_processing_service=mock_video_processing_service,
            analysis_service=mock_analysis_service,
            project_manager=mock_project_manager,
            recorder_factory=mock_recorder_factory,
            event_bus=mock_event_bus,
        )

        assert coordinator.state_manager == mock_state_manager
        assert coordinator.video_orchestrator == mock_video_orchestrator
        assert coordinator.video_processing_service == mock_video_processing_service
        assert coordinator.analysis_service == mock_analysis_service
        assert coordinator.project_manager == mock_project_manager
        assert coordinator.recorder_factory == mock_recorder_factory
        assert coordinator.event_bus == mock_event_bus

    def test_init_without_optional_dependencies(self, mock_state_manager):
        """Test initialization without optional dependencies."""
        coordinator = ProcessingCoordinator(state_manager=mock_state_manager)

        assert coordinator.video_orchestrator is None
        assert coordinator.video_processing_service is None
        assert coordinator.analysis_service is None
        assert coordinator.project_manager is None
        assert coordinator.recorder_factory is None
        assert coordinator.event_bus is None

    def test_validate_dependencies_passes(self, processing_coordinator):
        """Test that validate_dependencies returns True."""
        assert processing_coordinator.validate_dependencies() is True


# =============================================================================
# PROJECT PROCESSING WORKFLOW TESTS
# =============================================================================


class TestProjectProcessingWorkflow:
    """Test project-level batch processing workflows."""

    def test_start_project_processing_success(
        self,
        processing_coordinator,
        mock_video_orchestrator,
    ):
        """Test successful project processing start."""
        success = processing_coordinator.start_project_processing_workflow()

        assert success is True
        mock_video_orchestrator.start_project_processing_workflow.assert_called_once()

    def test_start_project_processing_without_validation(
        self,
        processing_coordinator,
        mock_video_orchestrator,
    ):
        """Test project processing start without zone validation."""
        success = processing_coordinator.start_project_processing_workflow(
            validate_zones=False
        )

        assert success is True
        mock_video_orchestrator.start_project_processing_workflow.assert_called_once()

    def test_start_project_processing_updates_state(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test that start_project_processing updates StateManager."""
        processing_coordinator.start_project_processing_workflow()

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[0][0] == StateCategory.PROCESSING
        assert call_args[1]["is_processing"] is True
        assert call_args[1]["processing_type"] == "project_batch"

    def test_start_project_processing_publishes_event(
        self,
        processing_coordinator,
        mock_event_bus,
    ):
        """Test that start_project_processing publishes event."""
        processing_coordinator.start_project_processing_workflow()

        mock_event_bus.publish_event.assert_called()
        # Find the success event
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "PROJECT_PROCESSING_STARTED" in calls

    def test_start_project_processing_no_project_manager(
        self,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test start_project_processing without ProjectManager."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=None,
        )

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.start_project_processing_workflow()

        assert "ProjectManager is required" in str(exc_info.value)

    def test_start_project_processing_no_orchestrator(
        self,
        mock_state_manager,
        mock_project_manager,
    ):
        """Test start_project_processing without VideoOrchestrator."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            video_orchestrator=None,
        )

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.start_project_processing_workflow()

        assert "VideoOrchestrator is required" in str(exc_info.value)

    def test_start_project_processing_already_active(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test start_project_processing when processing already active."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        success = processing_coordinator.start_project_processing_workflow()

        assert success is False

    def test_start_project_processing_no_project_loaded(
        self,
        processing_coordinator,
        mock_project_manager,
    ):
        """Test start_project_processing when no project is loaded."""
        mock_project_manager.project_path = None

        success = processing_coordinator.start_project_processing_workflow()

        assert success is False

    def test_start_project_processing_no_zones(
        self,
        processing_coordinator,
        mock_project_manager,
    ):
        """Test start_project_processing when zones are not defined."""
        mock_project_manager.get_zone_data.return_value = None

        success = processing_coordinator.start_project_processing_workflow()

        assert success is False

    def test_start_project_processing_orchestrator_raises_exception(
        self,
        processing_coordinator,
        mock_video_orchestrator,
    ):
        """Test start_project_processing when orchestrator raises exception."""
        mock_video_orchestrator.start_project_processing_workflow.side_effect = RuntimeError(
            "Test error"
        )

        with pytest.raises(ProcessingCoordinatorError) as exc_info:
            processing_coordinator.start_project_processing_workflow()

        assert "Failed to start project processing" in str(exc_info.value)

    def test_start_project_processing_reverts_state_on_error(
        self,
        processing_coordinator,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test that start_project_processing reverts state on error."""
        mock_video_orchestrator.start_project_processing_workflow.side_effect = RuntimeError(
            "Test error"
        )

        with pytest.raises(ProcessingCoordinatorError):
            processing_coordinator.start_project_processing_workflow()

        # Should have been called twice: once to set True, once to revert to False
        assert mock_state_manager.update_state.call_count >= 2


# =============================================================================
# PENDING VIDEOS PROCESSING TESTS
# =============================================================================


class TestPendingVideosProcessing:
    """Test pending videos batch processing workflows."""

    def test_process_pending_videos_success(
        self,
        processing_coordinator,
        mock_video_orchestrator,
    ):
        """Test successful pending videos processing."""
        success = processing_coordinator.process_pending_project_videos()

        assert success is True
        mock_video_orchestrator.process_pending_project_videos.assert_called_once()

    def test_process_pending_videos_updates_state(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test that process_pending_videos updates StateManager."""
        processing_coordinator.process_pending_project_videos()

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["is_processing"] is True
        assert call_args[1]["processing_type"] == "pending_videos"

    def test_process_pending_videos_publishes_event(
        self,
        processing_coordinator,
        mock_event_bus,
    ):
        """Test that process_pending_videos publishes event."""
        processing_coordinator.process_pending_project_videos()

        mock_event_bus.publish_event.assert_called()
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "PENDING_VIDEOS_PROCESSING_STARTED" in calls

    def test_process_pending_videos_no_orchestrator(
        self,
        mock_state_manager,
        mock_project_manager,
    ):
        """Test process_pending_videos without VideoOrchestrator."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            video_orchestrator=None,
        )

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.process_pending_project_videos()

        assert "VideoOrchestrator is required" in str(exc_info.value)

    def test_process_pending_videos_no_project_manager(
        self,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test process_pending_videos without ProjectManager."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=None,
        )

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.process_pending_project_videos()

        assert "ProjectManager is required" in str(exc_info.value)

    def test_process_pending_videos_already_active(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test process_pending_videos when processing already active."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        success = processing_coordinator.process_pending_project_videos()

        assert success is False

    def test_process_pending_videos_orchestrator_raises_exception(
        self,
        processing_coordinator,
        mock_video_orchestrator,
    ):
        """Test process_pending_videos when orchestrator raises exception."""
        mock_video_orchestrator.process_pending_project_videos.side_effect = RuntimeError(
            "Test error"
        )

        with pytest.raises(ProcessingCoordinatorError) as exc_info:
            processing_coordinator.process_pending_project_videos()

        assert "Failed to process pending videos" in str(exc_info.value)

    def test_process_pending_videos_reverts_state_on_error(
        self,
        processing_coordinator,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test that process_pending_videos reverts state on error."""
        mock_video_orchestrator.process_pending_project_videos.side_effect = RuntimeError(
            "Test error"
        )

        with pytest.raises(ProcessingCoordinatorError):
            processing_coordinator.process_pending_project_videos()

        # Should revert state on error
        assert mock_state_manager.update_state.call_count >= 2


# =============================================================================
# SINGLE VIDEO PROCESSING TESTS
# =============================================================================


class TestSingleVideoProcessing:
    """Test single video processing workflows."""

    def test_start_single_video_success(
        self,
        processing_coordinator,
        tmp_path,
    ):
        """Test successful single video processing start."""
        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        success = processing_coordinator.start_single_video_processing(video_path=video_file)

        assert success is True

    def test_start_single_video_with_config(
        self,
        processing_coordinator,
        tmp_path,
    ):
        """Test single video processing with config."""
        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        config = {"analysis_interval_frames": 10}
        success = processing_coordinator.start_single_video_processing(
            video_path=video_file,
            config=config,
        )

        assert success is True

    def test_start_single_video_updates_state(
        self,
        processing_coordinator,
        mock_state_manager,
        tmp_path,
    ):
        """Test that start_single_video updates StateManager."""
        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        processing_coordinator.start_single_video_processing(video_path=video_file)

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["is_processing"] is True
        assert call_args[1]["processing_type"] == "single_video"
        assert str(video_file) in call_args[1]["current_video"]

    def test_start_single_video_publishes_event(
        self,
        processing_coordinator,
        mock_event_bus,
        tmp_path,
    ):
        """Test that start_single_video publishes event."""
        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        processing_coordinator.start_single_video_processing(video_path=video_file)

        mock_event_bus.publish_event.assert_called()
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "SINGLE_VIDEO_PROCESSING_STARTED" in calls

    def test_start_single_video_string_path(
        self,
        processing_coordinator,
        tmp_path,
    ):
        """Test single video processing with string path."""
        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        success = processing_coordinator.start_single_video_processing(video_path=str(video_file))

        assert success is True

    def test_start_single_video_file_not_exists(
        self,
        processing_coordinator,
    ):
        """Test start_single_video with non-existent file."""
        with pytest.raises(ValueError) as exc_info:
            processing_coordinator.start_single_video_processing(video_path="/nonexistent.mp4")

        assert "does not exist" in str(exc_info.value)

    def test_start_single_video_path_is_directory(
        self,
        processing_coordinator,
        tmp_path,
    ):
        """Test start_single_video with directory path."""
        with pytest.raises(ValueError) as exc_info:
            processing_coordinator.start_single_video_processing(video_path=tmp_path)

        assert "not a file" in str(exc_info.value)

    def test_start_single_video_no_processing_service(
        self,
        mock_state_manager,
        tmp_path,
    ):
        """Test start_single_video without VideoProcessingService."""
        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            video_processing_service=None,
        )

        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.start_single_video_processing(video_path=video_file)

        assert "VideoProcessingService is required" in str(exc_info.value)

    def test_start_single_video_already_active(
        self,
        processing_coordinator,
        mock_state_manager,
        tmp_path,
    ):
        """Test start_single_video when processing already active."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        video_file = tmp_path / "test_video.mp4"
        video_file.touch()

        success = processing_coordinator.start_single_video_processing(video_path=video_file)

        assert success is False


# =============================================================================
# CANCEL PROCESSING TESTS
# =============================================================================


class TestCancelProcessing:
    """Test processing cancellation."""

    def test_cancel_processing_success(
        self,
        processing_coordinator,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test successful processing cancellation."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        success = processing_coordinator.cancel_processing()

        assert success is True
        mock_video_orchestrator.cancel_current_analysis.assert_called_once()

    def test_cancel_processing_updates_state(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test that cancel_processing updates StateManager."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        processing_coordinator.cancel_processing()

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["is_processing"] is False
        assert call_args[1]["is_cancelled"] is True

    def test_cancel_processing_publishes_event(
        self,
        processing_coordinator,
        mock_state_manager,
        mock_event_bus,
    ):
        """Test that cancel_processing publishes event."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        processing_coordinator.cancel_processing()

        mock_event_bus.publish_event.assert_called()
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "PROCESSING_CANCELLED" in calls

    def test_cancel_processing_not_active(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test cancel_processing when processing is not active."""
        mock_state_manager.get_state.return_value = {"is_processing": False}

        success = processing_coordinator.cancel_processing()

        assert success is False

    def test_cancel_processing_without_orchestrator(
        self,
        mock_state_manager,
    ):
        """Test cancel_processing without VideoOrchestrator."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        coordinator = ProcessingCoordinator(
            state_manager=mock_state_manager,
            video_orchestrator=None,
        )

        success = coordinator.cancel_processing()

        # Should still succeed even without orchestrator
        assert success is True

    def test_cancel_processing_orchestrator_raises_exception(
        self,
        processing_coordinator,
        mock_state_manager,
        mock_video_orchestrator,
    ):
        """Test cancel_processing when orchestrator raises exception."""
        mock_state_manager.get_state.return_value = {"is_processing": True}
        mock_video_orchestrator.cancel_current_analysis.side_effect = RuntimeError("Test error")

        # Should still succeed despite orchestrator error
        success = processing_coordinator.cancel_processing()

        assert success is True


# =============================================================================
# PROCESSING STATE QUERY TESTS
# =============================================================================


class TestProcessingStateQueries:
    """Test processing state query methods."""

    def test_is_processing_active_returns_true(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test is_processing_active when processing is active."""
        mock_state_manager.get_state.return_value = {"is_processing": True}

        assert processing_coordinator.is_processing_active() is True

    def test_is_processing_active_returns_false(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test is_processing_active when processing is not active."""
        mock_state_manager.get_state.return_value = {"is_processing": False}

        assert processing_coordinator.is_processing_active() is False

    def test_get_processing_info_when_active(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test get_processing_info when processing is active."""
        mock_state_manager.get_state.return_value = {
            "is_processing": True,
            "processing_type": "single_video",
            "current_video": "/path/to/video.mp4",
            "is_cancelled": False,
            "start_time": "2025-01-13T12:00:00",
        }

        info = processing_coordinator.get_processing_info()

        assert info["is_processing"] is True
        assert info["processing_type"] == "single_video"
        assert info["current_video"] == "/path/to/video.mp4"
        assert info["is_cancelled"] is False
        assert info["start_time"] == "2025-01-13T12:00:00"

    def test_get_processing_info_when_not_active(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test get_processing_info when processing is not active."""
        mock_state_manager.get_state.return_value = {}

        info = processing_coordinator.get_processing_info()

        assert info["is_processing"] is False
        assert info["processing_type"] is None

    def test_repr_shows_processing_state(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test __repr__ shows processing state."""
        mock_state_manager.get_state.return_value = {
            "is_processing": True,
            "processing_type": "project_batch",
        }

        repr_str = repr(processing_coordinator)

        assert "ProcessingCoordinator" in repr_str
        assert "active=True" in repr_str
        assert "type=project_batch" in repr_str


# =============================================================================
# PROCESSING COMPLETION TESTS
# =============================================================================


class TestProcessingCompletion:
    """Test processing completion callback."""

    def test_on_processing_complete_success(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test on_processing_complete with success."""
        processing_coordinator.on_processing_complete(success=True)

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["is_processing"] is False
        assert call_args[1]["last_success"] is True

    def test_on_processing_complete_failure(
        self,
        processing_coordinator,
        mock_state_manager,
    ):
        """Test on_processing_complete with failure."""
        processing_coordinator.on_processing_complete(
            success=False,
            error_message="Test error",
        )

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["is_processing"] is False
        assert call_args[1]["last_success"] is False
        assert call_args[1]["last_error"] == "Test error"

    def test_on_processing_complete_publishes_success_event(
        self,
        processing_coordinator,
        mock_event_bus,
    ):
        """Test on_processing_complete publishes success event."""
        processing_coordinator.on_processing_complete(success=True)

        mock_event_bus.publish_event.assert_called()
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "PROCESSING_COMPLETED" in calls

    def test_on_processing_complete_publishes_failure_event(
        self,
        processing_coordinator,
        mock_event_bus,
    ):
        """Test on_processing_complete publishes failure event."""
        processing_coordinator.on_processing_complete(success=False)

        mock_event_bus.publish_event.assert_called()
        calls = [call[0][0] for call in mock_event_bus.publish_event.call_args_list]
        assert "PROCESSING_FAILED" in calls


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestProcessingCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_project_processing_workflow(
        self,
        mock_video_orchestrator,
        mock_project_manager,
        mock_event_bus,
    ):
        """Test complete project processing workflow."""
        # Use real StateManager
        state_manager = StateManager()

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
            event_bus=mock_event_bus,
        )

        # Start processing
        success = coordinator.start_project_processing_workflow()
        assert success is True

        # Check state
        assert coordinator.is_processing_active() is True
        info = coordinator.get_processing_info()
        assert info["processing_type"] == "project_batch"

        # Complete processing
        coordinator.on_processing_complete(success=True)

        # Check state updated
        assert coordinator.is_processing_active() is False
        info = coordinator.get_processing_info()
        assert info["last_success"] is True

    def test_state_history_tracks_changes(
        self,
        mock_video_orchestrator,
        mock_project_manager,
        tmp_path,
    ):
        """Test that StateManager tracks processing state changes."""
        state_manager = StateManager(enable_history=True)

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
            video_processing_service=MagicMock(),
        )

        # Perform multiple operations
        coordinator.start_project_processing_workflow()

        video_file = tmp_path / "test.mp4"
        video_file.touch()

        coordinator.on_processing_complete(success=True)

        # Check history
        history = state_manager.get_history(StateCategory.PROCESSING)
        assert len(history) >= 2  # At least 2 state changes

    def test_error_recovery_on_workflow_failure(
        self,
        mock_video_orchestrator,
        mock_project_manager,
    ):
        """Test error recovery when workflow fails."""
        state_manager = StateManager()
        mock_video_orchestrator.start_project_processing_workflow.side_effect = RuntimeError(
            "Workflow failed"
        )

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
        )

        # Attempt workflow (should fail)
        with pytest.raises(ProcessingCoordinatorError):
            coordinator.start_project_processing_workflow()

        # Verify processing is not active
        assert coordinator.is_processing_active() is False

    def test_multiple_workflow_attempts(
        self,
        mock_video_orchestrator,
        mock_project_manager,
    ):
        """Test multiple sequential workflow attempts."""
        state_manager = StateManager()

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
        )

        # First workflow
        coordinator.start_project_processing_workflow()
        coordinator.on_processing_complete(success=True)

        # Second workflow
        coordinator.process_pending_project_videos()
        coordinator.on_processing_complete(success=True)

        # Verify both completed
        assert mock_video_orchestrator.start_project_processing_workflow.call_count == 1
        assert mock_video_orchestrator.process_pending_project_videos.call_count == 1

    def test_cancel_during_processing(
        self,
        mock_video_orchestrator,
        mock_project_manager,
    ):
        """Test cancelling during active processing."""
        state_manager = StateManager()

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
        )

        # Start processing
        coordinator.start_project_processing_workflow()
        assert coordinator.is_processing_active() is True

        # Cancel
        success = coordinator.cancel_processing()
        assert success is True
        assert coordinator.is_processing_active() is False

    def test_zone_validation_workflow(
        self,
        mock_video_orchestrator,
        mock_project_manager,
        mock_event_bus,
    ):
        """Test zone validation during workflow start."""
        state_manager = StateManager()

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
            event_bus=mock_event_bus,
        )

        # Zones defined - should succeed
        success = coordinator.start_project_processing_workflow(validate_zones=True)
        assert success is True

        # Complete and reset
        coordinator.on_processing_complete(success=True)

        # No zones - should fail
        mock_project_manager.get_zone_data.return_value = None
        success = coordinator.start_project_processing_workflow(validate_zones=True)
        assert success is False

    def test_processing_without_event_bus(
        self,
        mock_video_orchestrator,
        mock_project_manager,
    ):
        """Test processing works without EventBus."""
        state_manager = StateManager()

        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
            event_bus=None,
        )

        # Should work without EventBus
        success = coordinator.start_project_processing_workflow()
        assert success is True

    def test_parallel_coordinator_instances(
        self,
        mock_video_orchestrator,
        mock_project_manager,
    ):
        """Test that multiple coordinators can share StateManager."""
        state_manager = StateManager()

        coordinator1 = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=mock_video_orchestrator,
            project_manager=mock_project_manager,
        )

        coordinator2 = ProcessingCoordinator(
            state_manager=state_manager,
            video_orchestrator=MagicMock(),
            project_manager=mock_project_manager,
        )

        # Start with coordinator1
        coordinator1.start_project_processing_workflow()

        # Both coordinators should see the same state
        assert coordinator1.is_processing_active() is True
        assert coordinator2.is_processing_active() is True
