"""Tests for RecordingCoordinator.

This module tests the recording workflow orchestration coordinator.

Test Coverage (Sprint 4 - Target: 40 tests):
- Initialization and dependency injection (4 tests)
- Recording start (8 tests)
- Recording stop (5 tests)
- Arduino triggers (6 tests)
- Recording state queries (5 tests)
- Error handling (7 tests)
- Integration tests (5 tests)

Total: 40 tests
"""

from typing import Any, cast
from unittest.mock import Mock

import pytest

from zebtrack.coordinators.base import CoordinatorValidationError
from zebtrack.coordinators.recording_coordinator import (
    RecordingCoordinator,
    RecordingCoordinatorError,
)
from zebtrack.core.state_manager import StateCategory, StateManager


@pytest.fixture
def mock_state_manager():
    """Provide a mock StateManager."""
    state_manager = Mock(spec=StateManager)
    mock_state = Mock()
    mock_state.is_recording = False
    state_manager.get_recording_state.return_value = mock_state
    return state_manager


@pytest.fixture
def mock_recording_service():
    """Provide a mock RecordingService."""
    return Mock()


@pytest.fixture
def mock_arduino_manager():
    """Provide a mock ArduinoManager."""
    return Mock()


@pytest.fixture
def mock_event_bus():
    """Provide a mock EventBus."""
    return Mock()


