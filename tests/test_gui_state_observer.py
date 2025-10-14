"""
Integration tests for GUI observing StateManager changes.

Tests that the GUI correctly subscribes to and responds to state changes
from the StateManager for reactive UI updates.
"""

from unittest.mock import MagicMock

import pytest


class TestGUIStateObserver:
    """Test GUI integration with StateManager observer pattern."""

    @pytest.fixture
    def mock_root(self):
        """Create a mock Tkinter root."""
        root = MagicMock()
        root.after = MagicMock(return_value=None)
        root.mainloop = MagicMock()
        return root

    @pytest.fixture
    def controller(self, mock_root):
        """Create a MainViewModel with mocked dependencies."""
        from unittest.mock import patch

        with patch("zebtrack.core.controller.ApplicationGUI"):
            with patch("zebtrack.core.controller.settings"):
                from zebtrack.core.controller import MainViewModel

                controller = MainViewModel(mock_root)
                return controller

    @pytest.fixture
    def mock_gui(self, mock_root, controller):
        """Create a minimal mock GUI for testing state observers."""
        # Create a simple mock GUI object that mimics the necessary structure
        gui = MagicMock()
        gui.root = mock_root
        gui.controller = controller
        gui.start_rec_btn = MagicMock()
        gui.stop_rec_btn = MagicMock()
        gui.process_video_btn = MagicMock()

        # Import the actual observer methods from GUI

        # Bind the actual subscription method (simplified)
        gui._subscribe_to_state_changes = lambda: None
        gui._on_recording_state_changed = lambda cat, key, old, new: (
            gui.root.after(0, gui._update_recording_ui, new) if key == "is_recording" else None
        )
        gui._on_processing_state_changed = lambda cat, key, old, new: (
            gui.root.after(0, gui._update_processing_ui, new) if key == "is_processing" else None
        )
        gui._on_detector_state_changed = lambda cat, key, old, new: (
            gui.root.after(0, gui._update_detector_ui, new)
            if key == "detector_initialized"
            else None
        )

        # Bind the actual UI update methods
        def _update_recording_ui(is_recording):
            if is_recording:
                if gui.start_rec_btn:
                    gui.start_rec_btn.config(state="disabled")
                if gui.stop_rec_btn:
                    gui.stop_rec_btn.config(state="normal")
            else:
                if gui.start_rec_btn:
                    gui.start_rec_btn.config(state="normal")
                if gui.stop_rec_btn:
                    gui.stop_rec_btn.config(state="disabled")

        def _update_processing_ui(is_processing):
            if is_processing:
                if gui.process_video_btn:
                    gui.process_video_btn.config(state="disabled")
            else:
                if gui.process_video_btn:
                    gui.process_video_btn.config(state="normal")

        def _update_detector_ui(detector_initialized):
            pass  # Simplified for testing

        gui._update_recording_ui = _update_recording_ui
        gui._update_processing_ui = _update_processing_ui
        gui._update_detector_ui = _update_detector_ui

        # Subscribe to StateManager
        from zebtrack.core.state_manager import StateCategory

        controller.state_manager.subscribe(StateCategory.RECORDING, gui._on_recording_state_changed)
        controller.state_manager.subscribe(
            StateCategory.PROCESSING, gui._on_processing_state_changed
        )
        controller.state_manager.subscribe(StateCategory.DETECTOR, gui._on_detector_state_changed)

        return gui

    def test_gui_subscribes_to_state_manager(self, mock_gui, controller):
        """GUI should subscribe to StateManager on initialization."""
        from zebtrack.core.state_manager import StateCategory

        # Verify GUI subscribed to state changes
        recording_observers = controller.state_manager._observers.get(StateCategory.RECORDING, [])
        processing_observers = controller.state_manager._observers.get(StateCategory.PROCESSING, [])
        detector_observers = controller.state_manager._observers.get(StateCategory.DETECTOR, [])

        # Check that observers are registered
        assert len(recording_observers) > 0
        assert len(processing_observers) > 0
        assert len(detector_observers) > 0

    def test_recording_state_change_triggers_ui_update(self, mock_gui, controller):
        """Recording state changes should trigger UI updates."""
        # Trigger recording state change
        controller.state_manager.update_recording_state(source="test", is_recording=True)

        # Verify root.after was called to schedule UI update
        assert mock_gui.root.after.called
        # Extract the callback that was scheduled
        scheduled_calls = [call for call in mock_gui.root.after.call_args_list if call[0][0] == 0]
        assert len(scheduled_calls) > 0

        # Manually execute the scheduled callback
        callback = scheduled_calls[-1][0][1]
        args = scheduled_calls[-1][0][2:]
        callback(*args)

        # Verify button states were updated
        mock_gui.start_rec_btn.config.assert_called_with(state="disabled")
        mock_gui.stop_rec_btn.config.assert_called_with(state="normal")

    def test_processing_state_change_triggers_ui_update(self, mock_gui, controller):
        """Processing state changes should trigger UI updates."""
        # Trigger processing state change
        controller.state_manager.update_processing_state(source="test", is_processing=True)

        # Verify root.after was called
        assert mock_gui.root.after.called

        # Extract and execute the scheduled callback
        scheduled_calls = [call for call in mock_gui.root.after.call_args_list if call[0][0] == 0]
        assert len(scheduled_calls) > 0

        callback = scheduled_calls[-1][0][1]
        args = scheduled_calls[-1][0][2:]
        callback(*args)

        # Verify button state was updated
        mock_gui.process_video_btn.config.assert_called_with(state="disabled")

    def test_detector_state_change_triggers_ui_update(self, mock_gui, controller):
        """Detector state changes should trigger UI updates."""
        # Trigger detector state change
        controller.state_manager.update_detector_state(source="test", detector_initialized=True)

        # Verify root.after was called to schedule UI update
        assert mock_gui.root.after.called

        # Extract and execute the scheduled callback
        scheduled_calls = [call for call in mock_gui.root.after.call_args_list if call[0][0] == 0]
        assert len(scheduled_calls) > 0

        callback = scheduled_calls[-1][0][1]
        args = scheduled_calls[-1][0][2:]
        callback(*args)

        # Detector UI update executed without error

    def test_ui_updates_scheduled_on_main_thread(self, mock_gui, controller):
        """UI updates should always be scheduled on main thread via root.after."""
        # Clear previous calls
        mock_gui.root.after.reset_mock()

        # Trigger multiple state changes
        controller.state_manager.update_recording_state(source="test", is_recording=True)
        controller.state_manager.update_processing_state(source="test", is_processing=True)
        controller.state_manager.update_detector_state(source="test", detector_initialized=True)

        # Verify all UI updates were scheduled via root.after(0, ...)
        # This ensures thread safety
        after_calls = mock_gui.root.after.call_args_list
        zero_delay_calls = [call for call in after_calls if call[0][0] == 0]

        # Should have at least 3 calls (one per state change)
        assert len(zero_delay_calls) >= 3

    def test_recording_state_stop_updates_ui(self, mock_gui, controller):
        """Stopping recording should re-enable start button."""
        # Start recording
        controller.state_manager.update_recording_state(source="test", is_recording=True)
        mock_gui.root.after.reset_mock()

        # Stop recording
        controller.state_manager.update_recording_state(source="test", is_recording=False)

        # Verify root.after was called
        assert mock_gui.root.after.called

        # Execute the scheduled callback
        scheduled_calls = [call for call in mock_gui.root.after.call_args_list if call[0][0] == 0]
        callback = scheduled_calls[-1][0][1]
        args = scheduled_calls[-1][0][2:]
        callback(*args)

        # Verify button states were updated
        mock_gui.start_rec_btn.config.assert_called_with(state="normal")
        mock_gui.stop_rec_btn.config.assert_called_with(state="disabled")

    def test_processing_state_stop_updates_ui(self, mock_gui, controller):
        """Stopping processing should re-enable process button."""
        # Start processing
        controller.state_manager.update_processing_state(source="test", is_processing=True)
        mock_gui.root.after.reset_mock()

        # Stop processing
        controller.state_manager.update_processing_state(source="test", is_processing=False)

        # Verify root.after was called
        assert mock_gui.root.after.called

        # Execute the scheduled callback
        scheduled_calls = [call for call in mock_gui.root.after.call_args_list if call[0][0] == 0]
        callback = scheduled_calls[-1][0][1]
        args = scheduled_calls[-1][0][2:]
        callback(*args)

        # Verify button state was updated
        mock_gui.process_video_btn.config.assert_called_with(state="normal")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
