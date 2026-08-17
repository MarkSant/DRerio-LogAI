"""Extended unit tests for ui/components/state_synchronizer.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended6:
    """Test StateSynchronizer processing state changes dispatching."""

    def test_on_processing_state_changed_dispatches_ui(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)

        sync._on_processing_state_changed(None, "is_processing", False, True)
        gui.root.after.assert_called_once_with(0, sync._update_processing_ui, True)

    def test_update_processing_ui_active(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)

        sync._update_processing_ui(True)
        gui.process_video_btn.config.assert_called_once_with(state="disabled")

    def test_update_processing_ui_inactive(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        gui.analysis_view_controller = MagicMock()
        sync = StateSynchronizer(gui)
        monkeypatch.setattr(sync, "_is_live_session_active", lambda: False)

        sync._update_processing_ui(False)
        gui.process_video_btn.config.assert_called_once_with(state="normal")
        gui.analysis_view_controller.stop_analysis_view_mode.assert_called_once()
