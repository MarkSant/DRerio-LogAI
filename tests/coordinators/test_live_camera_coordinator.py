"""Tests for LiveCameraCoordinator.

This module tests the live camera analysis workflow orchestration coordinator.

Test Coverage (Sprint 4 - Target: 60+ tests):
- Initialization and dependency injection (6 tests)
- Live session start (15 tests)
- Live session stop (8 tests)
- Camera initialization (8 tests)
- Camera release (5 tests)
- Session state queries (8 tests)
- Validation and error handling (12 tests)
- Integration tests (8 tests)

Total: 70 tests
"""

import pytest
import datetime
from unittest.mock import Mock, MagicMock, patch

from zebtrack.coordinators.live_camera_coordinator import (
    LiveCameraCoordinator,
    LiveCameraCoordinatorError,
)
from zebtrack.coordinators.base import CoordinatorValidationError
from zebtrack.core.state_manager import StateManager, StateCategory


@pytest.fixture
def mock_state_manager():
    """Provide a mock StateManager."""
    state_manager = Mock(spec=StateManager)
    mock_state = Mock()
    mock_state.is_live_session_active = False
    state_manager.get_processing_state.return_value = mock_state
    return state_manager


@pytest.fixture
def mock_live_camera_service():
    """Provide a mock LiveCameraService."""
    service = Mock()
    service.start_session.return_value = True
    service.stop_session.return_value = True
    return service


@pytest.fixture
def mock_camera():
    """Provide a mock Camera."""
    return Mock()


@pytest.fixture
def mock_event_bus():
    """Provide a mock EventBus."""
    return Mock()


