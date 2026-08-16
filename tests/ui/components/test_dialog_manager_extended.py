"""Extended unit tests for ui/components/dialog_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended:
    """Test DialogManager suppression, messageboxes, and confirmations."""

    def test_init_and_zone_context_service_property(self):
        mock_gui = MagicMock()
        mock_svc = MagicMock()
        dm = DialogManager(mock_gui, zone_context_service=mock_svc)
        assert dm.gui is mock_gui
        assert dm.zone_context_service is mock_svc

    def test_zone_context_service_fallback_to_gui(self):
        mock_gui = MagicMock()
        mock_gui._zone_context_service = MagicMock()
        dm = DialogManager(mock_gui)
        assert dm.zone_context_service is mock_gui._zone_context_service

    def test_dialog_suppression_toggle(self):
        dm = DialogManager(MagicMock())
        assert dm._suppress_batch_dialogs is False

        dm.set_dialog_suppression(True)
        assert dm._suppress_batch_dialogs is True

        dm.set_dialog_suppression(False)
        assert dm._suppress_batch_dialogs is False

    @patch("tkinter.messagebox.showerror")
    def test_show_error_unsuppressed(self, mock_showerror):
        dm = DialogManager(MagicMock())
        dm.show_error("Error Title", "Something failed")
        mock_showerror.assert_called_once_with("Error Title", "Something failed")

    @patch("tkinter.messagebox.showerror")
    def test_show_error_suppressed(self, mock_showerror):
        mock_gui = MagicMock()
        dm = DialogManager(mock_gui)
        dm.set_dialog_suppression(True)

        dm.show_error("Error Title", "Something failed")
        mock_showerror.assert_not_called()
        mock_gui.status_var.set.assert_called_once()

    @patch("tkinter.messagebox.showwarning")
    def test_show_warning_unsuppressed(self, mock_showwarning):
        dm = DialogManager(MagicMock())
        dm.show_warning("Warning Title", "Careful")
        mock_showwarning.assert_called_once_with("Warning Title", "Careful")

    @patch("tkinter.messagebox.showwarning")
    def test_show_warning_suppressed(self, mock_showwarning):
        mock_gui = MagicMock()
        dm = DialogManager(mock_gui)
        dm.set_dialog_suppression(True)

        dm.show_warning("Warning Title", "Careful")
        mock_showwarning.assert_not_called()
        mock_gui.status_var.set.assert_called_once()

    @patch("tkinter.messagebox.showinfo")
    def test_show_info_unsuppressed(self, mock_showinfo):
        dm = DialogManager(MagicMock())
        dm.show_info("Info Title", "Process completed")
        mock_showinfo.assert_called_once_with("Info Title", "Process completed")

    @patch("tkinter.messagebox.showinfo")
    def test_show_info_suppressed(self, mock_showinfo):
        mock_gui = MagicMock()
        dm = DialogManager(mock_gui)
        dm.set_dialog_suppression(True)

        dm.show_info("Info Title", "Process completed")
        mock_showinfo.assert_not_called()
        mock_gui.status_var.set.assert_called_once()

    @patch("tkinter.messagebox.askyesno", return_value=True)
    def test_ask_yes_no_returns_bool(self, mock_askyesno):
        dm = DialogManager(MagicMock())
        result = dm.ask_yes_no("Question", "Do you want to continue?")
        assert result is True
        mock_askyesno.assert_called_once_with(
            "Question", "Do you want to continue?", icon="question"
        )

    @patch("tkinter.messagebox.askokcancel", return_value=False)
    def test_ask_ok_cancel_returns_bool(self, mock_askokcancel):
        dm = DialogManager(MagicMock())
        result = dm.ask_ok_cancel("Confirm", "Proceed with operation?")
        assert result is False
        mock_askokcancel.assert_called_once_with("Confirm", "Proceed with operation?")

    @patch("tkinter.simpledialog.askstring", return_value="user_input")
    def test_ask_string(self, mock_askstring):
        dm = DialogManager(MagicMock())
        result = dm.ask_string("Input Required", "Enter group name:")
        assert result == "user_input"

    def test_node_type_labels(self):
        labels = DialogManager._node_type_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels

    @patch.object(DialogManager, "ask_yes_no_cancel", return_value=True)
    def test_choose_processing_reports_delete_mode_project(self, mock_ask):
        dm = DialogManager(MagicMock())
        mode = dm.choose_processing_reports_delete_mode("Video 1")
        assert mode == "project"

    @patch.object(DialogManager, "ask_yes_no_cancel", return_value=False)
    def test_choose_processing_reports_delete_mode_data(self, mock_ask):
        dm = DialogManager(MagicMock())
        mode = dm.choose_processing_reports_delete_mode("Video 1")
        assert mode == "data"

    @patch.object(DialogManager, "ask_yes_no_cancel", return_value=None)
    def test_choose_processing_reports_delete_mode_cancel(self, mock_ask):
        dm = DialogManager(MagicMock())
        mode = dm.choose_processing_reports_delete_mode("Video 1")
        assert mode is None
