"""Extended unit tests for ui/components/state_synchronizer.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.state_manager import StateCategory
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended:
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


class TestStateSynchronizerExtended2:
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


class TestStateSynchronizerExtended4:
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


class TestStateSynchronizerExtended5:
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


class TestStateSynchronizerExtended6:
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


class TestStateSynchronizerExtended7:
    def test_state_synchronizer_init(self):
        gui = MagicMock()
        dialog_mgr = MagicMock()
        state_mgr = MagicMock()

        sync = StateSynchronizer(
            gui,
            dialog_manager=dialog_mgr,
            state_manager=state_mgr,
        )

        assert sync.gui is gui
        assert sync.dialog_manager is dialog_mgr
        assert sync._state_manager is state_mgr

    def test_state_synchronizer_dialog_manager_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        sync = StateSynchronizer(gui)
        assert sync.dialog_manager is gui.dialog_manager

    def test_state_synchronizer_gui_reference(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)
        assert sync.gui is gui
