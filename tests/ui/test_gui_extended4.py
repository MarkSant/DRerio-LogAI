"""Extended unit tests for ui/gui.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.ui.gui import ApplicationGUI


class TestGuiExtended4:
    """Test ApplicationGUI button state updater, progress bar, and dialog popups."""

    def test_update_button_state_buttons(self):
        gui = object.__new__(ApplicationGUI)
        gui.start_rec_btn = MagicMock()
        gui.stop_rec_btn = MagicMock()
        gui.process_video_btn = MagicMock()
        gui.analysis_display_widget = MagicMock()

        gui.update_button_state("start_rec", "disabled")
        gui.start_rec_btn.config.assert_called_once_with(state="disabled")

        gui.update_button_state("stop_rec", "normal")
        gui.stop_rec_btn.config.assert_called_once_with(state="normal")

        gui.update_button_state("process_video", "disabled")
        gui.process_video_btn.config.assert_called_once_with(state="disabled")

        gui.update_button_state("cancel_processing", "normal")
        gui.analysis_display_widget.enable_cancel_button.assert_called_once()

        gui.update_button_state("cancel_processing", "disabled")
        gui.analysis_display_widget.disable_cancel_button.assert_called_once()

    def test_hide_progress_bar(self):
        gui = object.__new__(ApplicationGUI)
        gui.analysis_display_widget = MagicMock()
        gui.hide_progress_bar()
        gui.analysis_display_widget.hide_progress.assert_called_once()

    @patch("zebtrack.ui.gui.messagebox.showinfo")
    def test_show_info_delegates(self, mock_info: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_info("Title", "Message")
        mock_info.assert_called_once_with("Title", "Message")

    @patch("zebtrack.ui.gui.messagebox.showwarning")
    def test_show_warning_delegates(self, mock_warn: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_warning("Warning Title", "Warning Message")
        mock_warn.assert_called_once_with("Warning Title", "Warning Message")

    @patch("zebtrack.ui.gui.messagebox.showerror")
    def test_show_error_delegates(self, mock_err: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_error("Error Title", "Error Message")
        mock_err.assert_called_once_with("Error Title", "Error Message")