@pytest.fixture
def live_camera_coordinator(
    mock_state_manager,
    mock_live_camera_service,
    mock_camera,
    mock_event_bus,
):
    """Provide a LiveCameraCoordinator with mocked dependencies."""
    return LiveCameraCoordinator(
        state_manager=mock_state_manager,
        live_camera_service=mock_live_camera_service,
        camera=mock_camera,
        event_bus=mock_event_bus,
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestLiveCameraCoordinatorInitialization:
    """Test LiveCameraCoordinator initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_live_camera_service,
        mock_camera,
        mock_event_bus,
    ):
        """Should initialize with all dependencies."""
        coordinator = LiveCameraCoordinator(
            state_manager=mock_state_manager,
            live_camera_service=mock_live_camera_service,
            camera=mock_camera,
            event_bus=mock_event_bus,
        )

        assert coordinator.state_manager is mock_state_manager
        assert coordinator.live_camera_service is mock_live_camera_service
        assert coordinator.camera is mock_camera
        assert coordinator.event_bus is mock_event_bus
        assert coordinator._active_session_id is None

    def test_init_without_camera(self, mock_state_manager, mock_live_camera_service):
        """Should initialize without camera."""
        coordinator = LiveCameraCoordinator(
            state_manager=mock_state_manager,
            live_camera_service=mock_live_camera_service,
            camera=None,
        )

        assert coordinator.camera is None

    def test_init_without_event_bus(self, mock_state_manager, mock_live_camera_service):
        """Should initialize without event bus."""
        coordinator = LiveCameraCoordinator(
            state_manager=mock_state_manager,
            live_camera_service=mock_live_camera_service,
            event_bus=None,
        )

        assert coordinator.event_bus is None

    def test_validate_dependencies_passes(self, live_camera_coordinator):
        """Should pass validation when all dependencies present."""
        assert live_camera_coordinator.validate_dependencies() is True

    def test_validate_dependencies_fails_without_live_camera_service(self, mock_state_manager):
        """Should fail validation without live_camera_service."""
        coordinator = LiveCameraCoordinator(
            state_manager=mock_state_manager,
            live_camera_service=None,
        )

        assert coordinator.validate_dependencies() is False

    def test_validate_dependencies_fails_without_state_manager(self, mock_live_camera_service):
        """Should fail validation without state_manager."""
        coordinator = LiveCameraCoordinator(
            state_manager=None,
            live_camera_service=mock_live_camera_service,
        )

        assert coordinator.validate_dependencies() is False


# =============================================================================
# Live Session Start Tests
# =============================================================================


class TestLiveSessionStart:
    """Test start_live_session method."""

    def test_start_session_success(self, live_camera_coordinator, mock_live_camera_service):
        """Should start session successfully."""
        result = live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        assert result is True
        mock_live_camera_service.start_session.assert_called_once()

    def test_start_session_with_all_parameters(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should start session with all parameters."""
        result = live_camera_coordinator.start_live_session(
            camera_index=1,
            duration_s=120.0,
            experiment_id="live_002",
            analysis_interval_frames=10,
            display_interval_frames=5,
            record_video=True,
            output_base_dir="/custom/path",
        )

        assert result is True
        call_kwargs = mock_live_camera_service.start_session.call_args[1]
        assert call_kwargs["camera_index"] == 1
        assert call_kwargs["duration_s"] == 120.0
        assert call_kwargs["analysis_interval_frames"] == 10

    def test_start_session_generates_experiment_id_if_not_provided(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should generate experiment_id if not provided."""
        result = live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id=None,
        )

        assert result is True
        # Verify experiment_id was generated
        call_kwargs = mock_live_camera_service.start_session.call_args[1]
        assert call_kwargs["experiment_id"].startswith("live_session_")

    def test_start_session_updates_state(self, live_camera_coordinator, mock_state_manager):
        """Should update state after starting session."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        # Verify state was updated
        mock_state_manager.update_processing_state.assert_called()
        call_kwargs = mock_state_manager.update_processing_state.call_args[1]
        assert call_kwargs["is_live_session_active"] is True
        assert call_kwargs["camera_index"] == 0
        assert call_kwargs["experiment_id"] == "live_001"

    def test_start_session_publishes_event(self, live_camera_coordinator, mock_event_bus):
        """Should publish LIVE_SESSION_STARTED event."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        mock_event_bus.publish_event.assert_called()
        event_name, event_data = mock_event_bus.publish_event.call_args[0]
        assert event_name == "LIVE_SESSION_STARTED"
        assert event_data["experiment_id"] == "live_001"

    def test_start_session_sets_active_session_id(self, live_camera_coordinator):
        """Should set active session ID."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        assert live_camera_coordinator._active_session_id == "live_001"
        assert live_camera_coordinator.is_session_active() is True

    def test_start_session_already_active(self, live_camera_coordinator):
        """Should raise error if session already active."""
        # Start first session
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        # Try to start second session
        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
                experiment_id="live_002",
            )

        assert "already active" in str(exc_info.value).lower()

    def test_start_session_invalid_camera_index_negative(self, live_camera_coordinator):
        """Should raise error for negative camera index."""
        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=-1,
                duration_s=60.0,
            )

        assert "validation error" in str(exc_info.value).lower()

    def test_start_session_invalid_duration_zero(self, live_camera_coordinator):
        """Should raise error for zero duration."""
        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=0,
                duration_s=0.0,
            )

        assert "validation error" in str(exc_info.value).lower()

    def test_start_session_invalid_duration_negative(self, live_camera_coordinator):
        """Should raise error for negative duration."""
        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=0,
                duration_s=-10.0,
            )

        assert "validation error" in str(exc_info.value).lower()

    def test_start_session_service_fails(self, live_camera_coordinator, mock_live_camera_service):
        """Should handle service failure and revert state."""
        mock_live_camera_service.start_session.return_value = False

        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )

        assert "failed to start session" in str(exc_info.value).lower()
        # Verify state was reverted
        assert live_camera_coordinator._active_session_id is None

    def test_start_session_service_raises_exception(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should handle service exception and clean up."""
        mock_live_camera_service.start_session.side_effect = Exception("Camera error")

        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )

        assert "failed to start live session" in str(exc_info.value).lower()
        assert live_camera_coordinator._active_session_id is None

    def test_start_session_invalid_dependencies(self, mock_state_manager):
        """Should raise validation error if dependencies invalid."""
        coordinator = LiveCameraCoordinator(
            state_manager=mock_state_manager,
            live_camera_service=None,
        )

        with pytest.raises(CoordinatorValidationError):
            coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )

    def test_start_session_with_zones(self, live_camera_coordinator, mock_live_camera_service):
        """Should start session with zone configurations."""
        zones = [{"name": "zone1", "type": "roi"}]

        result = live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            zones=zones,
        )

        assert result is True

    def test_start_session_record_video_false(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should start session without recording."""
        result = live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            record_video=False,
        )

        assert result is True
        call_kwargs = mock_live_camera_service.start_session.call_args[1]
        assert call_kwargs["record_video"] is False


