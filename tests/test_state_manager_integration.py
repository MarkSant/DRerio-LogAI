"""
Integration tests for StateManager with MainViewModel.

Phase 2, Step 4: Verify that StateManager is properly integrated with the controller
and that state changes are tracked correctly through the application lifecycle.

Phase 1.1: Enhanced with threading.Event synchronization to eliminate race conditions
in observer-based tests.
"""
import pytest

pytest.skip("Obsolete: MainViewModel no longer has is_recording property", allow_module_level=True)

import threading
from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.state_manager import StateCategory


class TestStateManagerControllerIntegration:
    """Test StateManager integration with MainViewModel."""

    @pytest.fixture
    def mock_root(self):
        """Create a mock Tkinter root."""
        root = MagicMock()
        root.after = MagicMock()
        root.mainloop = MagicMock()
        return root

    @pytest.fixture
    def test_event(self):
        """Create a threading.Event for test synchronization."""
        return threading.Event()

    @pytest.fixture
    def controller(self, mock_root, test_event):
        """Create a MainViewModel with mocked dependencies and test synchronization."""
        from tests.helpers import create_test_controller

        # Pass test_sync_event to factory for proper test synchronization
        controller = create_test_controller(root=mock_root, test_sync_event=test_event)
        return controller

    def test_state_manager_initialized(self, controller):
        """StateManager should be initialized on controller creation."""
        assert hasattr(controller, "state_manager")
        assert controller.state_manager is not None

    def test_recording_state_property(self, controller, test_event):
        """is_recording property should delegate to StateManager."""
        # Initial state
        assert controller.is_recording is False

        # Clear event before state change
        test_event.clear()

        # Set via property
        controller.is_recording = True

        # Wait for state change to be processed
        assert test_event.wait(timeout=2.0), "Timeout waiting for state change"

        assert controller.is_recording is True

        # Verify state was updated in StateManager
        state = controller.state_manager.get_recording_state()
        assert state.is_recording is True

        # Check history was recorded
        history = controller.state_manager.get_history(
            category=StateCategory.RECORDING, key="is_recording"
        )
        assert len(history) >= 1

    def test_detector_state_updates(self, controller, test_event):
        """Detector state should be tracked in StateManager."""
        # Initially no detector
        detector_state = controller.state_manager.get_detector_state()
        assert detector_state.detector_initialized is False
        assert controller.detector_initialized is False  # Test property

        # Clear event before state change
        test_event.clear()

        # Simulate detector setup (would normally happen in setup_detector)
        controller.state_manager.update_detector_state(
            source="test",
            detector_initialized=True,
            active_weight_name="test_weight.pt",
            use_openvino=False,
        )

        # Wait for state change to be processed
        assert test_event.wait(timeout=2.0), "Timeout waiting for detector state change"

        # Verify state was updated
        detector_state = controller.state_manager.get_detector_state()
        assert detector_state.detector_initialized is True
        assert detector_state.active_weight_name == "test_weight.pt"
        assert detector_state.use_openvino is False
        assert controller.detector_initialized is True  # Test property

    def test_processing_state_lifecycle(self, controller, test_event):
        """Processing state should track full lifecycle."""
        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is False
        assert controller.is_processing is False  # Test property

        # Clear event and start processing
        test_event.clear()
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=True,
            current_video="test.mp4",
            total_frames=1000,
        )
        assert test_event.wait(timeout=2.0), "Timeout waiting for processing start"

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is True
        assert processing_state.current_video == "test.mp4"
        assert processing_state.total_frames == 1000
        assert controller.is_processing is True  # Test property

        # Progress update
        test_event.clear()
        controller.state_manager.update_processing_state(source="test", current_frame=500)
        assert test_event.wait(timeout=2.0), "Timeout waiting for progress update"

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.current_frame == 500

        # Complete processing
        test_event.clear()
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=False,
            current_video=None,
        )
        assert test_event.wait(timeout=2.0), "Timeout waiting for processing completion"

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is False
        assert controller.is_processing is False  # Test property

    def test_project_state_updates(self, controller, test_event):
        """Project state should be tracked when projects are loaded."""
        project_state = controller.state_manager.get_project_state()
        assert project_state.project_path is None

        # Clear event and simulate project loading
        test_event.clear()
        test_path = Path("/test/project")
        controller.state_manager.update_project_state(
            source="test",
            project_path=test_path,
            project_data={"videos": ["v1.mp4", "v2.mp4"]},
        )
        assert test_event.wait(timeout=2.0), "Timeout waiting for project state update"

        project_state = controller.state_manager.get_project_state()
        assert project_state.project_path == test_path
        assert "videos" in project_state.project_data
        assert len(project_state.project_data["videos"]) == 2

    def test_state_history_tracking(self, controller, test_event):
        """State changes should be recorded in history."""
        # Make several state changes with synchronization
        test_event.clear()
        controller.is_recording = True
        assert test_event.wait(timeout=2.0), "Timeout on first recording change"

        test_event.clear()
        controller.is_recording = False
        assert test_event.wait(timeout=2.0), "Timeout on second recording change"

        test_event.clear()
        controller.state_manager.update_processing_state(source="test", is_processing=True)
        assert test_event.wait(timeout=2.0), "Timeout on processing start"

        test_event.clear()
        controller.state_manager.update_processing_state(source="test", is_processing=False)
        assert test_event.wait(timeout=2.0), "Timeout on processing end"

        # Get all history
        history = controller.state_manager.get_history()
        assert len(history) > 0

        # Filter by category
        recording_history = controller.state_manager.get_history(category=StateCategory.RECORDING)
        assert len(recording_history) >= 2

        processing_history = controller.state_manager.get_history(category=StateCategory.PROCESSING)
        assert len(processing_history) >= 2

    def test_state_observer_can_be_added(self, controller, test_event):
        """Should be able to subscribe to state changes."""
        changes = []

        def observer(category, key, old_val, new_val):
            changes.append((category.name, key, old_val, new_val))

        controller.state_manager.subscribe(StateCategory.RECORDING, observer)

        # Clear the event before triggering state change
        test_event.clear()

        # Trigger state change
        controller.is_recording = True

        # Wait for state change to be processed (Phase 1.1: race condition elimination)
        assert test_event.wait(timeout=2.0), "Timeout waiting for state change to be processed"

        # Observer should have been called
        assert len(changes) > 0
        assert any(change[1] == "is_recording" for change in changes)

    def test_state_dump_for_debugging(self, controller, test_event):
        """dump_state should provide comprehensive state overview."""
        # Set up some state with synchronization
        test_event.clear()
        controller.is_recording = True
        assert test_event.wait(timeout=2.0), "Timeout on recording state change"

        test_event.clear()
        controller.state_manager.update_detector_state(
            source="test",
            detector_initialized=True,
            active_weight_name="test.pt",
        )
        assert test_event.wait(timeout=2.0), "Timeout on detector state change"

        test_event.clear()
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=True,
            current_video="test.mp4",
        )
        assert test_event.wait(timeout=2.0), "Timeout on processing state change"

        # Dump state
        dump = controller.state_manager.dump_state()

        # Verify structure
        assert "recording" in dump
        assert dump["recording"]["is_recording"] is True

        assert "detector" in dump
        assert dump["detector"]["initialized"] is True
        assert dump["detector"]["active_weight"] == "test.pt"

        assert "processing" in dump
        assert dump["processing"]["is_processing"] is True
        assert dump["processing"]["current_video"] == "test.mp4"

    def test_state_snapshots_are_immutable(self, controller, test_event):
        """State snapshots should not affect original state."""
        # Set initial state
        test_event.clear()
        controller.is_recording = True
        assert test_event.wait(timeout=2.0), "Timeout on initial recording state change"

        # Get snapshot
        snapshot1 = controller.state_manager.get_snapshot()
        assert snapshot1.recording.is_recording is True

        # Modify snapshot (should not affect original)
        _snapshot1_copy = snapshot1.recording.copy()
        # Original state should be unchanged in StateManager
        assert controller.is_recording is True

        # Change state
        test_event.clear()
        controller.is_recording = False
        assert test_event.wait(timeout=2.0), "Timeout on second recording state change"

        # Old snapshot should still reflect old state (it's immutable)
        assert snapshot1.recording.is_recording is True

        # New snapshot should reflect new state
        snapshot2 = controller.state_manager.get_snapshot()
        assert snapshot2.recording.is_recording is False


if __name__ == "__main__":
    pytest.main([__file__])
