"""
Integration tests for StateManager with MainViewModel.

Phase 2, Step 4: Verify that StateManager is properly integrated with the controller
and that state changes are tracked correctly through the application lifecycle.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
    def controller(self, mock_root):
        """Create a MainViewModel with mocked dependencies."""
        with patch("zebtrack.core.controller.ApplicationGUI"):
            with patch("zebtrack.core.controller.settings"):
                from zebtrack.core.controller import MainViewModel

                controller = MainViewModel(mock_root)
                return controller

    def test_state_manager_initialized(self, controller):
        """StateManager should be initialized on controller creation."""
        assert hasattr(controller, "state_manager")
        assert controller.state_manager is not None

    def test_recording_state_property(self, controller):
        """is_recording property should delegate to StateManager."""
        # Initial state
        assert controller.is_recording is False

        # Set via property
        controller.is_recording = True
        assert controller.is_recording is True

        # Verify state was updated in StateManager
        state = controller.state_manager.get_recording_state()
        assert state.is_recording is True

        # Check history was recorded
        history = controller.state_manager.get_history(
            category=StateCategory.RECORDING, key="is_recording"
        )
        assert len(history) >= 1

    def test_detector_state_updates(self, controller):
        """Detector state should be tracked in StateManager."""
        # Initially no detector
        detector_state = controller.state_manager.get_detector_state()
        assert detector_state.detector_initialized is False
        assert controller.detector_initialized is False  # Test property

        # Simulate detector setup (would normally happen in setup_detector)
        controller.state_manager.update_detector_state(
            source="test",
            detector_initialized=True,
            active_weight_name="test_weight.pt",
            use_openvino=False,
        )

        # Verify state was updated
        detector_state = controller.state_manager.get_detector_state()
        assert detector_state.detector_initialized is True
        assert detector_state.active_weight_name == "test_weight.pt"
        assert detector_state.use_openvino is False
        assert controller.detector_initialized is True  # Test property

    def test_processing_state_lifecycle(self, controller):
        """Processing state should track full lifecycle."""
        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is False
        assert controller.is_processing is False  # Test property

        # Start processing
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=True,
            current_video="test.mp4",
            total_frames=1000,
        )

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is True
        assert processing_state.current_video == "test.mp4"
        assert processing_state.total_frames == 1000
        assert controller.is_processing is True  # Test property

        # Progress update
        controller.state_manager.update_processing_state(source="test", current_frame=500)

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.current_frame == 500

        # Complete processing
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=False,
            current_video=None,
        )

        processing_state = controller.state_manager.get_processing_state()
        assert processing_state.is_processing is False
        assert controller.is_processing is False  # Test property

    def test_project_state_updates(self, controller):
        """Project state should be tracked when projects are loaded."""
        project_state = controller.state_manager.get_project_state()
        assert project_state.project_path is None

        # Simulate project loading
        test_path = Path("/test/project")
        controller.state_manager.update_project_state(
            source="test",
            project_path=test_path,
            project_data={"videos": ["v1.mp4", "v2.mp4"]},
        )

        project_state = controller.state_manager.get_project_state()
        assert project_state.project_path == test_path
        assert "videos" in project_state.project_data
        assert len(project_state.project_data["videos"]) == 2

    def test_state_history_tracking(self, controller):
        """State changes should be recorded in history."""
        # Make several state changes
        controller.is_recording = True
        controller.is_recording = False

        controller.state_manager.update_processing_state(source="test", is_processing=True)
        controller.state_manager.update_processing_state(source="test", is_processing=False)

        # Get all history
        history = controller.state_manager.get_history()
        assert len(history) > 0

        # Filter by category
        recording_history = controller.state_manager.get_history(category=StateCategory.RECORDING)
        assert len(recording_history) >= 2

        processing_history = controller.state_manager.get_history(category=StateCategory.PROCESSING)
        assert len(processing_history) >= 2

    def test_state_observer_can_be_added(self, controller):
        """Should be able to subscribe to state changes."""
        changes = []

        def observer(category, key, old_val, new_val):
            changes.append((category.name, key, old_val, new_val))

        controller.state_manager.subscribe(StateCategory.RECORDING, observer)

        # Trigger state change
        controller.is_recording = True

        # Observer should have been called
        assert len(changes) > 0
        assert any(change[1] == "is_recording" for change in changes)

    def test_state_dump_for_debugging(self, controller):
        """dump_state should provide comprehensive state overview."""
        # Set up some state
        controller.is_recording = True
        controller.state_manager.update_detector_state(
            source="test",
            detector_initialized=True,
            active_weight_name="test.pt",
        )
        controller.state_manager.update_processing_state(
            source="test",
            is_processing=True,
            current_video="test.mp4",
        )

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

    def test_state_snapshots_are_immutable(self, controller):
        """State snapshots should not affect original state."""
        # Set initial state
        controller.is_recording = True

        # Get snapshot
        snapshot1 = controller.state_manager.get_snapshot()
        assert snapshot1.recording.is_recording is True

        # Modify snapshot (should not affect original)
        _snapshot1_copy = snapshot1.recording.copy()  # noqa: F841
        # Original state should be unchanged in StateManager
        assert controller.is_recording is True

        # Change state
        controller.is_recording = False

        # Old snapshot should still reflect old state (it's immutable)
        assert snapshot1.recording.is_recording is True

        # New snapshot should reflect new state
        snapshot2 = controller.state_manager.get_snapshot()
        assert snapshot2.recording.is_recording is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