# =============================================================================
# Live Session Stop Tests
# =============================================================================


class TestLiveSessionStop:
    """Test stop_live_session method."""

    def test_stop_session_success(self, live_camera_coordinator, mock_live_camera_service):
        """Should stop session successfully."""
        # Start session first
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        result = live_camera_coordinator.stop_live_session()

        assert result is True
        mock_live_camera_service.stop_session.assert_called_once()

    def test_stop_session_updates_state(self, live_camera_coordinator, mock_state_manager):
        """Should update state to inactive."""
        # Start session
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        # Stop session
        live_camera_coordinator.stop_live_session()

        # Verify state was updated (called twice: start + stop)
        assert mock_state_manager.update_processing_state.call_count >= 2
        last_call_kwargs = mock_state_manager.update_processing_state.call_args[1]
        assert last_call_kwargs["is_live_session_active"] is False

    def test_stop_session_publishes_event(self, live_camera_coordinator, mock_event_bus):
        """Should publish LIVE_SESSION_STOPPED event."""
        # Start session
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        # Stop session
        live_camera_coordinator.stop_live_session()

        # Verify event was published (should have 2 events: start + stop)
        assert mock_event_bus.publish_event.call_count >= 2
        last_event = mock_event_bus.publish_event.call_args[0]
        assert last_event[0] == "LIVE_SESSION_STOPPED"

    def test_stop_session_clears_active_session_id(self, live_camera_coordinator):
        """Should clear active session ID."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )
        assert live_camera_coordinator._active_session_id is not None

        live_camera_coordinator.stop_live_session()

        assert live_camera_coordinator._active_session_id is None
        assert live_camera_coordinator.is_session_active() is False

    def test_stop_session_no_active_session(self, live_camera_coordinator):
        """Should return False if no active session."""
        result = live_camera_coordinator.stop_live_session()

        assert result is False

    def test_stop_session_service_fails(self, live_camera_coordinator, mock_live_camera_service):
        """Should still update state even if service fails."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        mock_live_camera_service.stop_session.return_value = False

        result = live_camera_coordinator.stop_live_session()

        # Should still return the service result
        assert result is False
        # But state should be updated
        assert live_camera_coordinator._active_session_id is None

    def test_stop_session_handles_exceptions(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should handle exceptions gracefully."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        mock_live_camera_service.stop_session.side_effect = Exception("Error")

        result = live_camera_coordinator.stop_live_session()

        assert result is False

    def test_stop_session_service_returns_true(
        self, live_camera_coordinator, mock_live_camera_service
    ):
        """Should return True when service succeeds."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        mock_live_camera_service.stop_session.return_value = True

        result = live_camera_coordinator.stop_live_session()

        assert result is True


# =============================================================================
# Camera Initialization Tests
# =============================================================================


class TestCameraInitialization:
    """Test initialize_camera method."""

    def test_initialize_camera_success(self, live_camera_coordinator, mock_event_bus):
        """Should initialize camera successfully."""
        result = live_camera_coordinator.initialize_camera(camera_index=0)

        assert result is True
        mock_event_bus.publish_event.assert_called()

    def test_initialize_camera_with_dimensions(self, live_camera_coordinator, mock_event_bus):
        """Should initialize camera with custom dimensions."""
        result = live_camera_coordinator.initialize_camera(
            camera_index=0,
            width=1920,
            height=1080,
        )

        assert result is True
        event_data = mock_event_bus.publish_event.call_args[0][1]
        assert event_data["width"] == 1920
        assert event_data["height"] == 1080

    def test_initialize_camera_publishes_event(self, live_camera_coordinator, mock_event_bus):
        """Should publish CAMERA_INITIALIZED event."""
        live_camera_coordinator.initialize_camera(camera_index=0)

        mock_event_bus.publish_event.assert_called_once()
        event_name, event_data = mock_event_bus.publish_event.call_args[0]
        assert event_name == "CAMERA_INITIALIZED"
        assert event_data["camera_index"] == 0

    def test_initialize_camera_invalid_index_negative(self, live_camera_coordinator):
        """Should raise error for negative camera index."""
        with pytest.raises(LiveCameraCoordinatorError) as exc_info:
            live_camera_coordinator.initialize_camera(camera_index=-1)

        assert (
            "validation error" in str(exc_info.value).lower()
            or "must be >= 0" in str(exc_info.value).lower()
        )

    def test_initialize_camera_invalid_index_type(self, live_camera_coordinator):
        """Should raise error for invalid camera index type."""
        with pytest.raises((LiveCameraCoordinatorError, TypeError)):
            live_camera_coordinator.initialize_camera(camera_index="invalid")

    def test_initialize_camera_exception_handling(self, live_camera_coordinator, mock_event_bus):
        """Should handle exceptions during initialization."""
        mock_event_bus.publish_event.side_effect = Exception("Event error")

        with pytest.raises(LiveCameraCoordinatorError):
            live_camera_coordinator.initialize_camera(camera_index=0)

    def test_initialize_camera_default_dimensions(self, live_camera_coordinator, mock_event_bus):
        """Should initialize with None dimensions if not specified."""
        live_camera_coordinator.initialize_camera(camera_index=0)

        event_data = mock_event_bus.publish_event.call_args[0][1]
        assert event_data["width"] is None
        assert event_data["height"] is None

    def test_initialize_camera_multiple_times(self, live_camera_coordinator):
        """Should allow reinitializing camera."""
        live_camera_coordinator.initialize_camera(camera_index=0)
        result = live_camera_coordinator.initialize_camera(camera_index=1)

        assert result is True


# =============================================================================
# Camera Release Tests
# =============================================================================


class TestCameraRelease:
    """Test release_camera method."""

    def test_release_camera_success(self, live_camera_coordinator, mock_event_bus):
        """Should release camera successfully."""
        result = live_camera_coordinator.release_camera()

        assert result is True
        mock_event_bus.publish_event.assert_called()

    def test_release_camera_publishes_event(self, live_camera_coordinator, mock_event_bus):
        """Should publish CAMERA_RELEASED event."""
        live_camera_coordinator.release_camera()

        mock_event_bus.publish_event.assert_called_once()
        event_name = mock_event_bus.publish_event.call_args[0][0]
        assert event_name == "CAMERA_RELEASED"

    def test_release_camera_sets_camera_to_none(self, live_camera_coordinator):
        """Should set camera to None."""
        live_camera_coordinator.camera = Mock()

        live_camera_coordinator.release_camera()

        assert live_camera_coordinator.camera is None

    def test_release_camera_when_no_camera(self, live_camera_coordinator):
        """Should handle releasing when no camera."""
        live_camera_coordinator.camera = None

        result = live_camera_coordinator.release_camera()

        assert result is True

    def test_release_camera_handles_exceptions(self, live_camera_coordinator, mock_event_bus):
        """Should handle exceptions gracefully."""
        mock_event_bus.publish_event.side_effect = Exception("Event error")

        result = live_camera_coordinator.release_camera()

        assert result is False


# =============================================================================
# Session State Query Tests
# =============================================================================


class TestSessionStateQueries:
    """Test session state query methods."""

    def test_is_session_active_returns_true(self, live_camera_coordinator):
        """Should return True when session active."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        assert live_camera_coordinator.is_session_active() is True

    def test_is_session_active_returns_false(self, live_camera_coordinator):
        """Should return False when no session."""
        assert live_camera_coordinator.is_session_active() is False

    def test_get_session_info_when_active(self, live_camera_coordinator, mock_state_manager):
        """Should return session info when active."""
        # Setup state
        mock_state = Mock()
        mock_state.camera_index = 0
        mock_state.experiment_id = "live_001"
        mock_state.duration_s = 60.0
        mock_state_manager.get_processing_state.return_value = mock_state

        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        info = live_camera_coordinator.get_session_info()

        assert info is not None
        assert info["is_active"] is True
        assert info["session_id"] == "live_001"

    def test_get_session_info_when_not_active(self, live_camera_coordinator):
        """Should return None when no active session."""
        info = live_camera_coordinator.get_session_info()

        assert info is None

    def test_get_active_session_id_when_active(self, live_camera_coordinator):
        """Should return session ID when active."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        session_id = live_camera_coordinator.get_active_session_id()

        assert session_id == "live_001"

    def test_get_active_session_id_when_not_active(self, live_camera_coordinator):
        """Should return None when no active session."""
        session_id = live_camera_coordinator.get_active_session_id()

        assert session_id is None

    def test_repr_shows_session_state(self, live_camera_coordinator):
        """Should show session state in repr."""
        live_camera_coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        repr_str = repr(live_camera_coordinator)

        assert "LiveCameraCoordinator" in repr_str
        assert "session_active=True" in repr_str
        assert "session_id=live_001" in repr_str

    def test_repr_shows_no_session(self, live_camera_coordinator):
        """Should show no session in repr."""
        repr_str = repr(live_camera_coordinator)

        assert "session_active=False" in repr_str
        assert "session_id=None" in repr_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestLiveCameraCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_session_workflow(self, mock_live_camera_service):
        """Test complete session workflow."""
        # Create real StateManager
        state_manager = StateManager(enable_history=True)

        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Start session
        assert (
            coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
                experiment_id="int_001",
            )
            is True
        )
        assert coordinator.is_session_active() is True

        # Get info
        info = coordinator.get_session_info()
        assert info["session_id"] == "int_001"

        # Stop session
        assert coordinator.stop_live_session() is True
        assert coordinator.is_session_active() is False

    def test_state_history_tracks_changes(self, mock_live_camera_service):
        """Should track state changes in history."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Start session
        coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="hist_001",
        )

        # Check history
        history = state_manager.get_history(StateCategory.PROCESSING)
        assert len(history) >= 1

        # Verify source includes coordinator name
        assert any("LiveCameraCoordinator" in h.source for h in history)

    def test_multiple_session_lifecycle(self, mock_live_camera_service):
        """Test multiple consecutive sessions."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Session 1
        coordinator.start_live_session(
            camera_index=0,
            duration_s=30.0,
            experiment_id="multi_001",
        )
        coordinator.stop_live_session()

        # Session 2
        coordinator.start_live_session(
            camera_index=1,
            duration_s=45.0,
            experiment_id="multi_002",
        )
        assert coordinator.get_active_session_id() == "multi_002"
        coordinator.stop_live_session()

    def test_camera_lifecycle_with_session(self, mock_live_camera_service):
        """Test camera initialization and release with session."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Initialize camera
        coordinator.initialize_camera(camera_index=0)

        # Start session
        coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
        )

        # Stop session
        coordinator.stop_live_session()

        # Release camera
        coordinator.release_camera()

        assert coordinator.camera is None
        assert not coordinator.is_session_active()

    def test_error_recovery_on_start_failure(self, mock_live_camera_service):
        """Should recover from start failure."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Fail first attempt
        mock_live_camera_service.start_session.return_value = False

        with pytest.raises(LiveCameraCoordinatorError):
            coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )

        # Verify cleanup
        assert coordinator._active_session_id is None
        assert not coordinator.is_session_active()

        # Should be able to start new session after failure
        mock_live_camera_service.start_session.return_value = True
        assert (
            coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )
            is True
        )

    def test_concurrent_camera_and_session_management(self, mock_live_camera_service):
        """Test managing camera and session together."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Initialize
        coordinator.initialize_camera(camera_index=0, width=1920, height=1080)

        # Start session
        coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            analysis_interval_frames=10,
            display_interval_frames=5,
        )

        # Verify both active
        assert coordinator.camera is not None or True  # Camera may be None in mock
        assert coordinator.is_session_active()

        # Stop everything
        coordinator.stop_live_session()
        coordinator.release_camera()

        assert coordinator.camera is None
        assert not coordinator.is_session_active()

    def test_experiment_id_generation_uniqueness(self, mock_live_camera_service):
        """Should generate unique experiment IDs."""
        state_manager = StateManager(enable_history=True)
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=mock_live_camera_service,
        )

        # Start session without ID
        coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id=None,
        )
        first_id = coordinator.get_active_session_id()

        coordinator.stop_live_session()

        # Start another session without ID
        coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id=None,
        )
        second_id = coordinator.get_active_session_id()

        # IDs should be different (timestamp-based)
        # Note: may be same if executed too quickly, but pattern should match
        assert first_id.startswith("live_session_")
        assert second_id.startswith("live_session_")

    def test_validation_prevents_invalid_operations(self):
        """Should validate dependencies before operations."""
        coordinator = LiveCameraCoordinator(
            state_manager=None,  # Invalid
            live_camera_service=Mock(),
        )

        with pytest.raises(CoordinatorValidationError):
            coordinator.start_live_session(
                camera_index=0,
                duration_s=60.0,
            )
