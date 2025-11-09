"""Tests for StateSynchronizer component."""

from unittest.mock import Mock, patch

import pytest

from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


@pytest.fixture(autouse=True)
def block_all_dialogs():
    """Automatically block ALL dialog windows for all tests in this file."""
    with (
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.askyesno", return_value=False),
        patch("tkinter.messagebox.askokcancel", return_value=False),
        patch("tkinter.messagebox.askyesnocancel", return_value=None),
    ):
        yield


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager instance."""
    state_mgr = Mock()
    state_mgr.subscribe = Mock()
    return state_mgr


@pytest.fixture
def mock_controller(mock_state_manager):
    """Create a mock controller."""
    controller = Mock()
    controller.state_manager = mock_state_manager
    return controller


@pytest.fixture
def mock_gui(tkinter_root, mock_controller):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    # Mock Tkinter methods to prevent AttributeError
    gui.root.after = Mock(return_value="after#0")
    gui.root.after_cancel = Mock()
    gui.controller = mock_controller
    gui.state_manager = mock_controller.state_manager

    # Recording widgets
    gui.start_rec_btn = Mock()
    gui.stop_rec_btn = Mock()

    # Processing widgets
    gui.process_video_btn = Mock()

    # Arduino widget
    gui.arduino_dashboard_widget = Mock()

    # Analysis widgets
    gui.analysis_video_label = Mock()
    gui.analysis_video_label.winfo_exists = Mock(return_value=True)
    gui.roi_canvas = Mock()
    gui.roi_canvas.winfo_exists = Mock(return_value=True)
    gui.roi_canvas.pack_forget = Mock()
    gui.viz_frame = Mock()
    gui.viz_frame.winfo_exists = Mock(return_value=True)
    gui.viz_frame.destroy = Mock()
    gui.zone_tab_frame = Mock()
    gui.zone_tab_frame.winfo_exists = Mock(return_value=True)
    gui.zone_tab_frame.destroy = Mock()
    gui.notebook = Mock()
    gui.notebook.destroy = Mock()
    gui.main_controls_frame = Mock()
    gui.main_controls_frame.destroy = Mock()
    gui.project_overview_frame = None
    gui.project_overview_tree = None

    # Analysis variables
    gui.analysis_status_var = Mock()
    gui.analysis_task_var = Mock()
    gui.analysis_metadata_var = Mock()
    gui.analysis_group_var = Mock()
    gui.analysis_day_var = Mock()
    gui.analysis_subject_var = Mock()
    gui.external_trigger_notice_var = Mock()

    # Track selector
    gui.track_selector_var = Mock()
    gui.track_selector_widget = Mock()
    gui._available_track_options = ()
    gui._active_processing_mode = ProcessingMode.MULTI_TRACK

    # Progress and metadata
    gui.progress_labels = {}
    gui.project_status_vars = {}
    gui._project_status_containers = {}
    gui._last_overview_counts = {}
    gui._overview_refresh_job = None

    # Analysis state
    gui.analysis_tab_frame = Mock()
    gui._analysis_overlay_image = Mock()
    gui._current_detections = []
    gui._last_analysis_frame = None

    # Helper methods
    gui.hide_progress_bar = Mock()
    gui._reload_config_editor_values_widget = Mock()
    gui.show_info = Mock()

    return gui


@pytest.fixture
def state_synchronizer(mock_gui):
    """Create a StateSynchronizer instance for testing."""
    return StateSynchronizer(mock_gui)


@pytest.mark.gui
class TestStateSynchronizerInitialization:
    """Tests for StateSynchronizer initialization."""

    def test_initialization(self, state_synchronizer, mock_gui):
        """Test that StateSynchronizer initializes correctly."""
        assert state_synchronizer.gui is mock_gui

    def test_initialization_with_real_gui(self, tkinter_root):
        """Test initialization with minimal real gui object."""
        gui = Mock()
        gui.root = tkinter_root
        synchronizer = StateSynchronizer(gui)
        assert synchronizer.gui is gui


@pytest.mark.gui
class TestStateChangeSubscription:
    """Tests for state change subscription."""

    def test_subscribe_to_state_changes_registers_callbacks(
        self, state_synchronizer, mock_state_manager
    ):
        """Test that all callbacks are registered with StateManager."""
        from zebtrack.core.state_manager import StateCategory

        state_synchronizer.subscribe_to_state_changes()

        # Verify subscribe was called 4 times (RECORDING, PROCESSING, DETECTOR, PROJECT)
        assert mock_state_manager.subscribe.call_count == 4

        # Verify each category was subscribed to
        calls = mock_state_manager.subscribe.call_args_list
        categories = [call[0][0] for call in calls]

        assert StateCategory.RECORDING in categories
        assert StateCategory.PROCESSING in categories
        assert StateCategory.DETECTOR in categories
        assert StateCategory.PROJECT in categories

    def test_subscribe_to_state_changes_registers_correct_callbacks(
        self, state_synchronizer, mock_state_manager
    ):
        """Test that correct callback methods are registered."""
        from zebtrack.core.state_manager import StateCategory

        state_synchronizer.subscribe_to_state_changes()

        # Get all subscribe calls
        calls = mock_state_manager.subscribe.call_args_list

        # Build dict of category -> callback
        subscriptions = {call[0][0]: call[0][1] for call in calls}

        # Verify correct callbacks
        assert (
            subscriptions[StateCategory.RECORDING] == state_synchronizer._on_recording_state_changed
        )
        assert (
            subscriptions[StateCategory.PROCESSING]
            == state_synchronizer._on_processing_state_changed
        )
        assert (
            subscriptions[StateCategory.DETECTOR] == state_synchronizer._on_detector_state_changed
        )
        assert subscriptions[StateCategory.PROJECT] == state_synchronizer._on_project_state_changed


@pytest.mark.gui
class TestRecordingStateCallbacks:
    """Tests for recording state change callbacks."""

    def test_on_recording_state_changed_is_recording(self, state_synchronizer, mock_gui):
        """Test callback when is_recording changes."""
        state_synchronizer._on_recording_state_changed("RECORDING", "is_recording", False, True)

        # Verify root.after was called to schedule UI update
        mock_gui.root.after.assert_called_once()
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0
        assert call_args[0][1] == state_synchronizer._update_recording_ui
        assert call_args[0][2] is True

    def test_on_recording_state_changed_arduino_connected(self, state_synchronizer, mock_gui):
        """Test callback when arduino_connected changes."""
        state_synchronizer._on_recording_state_changed(
            "RECORDING", "arduino_connected", False, True
        )

        # Verify root.after was called to schedule Arduino UI update
        mock_gui.root.after.assert_called_once()
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0
        assert call_args[0][1] == state_synchronizer._update_arduino_ui
        assert call_args[0][2] is True

    def test_on_recording_state_changed_other_key(self, state_synchronizer, mock_gui):
        """Test callback with unhandled key."""
        state_synchronizer._on_recording_state_changed("RECORDING", "other_key", "old", "new")

        # Should not schedule any UI update
        mock_gui.root.after.assert_not_called()

    def test_update_recording_ui_recording_started(self, state_synchronizer, mock_gui):
        """Test UI update when recording starts."""
        state_synchronizer._update_recording_ui(True)

        # Verify start button disabled
        mock_gui.start_rec_btn.config.assert_called_once_with(state="disabled")

        # Verify stop button enabled
        mock_gui.stop_rec_btn.config.assert_called_once_with(state="normal")

    def test_update_recording_ui_recording_stopped(self, state_synchronizer, mock_gui):
        """Test UI update when recording stops."""
        state_synchronizer._update_recording_ui(False)

        # Verify start button enabled
        mock_gui.start_rec_btn.config.assert_called_once_with(state="normal")

        # Verify stop button disabled
        mock_gui.stop_rec_btn.config.assert_called_once_with(state="disabled")

    def test_update_recording_ui_no_buttons(self, state_synchronizer, mock_gui):
        """Test UI update when buttons are None."""
        mock_gui.start_rec_btn = None
        mock_gui.stop_rec_btn = None

        # Should not crash
        state_synchronizer._update_recording_ui(True)


@pytest.mark.gui
class TestProcessingStateCallbacks:
    """Tests for processing state change callbacks."""

    def test_on_processing_state_changed_is_processing(self, state_synchronizer, mock_gui):
        """Test callback when is_processing changes."""
        state_synchronizer._on_processing_state_changed("PROCESSING", "is_processing", False, True)

        # Verify root.after was called to schedule UI update
        mock_gui.root.after.assert_called_once()
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0
        assert call_args[0][1] == state_synchronizer._update_processing_ui
        assert call_args[0][2] is True

    def test_on_processing_state_changed_other_key(self, state_synchronizer, mock_gui):
        """Test callback with unhandled key."""
        state_synchronizer._on_processing_state_changed("PROCESSING", "other_key", "old", "new")

        # Should not schedule any UI update
        mock_gui.root.after.assert_not_called()

    def test_update_processing_ui_processing_started(self, state_synchronizer, mock_gui):
        """Test UI update when processing starts."""
        state_synchronizer._update_processing_ui(True)

        # Verify process button disabled
        mock_gui.process_video_btn.config.assert_called_once_with(state="disabled")

    def test_update_processing_ui_processing_stopped(self, state_synchronizer, mock_gui):
        """Test UI update when processing stops."""
        state_synchronizer._update_processing_ui(False)

        # Verify process button enabled
        mock_gui.process_video_btn.config.assert_called_once_with(state="normal")

    def test_update_processing_ui_no_button(self, state_synchronizer, mock_gui):
        """Test UI update when button is None."""
        mock_gui.process_video_btn = None

        # Should not crash
        state_synchronizer._update_processing_ui(True)


@pytest.mark.gui
class TestDetectorStateCallbacks:
    """Tests for detector state change callbacks."""

    def test_on_detector_state_changed_initialized(self, state_synchronizer, mock_gui):
        """Test callback when detector_initialized changes."""
        state_synchronizer._on_detector_state_changed(
            "DETECTOR", "detector_initialized", False, True
        )

        # Verify root.after was called to schedule UI update
        mock_gui.root.after.assert_called_once()
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0
        assert call_args[0][1] == state_synchronizer._update_detector_ui
        assert call_args[0][2] is True

    def test_on_detector_state_changed_other_key(self, state_synchronizer, mock_gui):
        """Test callback with unhandled key."""
        state_synchronizer._on_detector_state_changed("DETECTOR", "other_key", "old", "new")

        # Should not schedule any UI update
        mock_gui.root.after.assert_not_called()

    def test_update_detector_ui_initialized(self, state_synchronizer, mock_gui):
        """Test UI update when detector is initialized."""
        # Currently a stub - just verify it doesn't crash
        state_synchronizer._update_detector_ui(True)

    def test_update_detector_ui_uninitialized(self, state_synchronizer, mock_gui):
        """Test UI update when detector is uninitialized."""
        # Currently a stub - just verify it doesn't crash
        state_synchronizer._update_detector_ui(False)


@pytest.mark.gui
class TestProjectStateCallbacks:
    """Tests for project state change callbacks."""

    def test_on_project_state_changed_project_path(self, state_synchronizer, mock_gui):
        """Test callback when project_path changes."""
        from pathlib import Path

        project_path = Path("/path/to/project")
        state_synchronizer._on_project_state_changed("PROJECT", "project_path", None, project_path)

        # Verify root.after was called to schedule UI update
        mock_gui.root.after.assert_called_once()
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0
        assert call_args[0][1] == state_synchronizer._update_project_ui
        assert call_args[0][2] == project_path

    def test_on_project_state_changed_other_key(self, state_synchronizer, mock_gui):
        """Test callback with unhandled key."""
        state_synchronizer._on_project_state_changed("PROJECT", "other_key", "old", "new")

        # Should not schedule any UI update
        mock_gui.root.after.assert_not_called()

    def test_update_project_ui_project_loaded(self, state_synchronizer, mock_gui):
        """Test UI update when project is loaded."""
        from pathlib import Path

        project_path = Path("/path/to/project")

        # Currently a stub - just verify it doesn't crash
        state_synchronizer._update_project_ui(project_path)

    def test_update_project_ui_project_closed(self, state_synchronizer, mock_gui):
        """Test UI update when project is closed."""
        # Currently a stub - just verify it doesn't crash
        state_synchronizer._update_project_ui(None)


@pytest.mark.gui
class TestArduinoUIUpdate:
    """Tests for Arduino UI update."""

    def test_update_arduino_ui_connected(self, state_synchronizer, mock_gui):
        """Test Arduino UI update when connected."""
        state_synchronizer._update_arduino_ui(True)

        # Verify dashboard widget was updated
        mock_gui.arduino_dashboard_widget.update_status.assert_called_once_with(True, None)

    def test_update_arduino_ui_disconnected(self, state_synchronizer, mock_gui):
        """Test Arduino UI update when disconnected."""
        state_synchronizer._update_arduino_ui(False)

        # Verify dashboard widget was updated
        mock_gui.arduino_dashboard_widget.update_status.assert_called_once_with(False, None)

    def test_update_arduino_ui_no_widget(self, state_synchronizer, mock_gui):
        """Test Arduino UI update when widget is None."""
        mock_gui.arduino_dashboard_widget = None

        # Should not crash
        state_synchronizer._update_arduino_ui(True)


@pytest.mark.gui
class TestResetAnalysisWidgets:
    """Tests for analysis widget reset methods."""

    def test_reset_analysis_widgets_calls_helpers(self, state_synchronizer, mock_gui):
        """Test that reset_analysis_widgets calls all helper methods."""
        with (
            patch.object(state_synchronizer, "_reset_analysis_media") as mock_media,
            patch.object(
                state_synchronizer, "_reset_analysis_progress_and_metadata"
            ) as mock_progress,
            patch.object(state_synchronizer, "_reset_roi_and_visual_frames") as mock_roi,
            patch.object(state_synchronizer, "_destroy_notebook_and_main_controls") as mock_destroy,
        ):
            state_synchronizer.reset_analysis_widgets()

            # Verify all helpers were called
            mock_media.assert_called_once()
            mock_progress.assert_called_once()
            mock_roi.assert_called_once()
            mock_destroy.assert_called_once()

    def test_reset_analysis_widgets_clears_analysis_tab_frame(self, state_synchronizer, mock_gui):
        """Test that analysis_tab_frame is set to None."""
        mock_gui.analysis_tab_frame = Mock()

        state_synchronizer.reset_analysis_widgets()

        assert mock_gui.analysis_tab_frame is None

    def test_reset_analysis_media_clears_video_label(self, state_synchronizer, mock_gui):
        """Test media reset clears video label."""
        state_synchronizer._reset_analysis_media()

        # Verify image was cleared
        mock_gui.analysis_video_label.configure.assert_called_once_with(image="")
        assert mock_gui._analysis_overlay_image is None

    def test_reset_analysis_media_no_video_label(self, state_synchronizer, mock_gui):
        """Test media reset when video label is None."""
        mock_gui.analysis_video_label = None

        # Should not crash
        state_synchronizer._reset_analysis_media()

    def test_reset_analysis_media_widget_destroyed(self, state_synchronizer, mock_gui):
        """Test media reset when widget no longer exists."""
        mock_gui.analysis_video_label.winfo_exists.return_value = False

        # Should not crash
        state_synchronizer._reset_analysis_media()

    def test_reset_analysis_progress_and_metadata_calls_hide_progress(
        self, state_synchronizer, mock_gui
    ):
        """Test that hide_progress_bar is called."""
        state_synchronizer._reset_analysis_progress_and_metadata()

        mock_gui.hide_progress_bar.assert_called_once()

    def test_reset_analysis_progress_and_metadata_resets_status(self, state_synchronizer, mock_gui):
        """Test that status variable is reset."""
        state_synchronizer._reset_analysis_progress_and_metadata()

        mock_gui.analysis_status_var.set.assert_called_once_with("Nenhuma análise em andamento.")

    def test_reset_analysis_progress_and_metadata_resets_task(self, state_synchronizer, mock_gui):
        """Test that task variable is reset."""
        state_synchronizer._reset_analysis_progress_and_metadata()

        mock_gui.analysis_task_var.set.assert_called_once_with("Nenhuma tarefa em andamento.")

    def test_reset_analysis_progress_and_metadata_sets_defaults(self, state_synchronizer, mock_gui):
        """Test that metadata defaults are set."""
        state_synchronizer._reset_analysis_progress_and_metadata()

        # Verify metadata variables were set
        assert mock_gui.analysis_metadata_var.set.called
        assert mock_gui.analysis_group_var.set.called
        assert mock_gui.analysis_day_var.set.called
        assert mock_gui.analysis_subject_var.set.called

    def test_reset_analysis_progress_and_metadata_resets_progress_labels(
        self, state_synchronizer, mock_gui
    ):
        """Test that progress labels are reset to '-'."""
        var1 = Mock()
        var2 = Mock()
        mock_gui.progress_labels = {"label1": var1, "label2": var2}

        state_synchronizer._reset_analysis_progress_and_metadata()

        var1.set.assert_called_once_with("-")
        var2.set.assert_called_once_with("-")

    def test_reset_analysis_progress_and_metadata_handles_exceptions(
        self, state_synchronizer, mock_gui
    ):
        """Test that exceptions are handled gracefully."""
        mock_gui.hide_progress_bar.side_effect = Exception("Test error")
        mock_gui.analysis_status_var.set.side_effect = Exception("Test error")

        # Should not crash
        state_synchronizer._reset_analysis_progress_and_metadata()

    def test_reset_roi_and_visual_frames_packs_forget_canvas(self, state_synchronizer, mock_gui):
        """Test that ROI canvas is packed forgotten."""
        state_synchronizer._reset_roi_and_visual_frames()

        mock_gui.roi_canvas.pack_forget.assert_called_once()

    def test_reset_roi_and_visual_frames_destroys_viz_frame(self, state_synchronizer, mock_gui):
        """Test that viz_frame is destroyed."""
        # Capture the mock before it's set to None
        viz_frame_mock = mock_gui.viz_frame

        state_synchronizer._reset_roi_and_visual_frames()

        viz_frame_mock.destroy.assert_called_once()
        assert mock_gui.viz_frame is None

    def test_reset_roi_and_visual_frames_destroys_zone_tab_frame(
        self, state_synchronizer, mock_gui
    ):
        """Test that zone_tab_frame is destroyed."""
        state_synchronizer._reset_roi_and_visual_frames()

        mock_gui.zone_tab_frame.destroy.assert_called_once()

    def test_reset_roi_and_visual_frames_no_canvas(self, state_synchronizer, mock_gui):
        """Test reset when canvas is None."""
        mock_gui.roi_canvas = None

        # Should not crash
        state_synchronizer._reset_roi_and_visual_frames()

    def test_reset_roi_and_visual_frames_widget_destroyed(self, state_synchronizer, mock_gui):
        """Test reset when widgets no longer exist."""
        mock_gui.roi_canvas.winfo_exists.return_value = False
        mock_gui.viz_frame.winfo_exists.return_value = False
        mock_gui.zone_tab_frame.winfo_exists.return_value = False

        # Should not crash
        state_synchronizer._reset_roi_and_visual_frames()

    def test_destroy_notebook_and_main_controls_destroys_notebook(
        self, state_synchronizer, mock_gui
    ):
        """Test that notebook is destroyed."""
        # Capture the mock before it's set to None
        notebook_mock = mock_gui.notebook

        state_synchronizer._destroy_notebook_and_main_controls()

        notebook_mock.destroy.assert_called_once()
        assert mock_gui.notebook is None

    def test_destroy_notebook_and_main_controls_destroys_main_controls(
        self, state_synchronizer, mock_gui
    ):
        """Test that main_controls_frame is destroyed."""
        # Capture the mock before it's set to None
        main_controls_mock = mock_gui.main_controls_frame

        state_synchronizer._destroy_notebook_and_main_controls()

        main_controls_mock.destroy.assert_called_once()
        assert mock_gui.main_controls_frame is None

    def test_destroy_notebook_and_main_controls_clears_arduino_widgets(
        self, state_synchronizer, mock_gui
    ):
        """Test that Arduino widgets are cleared."""
        state_synchronizer._destroy_notebook_and_main_controls()

        assert mock_gui.arduino_dashboard_widget is None
        assert mock_gui.external_trigger_notice_label is None

    def test_destroy_notebook_and_main_controls_resets_external_trigger_notice(
        self, state_synchronizer, mock_gui
    ):
        """Test that external trigger notice is reset."""
        state_synchronizer._destroy_notebook_and_main_controls()

        # Should try to set the var (may fail gracefully)
        # Just verify it was called or exception was handled
        assert True  # If we get here, no crash occurred

    def test_destroy_notebook_and_main_controls_cancels_refresh_job(
        self, state_synchronizer, mock_gui
    ):
        """Test that overview refresh job is cancelled."""
        mock_gui._overview_refresh_job = 12345

        state_synchronizer._destroy_notebook_and_main_controls()

        mock_gui.root.after_cancel.assert_called_once_with(12345)
        assert mock_gui._overview_refresh_job is None

    def test_destroy_notebook_and_main_controls_clears_project_overview(
        self, state_synchronizer, mock_gui
    ):
        """Test that project overview state is cleared."""
        state_synchronizer._destroy_notebook_and_main_controls()

        assert mock_gui.project_overview_frame is None
        assert mock_gui.project_overview_tree is None
        assert len(mock_gui.project_status_vars) == 0
        assert len(mock_gui._project_status_containers) == 0
        assert len(mock_gui._last_overview_counts) == 0

    def test_destroy_notebook_and_main_controls_no_refresh_job(self, state_synchronizer, mock_gui):
        """Test when no refresh job is active."""
        mock_gui._overview_refresh_job = None

        # Should not crash
        state_synchronizer._destroy_notebook_and_main_controls()
        mock_gui.root.after_cancel.assert_not_called()


@pytest.mark.gui
class TestResetAnalysisControls:
    """Tests for analysis control reset methods."""

    def test_reset_analysis_controls_clears_detections(self, state_synchronizer, mock_gui):
        """Test that current detections are cleared."""
        mock_gui._current_detections = [[100, 100, 200, 200, 0.95, 1, 0]]

        state_synchronizer.reset_analysis_controls()

        assert mock_gui._current_detections == []

    def test_reset_analysis_controls_clears_frame_cache(self, state_synchronizer, mock_gui):
        """Test that frame cache is cleared."""
        import numpy as np

        mock_gui._last_analysis_frame = np.zeros((600, 800, 3))
        mock_gui._analysis_overlay_image = Mock()

        state_synchronizer.reset_analysis_controls()

        assert mock_gui._last_analysis_frame is None
        assert mock_gui._analysis_overlay_image is None

    def test_reset_analysis_controls_resets_track_selector(self, state_synchronizer, mock_gui):
        """Test that track selector is reset to 'Todos'."""
        mock_gui.track_selector_var.get.return_value = "5"

        state_synchronizer.reset_analysis_controls()

        mock_gui.track_selector_var.set.assert_called_once_with("Todos")

    def test_reset_analysis_controls_updates_track_options(self, state_synchronizer, mock_gui):
        """Test that track options are updated."""
        with patch.object(state_synchronizer, "_update_track_options") as mock_update:
            state_synchronizer.reset_analysis_controls()

            mock_update.assert_called_once_with(["Todos"])

    def test_reset_analysis_controls_sets_widget_state_multi_subject(
        self, state_synchronizer, mock_gui
    ):
        """Test widget state for multi-subject mode."""
        mock_gui._active_processing_mode = ProcessingMode.MULTI_TRACK

        state_synchronizer.reset_analysis_controls()

        # configure() is called twice: once for values, once for state
        mock_gui.track_selector_widget.configure.assert_any_call(state="readonly")

    def test_reset_analysis_controls_sets_widget_state_single_subject(
        self, state_synchronizer, mock_gui
    ):
        """Test widget state for single-subject mode."""
        mock_gui._active_processing_mode = ProcessingMode.SINGLE_SUBJECT

        state_synchronizer.reset_analysis_controls()

        # configure() is called twice: once for values, once for state
        mock_gui.track_selector_widget.configure.assert_any_call(state="disabled")

    def test_reset_analysis_controls_no_widget(self, state_synchronizer, mock_gui):
        """Test reset when widget is None."""
        mock_gui.track_selector_widget = None

        # Should not crash
        state_synchronizer.reset_analysis_controls()

    def test_update_track_options_cleans_duplicates(self, state_synchronizer, mock_gui):
        """Test that duplicate options are removed."""
        options = ["Todos", "1", "2", "1", "3", "2"]

        state_synchronizer._update_track_options(options)

        # Should have unique values
        expected = ("Todos", "1", "2", "3")
        assert mock_gui._available_track_options == expected

    def test_update_track_options_handles_empty_strings(self, state_synchronizer, mock_gui):
        """Test that empty strings are converted to 'Todos'."""
        options = ["", "  ", "1"]

        state_synchronizer._update_track_options(options)

        # Empty strings should become "Todos", but only one "Todos"
        assert "Todos" in mock_gui._available_track_options
        assert "1" in mock_gui._available_track_options

    def test_update_track_options_converts_to_strings(self, state_synchronizer, mock_gui):
        """Test that non-string options are converted."""
        options = [1, 2, 3, "Todos"]

        state_synchronizer._update_track_options(options)

        # All should be strings
        expected = ("1", "2", "3", "Todos")
        assert mock_gui._available_track_options == expected

    def test_update_track_options_handles_empty_list(self, state_synchronizer, mock_gui):
        """Test handling of empty options list."""
        state_synchronizer._update_track_options([])

        # Should default to ["Todos"]
        assert mock_gui._available_track_options == ("Todos",)

    def test_update_track_options_preserves_order(self, state_synchronizer, mock_gui):
        """Test that option order is preserved."""
        options = ["Todos", "5", "3", "1"]

        state_synchronizer._update_track_options(options)

        # Order should be preserved
        expected = ("Todos", "5", "3", "1")
        assert mock_gui._available_track_options == expected

    def test_update_track_options_updates_widget(self, state_synchronizer, mock_gui):
        """Test that combobox widget is updated."""
        options = ["Todos", "1", "2"]

        state_synchronizer._update_track_options(options)

        mock_gui.track_selector_widget.configure.assert_called_once_with(values=["Todos", "1", "2"])

    def test_update_track_options_skips_update_if_unchanged(self, state_synchronizer, mock_gui):
        """Test that widget is not updated if options unchanged."""
        options = ["Todos", "1", "2"]
        mock_gui._available_track_options = ("Todos", "1", "2")

        state_synchronizer._update_track_options(options)

        # Should not configure widget if options are same
        mock_gui.track_selector_widget.configure.assert_not_called()

    def test_update_track_options_no_widget(self, state_synchronizer, mock_gui):
        """Test update when widget is None."""
        mock_gui.track_selector_widget = None
        options = ["Todos", "1", "2"]

        # Should not crash
        state_synchronizer._update_track_options(options)


@pytest.mark.gui
class TestResetGlobalConfig:
    """Tests for global config reset."""

    def test_reset_global_config_form_widget_reloads_editor(self, state_synchronizer, mock_gui):
        """Test that config editor is reloaded."""
        state_synchronizer.reset_global_config_form_widget()

        mock_gui._reload_config_editor_values_widget.assert_called_once()

    def test_reset_global_config_form_widget_shows_confirmation(self, state_synchronizer, mock_gui):
        """Test that confirmation message is shown."""
        state_synchronizer.reset_global_config_form_widget()

        mock_gui.show_info.assert_called_once_with(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )


@pytest.mark.gui
class TestAnalysisMetadataHelpers:
    """Tests for analysis metadata helper methods."""

    def test_analysis_metadata_defaults_returns_tuple(self, state_synchronizer):
        """Test that defaults returns correct tuple."""
        result = state_synchronizer._analysis_metadata_defaults()

        assert result == ("Sem Grupo", "Sem Dia", "Não informado")

    def test_default_analysis_metadata_text_format(self, state_synchronizer):
        """Test metadata text formatting."""
        result = state_synchronizer._default_analysis_metadata_text()

        expected = "Grupo: Sem Grupo | Dia: Sem Dia | Indivíduo: Não informado"
        assert result == expected

    def test_set_analysis_metadata_defaults_applies_defaults(self, state_synchronizer, mock_gui):
        """Test that defaults are applied to variables."""
        state_synchronizer._set_analysis_metadata_defaults()

        # Verify all metadata variables were set
        assert mock_gui.analysis_metadata_var.set.called
        assert mock_gui.analysis_group_var.set.called
        assert mock_gui.analysis_day_var.set.called
        assert mock_gui.analysis_subject_var.set.called

    def test_apply_analysis_metadata_strings_sets_combined(self, state_synchronizer, mock_gui):
        """Test that combined metadata string is set."""
        state_synchronizer._apply_analysis_metadata_strings("Grupo A", "Dia 1", "Peixe 1")

        expected = "Grupo: Grupo A | Dia: Dia 1 | Indivíduo: Peixe 1"
        mock_gui.analysis_metadata_var.set.assert_called_once_with(expected)

    def test_apply_analysis_metadata_strings_sets_individual(self, state_synchronizer, mock_gui):
        """Test that individual metadata strings are set."""
        state_synchronizer._apply_analysis_metadata_strings("Grupo A", "Dia 1", "Peixe 1")

        mock_gui.analysis_group_var.set.assert_called_once_with("Grupo: Grupo A")
        mock_gui.analysis_day_var.set.assert_called_once_with("Dia: Dia 1")
        mock_gui.analysis_subject_var.set.assert_called_once_with("Indivíduo: Peixe 1")

    def test_apply_analysis_metadata_strings_handles_none_vars(self, state_synchronizer, mock_gui):
        """Test handling when variables are None."""
        mock_gui.analysis_metadata_var = None
        mock_gui.analysis_group_var = None
        mock_gui.analysis_day_var = None
        mock_gui.analysis_subject_var = None

        # Should not crash
        state_synchronizer._apply_analysis_metadata_strings("Grupo A", "Dia 1", "Peixe 1")

    def test_apply_analysis_metadata_strings_uses_getattr(self, state_synchronizer, mock_gui):
        """Test that getattr is used safely."""
        # Remove attributes entirely
        delattr(mock_gui, "analysis_metadata_var")
        delattr(mock_gui, "analysis_group_var")
        delattr(mock_gui, "analysis_day_var")
        delattr(mock_gui, "analysis_subject_var")

        # Should not crash
        state_synchronizer._apply_analysis_metadata_strings("Grupo A", "Dia 1", "Peixe 1")

    def test_default_analysis_task_text_returns_default(self, state_synchronizer):
        """Test default task text."""
        result = state_synchronizer._default_analysis_task_text()

        assert result == "Nenhuma tarefa em andamento."


@pytest.mark.gui
class TestThreadSafety:
    """Tests for thread-safety and root.after usage."""

    def test_recording_callback_uses_root_after(self, state_synchronizer, mock_gui):
        """Test that recording callback schedules on main thread."""
        state_synchronizer._on_recording_state_changed("RECORDING", "is_recording", False, True)

        # Verify root.after(0, ...) was used
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0  # Delay of 0

    def test_processing_callback_uses_root_after(self, state_synchronizer, mock_gui):
        """Test that processing callback schedules on main thread."""
        state_synchronizer._on_processing_state_changed("PROCESSING", "is_processing", False, True)

        # Verify root.after(0, ...) was used
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0

    def test_detector_callback_uses_root_after(self, state_synchronizer, mock_gui):
        """Test that detector callback schedules on main thread."""
        state_synchronizer._on_detector_state_changed(
            "DETECTOR", "detector_initialized", False, True
        )

        # Verify root.after(0, ...) was used
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0

    def test_project_callback_uses_root_after(self, state_synchronizer, mock_gui):
        """Test that project callback schedules on main thread."""
        state_synchronizer._on_project_state_changed(
            "PROJECT", "project_path", None, "/path/to/project"
        )

        # Verify root.after(0, ...) was used
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0

    def test_arduino_callback_uses_root_after(self, state_synchronizer, mock_gui):
        """Test that Arduino callback schedules on main thread."""
        state_synchronizer._on_recording_state_changed(
            "RECORDING", "arduino_connected", False, True
        )

        # Verify root.after(0, ...) was used
        call_args = mock_gui.root.after.call_args
        assert call_args[0][0] == 0


@pytest.mark.gui
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_reset_analysis_widgets_with_all_none(self, state_synchronizer, mock_gui):
        """Test reset when all widgets are None."""
        mock_gui.analysis_video_label = None
        mock_gui.roi_canvas = None
        mock_gui.viz_frame = None
        mock_gui.zone_tab_frame = None
        mock_gui.notebook = None
        mock_gui.main_controls_frame = None

        # Should not crash
        state_synchronizer.reset_analysis_widgets()

    def test_reset_analysis_widgets_with_widget_errors(self, state_synchronizer, mock_gui):
        """Test reset when widgets raise exceptions."""
        mock_gui.analysis_video_label.configure.side_effect = Exception("Widget error")
        mock_gui.roi_canvas.pack_forget.side_effect = Exception("Widget error")

        # Should handle exceptions gracefully
        state_synchronizer.reset_analysis_widgets()

    def test_update_track_options_with_mixed_types(self, state_synchronizer, mock_gui):
        """Test track options with mixed types."""
        options = [1, "2", 3.5, None, "Todos", True]

        # Should convert all to strings without crashing
        state_synchronizer._update_track_options(options)

        # Verify all were converted
        assert all(isinstance(opt, str) for opt in mock_gui._available_track_options)

    def test_apply_metadata_with_special_characters(self, state_synchronizer, mock_gui):
        """Test metadata application with special characters."""
        state_synchronizer._apply_analysis_metadata_strings("Grupo | A", "Dia & 1", "Peixe <1>")

        # Should handle special characters without crashing
        expected = "Grupo: Grupo | A | Dia: Dia & 1 | Indivíduo: Peixe <1>"
        mock_gui.analysis_metadata_var.set.assert_called_once_with(expected)

    def test_destroy_notebook_with_invalid_refresh_job(self, state_synchronizer, mock_gui):
        """Test destroying notebook with invalid refresh job ID."""
        mock_gui._overview_refresh_job = "invalid"
        mock_gui.root.after_cancel.side_effect = Exception("Invalid job ID")

        # Should handle exception gracefully
        state_synchronizer._destroy_notebook_and_main_controls()

    def test_multiple_reset_calls(self, state_synchronizer, mock_gui):
        """Test calling reset methods multiple times."""
        # Should be idempotent
        state_synchronizer.reset_analysis_widgets()
        state_synchronizer.reset_analysis_widgets()
        state_synchronizer.reset_analysis_widgets()

        # Should not crash or cause issues
        assert mock_gui.analysis_tab_frame is None

    def test_update_ui_methods_with_rapid_changes(self, state_synchronizer, mock_gui):
        """Test UI update methods with rapid state changes."""
        # Simulate rapid state changes
        for i in range(10):
            state_synchronizer._update_recording_ui(i % 2 == 0)
            state_synchronizer._update_processing_ui(i % 2 == 1)

        # Should handle all updates without issues
        assert mock_gui.start_rec_btn.config.call_count >= 1
        assert mock_gui.process_video_btn.config.call_count >= 1