@pytest.fixture
def recording_coordinator(
    mock_state_manager,
    mock_recording_service,
    mock_arduino_manager,
    mock_event_bus,
):
    """Provide a RecordingCoordinator with mocked dependencies."""
    return RecordingCoordinator(
        state_manager=mock_state_manager,
        recording_service=mock_recording_service,
        arduino_manager=mock_arduino_manager,
        event_bus=mock_event_bus,
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestRecordingCoordinatorInitialization:
    """Test RecordingCoordinator initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_recording_service,
        mock_arduino_manager,
        mock_event_bus,
    ):
        """Should initialize with all dependencies."""
        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=mock_recording_service,
            arduino_manager=mock_arduino_manager,
            event_bus=mock_event_bus,
        )

        assert coordinator.state_manager is mock_state_manager
        assert coordinator.recording_service is mock_recording_service
        assert coordinator.arduino_manager is mock_arduino_manager
        assert coordinator.event_bus is mock_event_bus

    def test_init_without_arduino(self, mock_state_manager, mock_recording_service):
        """Should initialize without Arduino."""
        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=mock_recording_service,
            arduino_manager=None,
        )

        assert coordinator.arduino_manager is None

    def test_validate_dependencies_passes(self, recording_coordinator):
        """Should pass validation when all dependencies present."""
        assert recording_coordinator.validate_dependencies() is True

    def test_validate_dependencies_fails_without_recording_service(self, mock_state_manager):
        """Should fail validation without recording_service."""
        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=cast(Any, None),
        )

        assert coordinator.validate_dependencies() is False


# =============================================================================
# Recording Start Tests
# =============================================================================


class TestRecordingStart:
    """Test start_recording method."""

    def test_start_recording_success(self, recording_coordinator, mock_state_manager):
        """Should start recording successfully."""
        result = recording_coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="exp_001",
        )

        assert result is True
        mock_state_manager.update_recording_state.assert_called()

    def test_start_recording_with_duration(self, recording_coordinator, mock_state_manager):
        """Should start recording with duration."""
        result = recording_coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="exp_001",
            duration=60,
        )

        assert result is True
        # Verify duration was passed to state update
        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["duration"] == 60

    def test_start_recording_updates_state(self, recording_coordinator, mock_state_manager):
        """Should update state after starting recording."""
        recording_coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="exp_001",
        )

        # Verify state was updated
        mock_state_manager.update_recording_state.assert_called()
        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["is_recording"] is True
        assert call_kwargs["output_path"] == "/path/to/output"
        assert call_kwargs["experiment_id"] == "exp_001"

    def test_start_recording_publishes_event(self, recording_coordinator, mock_event_bus):
        """Should publish RECORDING_STARTED event."""
        from zebtrack.ui.events import Events

        recording_coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="exp_001",
        )

        mock_event_bus.publish_event.assert_called_once()
        event_name, event_data = mock_event_bus.publish_event.call_args[0]
        assert event_name == Events.RECORDING_STARTED
        assert event_data["output_path"] == "/path/to/output"

    def test_start_recording_already_recording(self, recording_coordinator, mock_state_manager):
        """Should raise error if already recording."""
        # Setup state as already recording
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        with pytest.raises(RecordingCoordinatorError) as exc_info:
            recording_coordinator.start_recording(
                output_path="/path/to/output",
                experiment_id="exp_001",
            )

        assert "already in progress" in str(exc_info.value).lower()

    def test_start_recording_none_output_path(self, recording_coordinator):
        """Should raise error if output_path is None."""
        with pytest.raises(ValueError):
            recording_coordinator.start_recording(
                output_path=None,
                experiment_id="exp_001",
            )

    def test_start_recording_none_experiment_id(self, recording_coordinator):
        """Should raise error if experiment_id is None."""
        with pytest.raises(ValueError):
            recording_coordinator.start_recording(
                output_path="/path/to/output",
                experiment_id=None,
            )

    def test_start_recording_invalid_dependencies(self, mock_state_manager):
        """Should raise validation error if dependencies invalid."""
        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=cast(Any, None),  # Missing
        )

        with pytest.raises(CoordinatorValidationError):
            coordinator.start_recording(
                output_path="/path/to/output",
                experiment_id="exp_001",
            )


# =============================================================================
# Recording Stop Tests
# =============================================================================


class TestRecordingStop:
    """Test stop_recording method."""

    def test_stop_recording_success(self, recording_coordinator, mock_state_manager):
        """Should stop recording successfully."""
        # Setup state as recording
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        result = recording_coordinator.stop_recording()

        assert result is True
        mock_state_manager.update_recording_state.assert_called()

    def test_stop_recording_updates_state(self, recording_coordinator, mock_state_manager):
        """Should update state to not recording."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        recording_coordinator.stop_recording()

        # Verify state was updated
        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["is_recording"] is False

    def test_stop_recording_publishes_event(
        self, recording_coordinator, mock_event_bus, mock_state_manager
    ):
        """Should publish RECORDING_STOPPED event."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        recording_coordinator.stop_recording()

        mock_event_bus.publish_event.assert_called_once()
        event_name = mock_event_bus.publish_event.call_args[0][0]
        assert event_name == "RECORDING_STOPPED"

    def test_stop_recording_not_recording(self, recording_coordinator, mock_state_manager):
        """Should return False if not recording."""
        # State already not recording
        mock_state = Mock()
        mock_state.is_recording = False
        mock_state_manager.get_recording_state.return_value = mock_state

        result = recording_coordinator.stop_recording()

        assert result is False

    def test_stop_recording_handles_errors_gracefully(
        self, recording_coordinator, mock_state_manager
    ):
        """Should not raise exception on error."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state
        mock_state_manager.update_recording_state.side_effect = Exception("Error")

        # Should return False but not raise
        result = recording_coordinator.stop_recording()

        assert result is False


# =============================================================================
# Arduino Trigger Tests
# =============================================================================


class TestArduinoTrigger:
    """Test trigger_recording method."""

    def test_trigger_recording_enter(self, recording_coordinator, mock_event_bus):
        """Should trigger recording on zone enter."""
        result = recording_coordinator.trigger_recording(
            zone_name="zone1",
            trigger_type="enter",
        )

        assert result is True
        mock_event_bus.publish_event.assert_called_once()

    def test_trigger_recording_exit(self, recording_coordinator, mock_event_bus):
        """Should trigger recording on zone exit."""
        result = recording_coordinator.trigger_recording(
            zone_name="zone1",
            trigger_type="exit",
        )

        assert result is True

    def test_trigger_recording_without_arduino(self, mock_state_manager, mock_recording_service):
        """Should return False if no Arduino manager."""
        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=mock_recording_service,
            arduino_manager=None,
        )

        result = coordinator.trigger_recording(zone_name="zone1")

        assert result is False

    def test_trigger_recording_unknown_type(self, recording_coordinator):
        """Should return False for unknown trigger type."""
        result = recording_coordinator.trigger_recording(
            zone_name="zone1",
            trigger_type="unknown",
        )

        assert result is False

    def test_trigger_recording_publishes_event(self, recording_coordinator, mock_event_bus):
        """Should publish RECORDING_TRIGGERED event."""
        recording_coordinator.trigger_recording(
            zone_name="zone1",
            trigger_type="enter",
        )

        mock_event_bus.publish_event.assert_called_once()
        event_name, event_data = mock_event_bus.publish_event.call_args[0]
        assert event_name == "RECORDING_TRIGGERED"
        assert event_data["zone_name"] == "zone1"
        assert event_data["trigger_type"] == "enter"

    def test_trigger_recording_handles_errors(self, recording_coordinator, mock_event_bus):
        """Should handle errors gracefully."""
        mock_event_bus.publish_event.side_effect = Exception("Error")

        result = recording_coordinator.trigger_recording(zone_name="zone1")

        assert result is False


