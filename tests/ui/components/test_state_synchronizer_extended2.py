"""Extended unit tests for ui/components/state_synchronizer.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended2:
    """Test StateSynchronizer social metrics, dialog manager DI, and processing modes."""

    def test_dialog_manager_property_injected_and_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        # Injected directly
        mock_dm = MagicMock()
        sync_injected = StateSynchronizer(gui, dialog_manager=mock_dm)
        assert sync_injected.dialog_manager is mock_dm

        # Fallback to gui
        sync_fallback = StateSynchronizer(gui, dialog_manager=None)
        assert sync_fallback.dialog_manager is gui.dialog_manager

    def test_update_social_summary_single_subject_mode(self):
        gui = MagicMock()
        gui._active_processing_mode = ProcessingMode.SINGLE_SUBJECT
        gui.analysis_display_widget = MagicMock()

        sync = StateSynchronizer(gui)
        sync.update_social_summary(profile="standard", stats=None, tracks=["1"])

        gui.analysis_display_widget.set_social_summary.assert_called_once()
        msg = gui.analysis_display_widget.set_social_summary.call_args[0][0]
        assert "not applicable" in msg or "não aplicável" in msg or "single-subject" in msg

    def test_update_social_summary_with_percentages(self):
        gui = MagicMock()
        gui._active_processing_mode = ProcessingMode.MULTI_TRACK
        gui.analysis_display_widget = MagicMock()

        sync = StateSynchronizer(gui)
        stats = {"social_time_percentage": {"1": 45.5, "2": 54.5}}
        sync.update_social_summary(profile="social_interaction", stats=stats, tracks=["1", "2"])

        gui.analysis_display_widget.set_social_summary.assert_called_once()
        msg = gui.analysis_display_widget.set_social_summary.call_args[0][0]
        assert "ID 1: 45.5%" in msg
        assert "ID 2: 54.5%" in msg

    def test_update_social_summary_profile_mismatch(self):
        gui = MagicMock()
        gui._active_processing_mode = ProcessingMode.MULTI_TRACK
        gui.analysis_display_widget = MagicMock()

        sync = StateSynchronizer(gui)
        sync.update_social_summary(profile="open_field", stats=None, tracks=["1", "2"])

        gui.analysis_display_widget.set_social_summary.assert_called_once()
        msg = gui.analysis_display_widget.set_social_summary.call_args[0][0]
        assert "profile produces no social metrics" in msg or "perfil atual" in msg
