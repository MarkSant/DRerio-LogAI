"""Extended unit tests for ui/components/state_synchronizer.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.state_manager import StateCategory
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended4:
    """Test StateSynchronizer state change dispatching to Tk main thread."""

    def test_on_recording_state_changed_is_recording(self):
        gui = MagicMock()
        sync = object.__new__(StateSynchronizer)
        sync.gui = gui

        sync._on_recording_state_changed(StateCategory.RECORDING, "is_recording", False, True)
        gui.root.after.assert_called_once_with(0, sync._update_recording_ui, True)

    def test_on_processing_state_changed_is_processing(self):
        gui = MagicMock()
        sync = object.__new__(StateSynchronizer)
        sync.gui = gui

        sync._on_processing_state_changed(StateCategory.PROCESSING, "is_processing", False, True)
        gui.root.after.assert_called_once_with(0, sync._update_processing_ui, True)

    def test_on_detector_state_changed_initialized(self):
        gui = MagicMock()
        sync = object.__new__(StateSynchronizer)
        sync.gui = gui

        sync._on_detector_state_changed(StateCategory.DETECTOR, "detector_initialized", False, True)
        gui.root.after.assert_called_once_with(0, sync._update_detector_ui, True)