# =============================================================================
# Recording State Query Tests
# =============================================================================


class TestRecordingStateQueries:
    """Test recording state query methods."""

    def test_is_recording_returns_true(self, recording_coordinator, mock_state_manager):
        """Should return True when recording."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        assert recording_coordinator.is_recording() is True

    def test_is_recording_returns_false(self, recording_coordinator, mock_state_manager):
        """Should return False when not recording."""
        mock_state = Mock()
        mock_state.is_recording = False
        mock_state_manager.get_recording_state.return_value = mock_state

        assert recording_coordinator.is_recording() is False

    def test_get_recording_info_when_recording(self, recording_coordinator, mock_state_manager):
        """Should return recording info when recording."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state.output_path = "/path/to/output"
        mock_state.experiment_id = "exp_001"
        mock_state.duration = 60
        mock_state_manager.get_recording_state.return_value = mock_state

        info = recording_coordinator.get_recording_info()

        assert info is not None
        assert info["is_recording"] is True
        assert info["output_path"] == "/path/to/output"
        assert info["experiment_id"] == "exp_001"
        assert info["duration"] == 60

    def test_get_recording_info_when_not_recording(self, recording_coordinator, mock_state_manager):
        """Should return None when not recording."""
        mock_state = Mock()
        mock_state.is_recording = False
        mock_state_manager.get_recording_state.return_value = mock_state

        info = recording_coordinator.get_recording_info()

        assert info is None

    def test_repr_shows_recording_state(self, recording_coordinator, mock_state_manager):
        """Should show recording state in repr."""
        mock_state = Mock()
        mock_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = mock_state

        repr_str = repr(recording_coordinator)

        assert "RecordingCoordinator" in repr_str
        assert "is_recording=True" in repr_str
        assert "has_arduino=True" in repr_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestRecordingCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_recording_workflow(self, mock_recording_service, mock_arduino_manager):
        """Test complete recording workflow."""
        # Create real StateManager
        state_manager = StateManager(enable_history=True)

        coordinator = RecordingCoordinator(
            state_manager=state_manager,
            recording_service=mock_recording_service,
            arduino_manager=mock_arduino_manager,
        )

        # Start recording
        assert (
            coordinator.start_recording(
                output_path="/path/to/output",
                experiment_id="int_001",
                duration=60,
            )
            is True
        )
        assert coordinator.is_recording() is True

        # Get info
        info = coordinator.get_recording_info()
        assert info is not None
        assert info["experiment_id"] == "int_001"

        # Stop recording
        assert coordinator.stop_recording() is True
        assert coordinator.is_recording() is False

    def test_state_history_tracks_changes(self, mock_recording_service):
        """Should track state changes in history."""
        state_manager = StateManager(enable_history=True)
        coordinator = RecordingCoordinator(
            state_manager=state_manager,
            recording_service=mock_recording_service,
        )

        # Start recording
        coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="hist_001",
        )

        # Check history
        history = state_manager.get_history(StateCategory.RECORDING)
        assert len(history) >= 1

        # Verify source includes coordinator name
        assert any("RecordingCoordinator" in h.source for h in history)

    def test_arduino_trigger_workflow(self, mock_recording_service, mock_arduino_manager):
        """Test Arduino trigger workflow."""
        state_manager = StateManager(enable_history=True)
        coordinator = RecordingCoordinator(
            state_manager=state_manager,
            recording_service=mock_recording_service,
            arduino_manager=mock_arduino_manager,
        )

        # Start recording
        coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="arduino_001",
        )

        # Trigger zone enter
        assert (
            coordinator.trigger_recording(
                zone_name="zone1",
                trigger_type="enter",
            )
            is True
        )

        # Trigger zone exit
        assert (
            coordinator.trigger_recording(
                zone_name="zone1",
                trigger_type="exit",
            )
            is True
        )

    def test_error_recovery_reverts_state(self, mock_state_manager, mock_recording_service):
        """Should revert state on start error."""
        # Setup to cause error
        mock_state_manager.update_recording_state.side_effect = [
            None,  # First call succeeds (sets recording=True)
            Exception("Error"),  # Second call fails when reverting
        ]
        mock_recording_service.schedule_recording.side_effect = Exception("Start failure")

        coordinator = RecordingCoordinator(
            state_manager=mock_state_manager,
            recording_service=mock_recording_service,
        )

        # Should raise error
        with pytest.raises(RecordingCoordinatorError):
            coordinator.start_recording(
                output_path="/path/to/output",
                experiment_id="error_001",
            )

        # Verify state was reverted (called twice)
        assert mock_state_manager.update_recording_state.call_count == 2
