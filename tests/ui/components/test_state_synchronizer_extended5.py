"""Extended unit tests for ui/components/state_synchronizer.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended5:
    """Test StateSynchronizer recording and processing UI update methods."""

    def test_update_recording_ui_is_recording(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)

        sync._update_recording_ui(True)
        gui.start_rec_btn.config.assert_called_once_with(state="disabled")
        gui.stop_rec_btn.config.assert_called_once_with(state="normal")

    def test_update_recording_ui_stopped(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)

        sync._update_recording_ui(False)
        gui.start_rec_btn.config.assert_called_once_with(state="normal")
        gui.stop_rec_btn.config.assert_called_once_with(state="disabled")

    def test_on_recording_state_changed_dispatches_ui(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)

        sync._on_recording_state_changed(None, "is_recording", False, True)
        gui.root.after.assert_called_once_with(0, sync._update_recording_ui, True)
