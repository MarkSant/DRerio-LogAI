"""Extended unit tests for ui/components/state_synchronizer.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.state_manager import StateCategory
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended:
    """Test StateSynchronizer state subscriptions, button state updates, and UI synchronization."""

    def test_init_and_dialog_manager_fallback(self):
        mock_gui = MagicMock()
        mock_gui.dialog_manager = MagicMock()

        sync = StateSynchronizer(mock_gui)
        assert sync.dialog_manager == mock_gui.dialog_manager

        custom_dialog = MagicMock()
        sync2 = StateSynchronizer(mock_gui, dialog_manager=custom_dialog)
        assert sync2.dialog_manager == custom_dialog

    def test_subscribe_to_state_changes(self):
        mock_gui = MagicMock()
        mock_sm = MagicMock()

        sync = StateSynchronizer(mock_gui, state_manager=mock_sm)
        sync.subscribe_to_state_changes()

        assert mock_sm.subscribe.call_count == 4
        # Verify subscriptions for RECORDING, PROCESSING, DETECTOR, PROJECT
        categories = [call[0][0] for call in mock_sm.subscribe.call_args_list]
        assert StateCategory.RECORDING in categories
        assert StateCategory.PROCESSING in categories
        assert StateCategory.DETECTOR in categories
        assert StateCategory.PROJECT in categories

    def test_on_recording_state_changed_schedules_ui_update(self):
        mock_gui = MagicMock()
        sync = StateSynchronizer(mock_gui)

        sync._on_recording_state_changed(StateCategory.RECORDING, "is_recording", False, True)
        mock_gui.root.after.assert_called_once_with(0, sync._update_recording_ui, True)

        mock_gui.root.after.reset_mock()
        sync._on_recording_state_changed(StateCategory.RECORDING, "arduino_connected", False, True)
        mock_gui.root.after.assert_called_once_with(0, sync._update_arduino_ui, True)

    def test_update_recording_ui_toggles_buttons(self):
        mock_gui = MagicMock()
        mock_gui.start_rec_btn = MagicMock()
        mock_gui.stop_rec_btn = MagicMock()

        sync = StateSynchronizer(mock_gui)

        # Recording started
        sync._update_recording_ui(True)
        mock_gui.start_rec_btn.config.assert_called_with(state="disabled")
        mock_gui.stop_rec_btn.config.assert_called_with(state="normal")

        # Recording stopped
        sync._update_recording_ui(False)
        mock_gui.start_rec_btn.config.assert_called_with(state="normal")
        mock_gui.stop_rec_btn.config.assert_called_with(state="disabled")

    def test_update_processing_ui_toggles_buttons(self):
        mock_gui = MagicMock()
        mock_gui.process_video_btn = MagicMock()
        mock_gui.analysis_view_controller = MagicMock()
        live_coord = mock_gui.controller.live_camera_session_coordinator
        live_coord.is_live_session_active.return_value = False
        proc_state = mock_gui.controller.state_manager.get_processing_state.return_value
        proc_state.is_live_session_active = False

        sync = StateSynchronizer(mock_gui)

        # Processing started
        sync._update_processing_ui(True)
        mock_gui.process_video_btn.config.assert_called_with(state="disabled")

        # Processing stopped
        sync._update_processing_ui(False)
        mock_gui.process_video_btn.config.assert_called_with(state="normal")
        mock_gui.analysis_view_controller.stop_analysis_view_mode.assert_called_once()

    def test_is_live_session_active_checks(self):
        mock_gui = MagicMock()
        mock_sm = MagicMock()
        mock_proc_state = MagicMock()
        mock_proc_state.is_live_session_active = True
        mock_sm.get_processing_state.return_value = mock_proc_state

        sync = StateSynchronizer(mock_gui, state_manager=mock_sm)
        assert sync._is_live_session_active() is True

        mock_proc_state.is_live_session_active = False
        assert sync._is_live_session_active() is False

    def test_update_arduino_ui(self):
        mock_gui = MagicMock()
        mock_gui.arduino_dashboard_widget = MagicMock()

        sync = StateSynchronizer(mock_gui)
        sync._update_arduino_ui(True)
        mock_gui.arduino_dashboard_widget.update_status.assert_called_once_with(True, None)
