"""Extended unit tests for ui/components/dialog_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended:
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


class TestDialogManagerExtended2:
    def test_set_dialog_suppression(self):
        gui = MagicMock()
        manager = DialogManager(gui)
        assert manager._suppress_batch_dialogs is False

        manager.set_dialog_suppression(True)
        assert manager._suppress_batch_dialogs is True

        manager.set_dialog_suppression(False)
        assert manager._suppress_batch_dialogs is False

    def test_show_error_suppressed(self):
        gui = MagicMock()
        manager = DialogManager(gui)
        manager.set_dialog_suppression(True)

        manager.show_error("Validation Fail", "Missing polygon coordinates")
        gui.status_var.set.assert_called_once()
        args = gui.status_var.set.call_args[0][0]
        assert "Validation Fail" in args
        assert "Missing polygon coordinates" in args

    def test_show_warning_suppressed(self):
        gui = MagicMock()
        manager = DialogManager(gui)
        manager.set_dialog_suppression(True)

        manager.show_warning("Low FPS", "Camera dropped below 15 fps")
        gui.status_var.set.assert_called_once()
        args = gui.status_var.set.call_args[0][0]
        assert "Low FPS" in args
        assert "Camera dropped below 15 fps" in args

    def test_show_info_suppressed(self):
        gui = MagicMock()
        manager = DialogManager(gui)
        manager.set_dialog_suppression(True)

        manager.show_info("Batch Done", "All 10 videos processed")
        gui.status_var.set.assert_called_once()
        args = gui.status_var.set.call_args[0][0]
        assert "Batch Done" in args
        assert "All 10 videos processed" in args

    def test_update_status_bar_truncation(self):
        gui = MagicMock()
        manager = DialogManager(gui)

        long_text = "A" * 300
        manager._update_status_bar(long_text)
        gui.status_var.set.assert_called_once()
        assert len(gui.status_var.set.call_args[0][0]) == 200

    def test_choose_processing_reports_delete_mode_options(self):
        gui = MagicMock()
        manager = DialogManager(gui)

        # True -> "project"
        manager.ask_yes_no_cancel = MagicMock(return_value=True)  # type: ignore[method-assign]
        assert manager.choose_processing_reports_delete_mode("video1.mp4") == "project"

        # False -> "data"
        manager.ask_yes_no_cancel = MagicMock(return_value=False)  # type: ignore[method-assign]
        assert manager.choose_processing_reports_delete_mode("video1.mp4") == "data"

        # None -> None
        manager.ask_yes_no_cancel = MagicMock(return_value=None)  # type: ignore[method-assign]
        assert manager.choose_processing_reports_delete_mode("video1.mp4") is None

    def test_confirm_delete_processing_data_cancelled(self):
        gui = MagicMock()
        manager = DialogManager(gui)
        manager.ask_yes_no = MagicMock(return_value=False)  # type: ignore[method-assign]

        confirmed, delete_disk = manager.confirm_delete_processing_data(
            "Video 1", 1, ["video1.mp4"]
        )
        assert confirmed is False
        assert delete_disk is False


class TestDialogManagerExtended4:
    def test_show_error_suppressed(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm._suppress_batch_dialogs = True
        mock_status = MagicMock()
        monkeypatch.setattr(dm, "_update_status_bar", mock_status)

        dm.show_error("Disk Error", "Failed to save file")
        mock_status.assert_called_once()
        assert "Disk Error" in mock_status.call_args[0][0]

    def test_show_warning_suppressed(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm._suppress_batch_dialogs = True
        mock_status = MagicMock()
        monkeypatch.setattr(dm, "_update_status_bar", mock_status)

        dm.show_warning("Low Memory", "RAM usage is high")
        mock_status.assert_called_once()
        assert "Low Memory" in mock_status.call_args[0][0]

    def test_show_info_suppressed(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm._suppress_batch_dialogs = True
        mock_status = MagicMock()
        monkeypatch.setattr(dm, "_update_status_bar", mock_status)

        dm.show_info("Done", "Process complete")
        mock_status.assert_called_once_with("Done: Process complete")

    def test_update_status_bar_truncation(self):
        gui = MagicMock()
        dm = DialogManager(gui)
        long_message = "A" * 300

        dm._update_status_bar(long_message)
        gui.status_var.set.assert_called_once_with("A" * 200)


class TestDialogManagerExtended5:
    def test_choose_processing_reports_delete_mode_project(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        monkeypatch.setattr(dm, "ask_yes_no_cancel", lambda *args, **kwargs: True)

        mode = dm.choose_processing_reports_delete_mode("Item1", target_kind="session")
        assert mode == "project"

    def test_choose_processing_reports_delete_mode_data(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        monkeypatch.setattr(dm, "ask_yes_no_cancel", lambda *args, **kwargs: False)

        mode = dm.choose_processing_reports_delete_mode("Item1", target_kind="session")
        assert mode == "data"

    def test_choose_processing_reports_delete_mode_cancel(self, monkeypatch: pytest.MonkeyPatch):
        gui = MagicMock()
        dm = DialogManager(gui)
        monkeypatch.setattr(dm, "ask_yes_no_cancel", lambda *args, **kwargs: None)

        mode = dm.choose_processing_reports_delete_mode("Item1", target_kind="session")
        assert mode is None

    @patch("zebtrack.ui.components.dialog_manager.messagebox.askokcancel")
    def test_ask_ok_cancel_delegates(self, mock_ask: MagicMock):
        gui = MagicMock()
        dm = DialogManager(gui)
        mock_ask.return_value = True

        assert dm.ask_ok_cancel("Confirm", "Are you sure?") is True
        mock_ask.assert_called_once_with("Confirm", "Are you sure?")


class TestDialogManagerExtended6:
    @patch("zebtrack.ui.components.dialog_manager.messagebox.showinfo")
    def test_show_info_delegation(self, mock_showinfo: MagicMock):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm.show_info("Hello", "World")

        mock_showinfo.assert_called_once_with("Hello", "World")

    @patch("zebtrack.ui.components.dialog_manager.messagebox.showwarning")
    def test_show_warning_delegation(self, mock_showwarning: MagicMock):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm.show_warning("Notice", "Warning text")

        mock_showwarning.assert_called_once_with("Notice", "Warning text")

    @patch("zebtrack.ui.components.dialog_manager.messagebox.showerror")
    def test_show_error_delegation(self, mock_showerror: MagicMock):
        gui = MagicMock()
        dm = DialogManager(gui)
        dm.show_error("Critical", "Error message")

        mock_showerror.assert_called_once_with("Critical", "Error message")


class TestDialogManagerExtended7:
    @patch("zebtrack.ui.components.dialog_manager.messagebox.askyesno")
    def test_ask_yes_no_delegation(self, mock_askyesno: MagicMock):
        mock_askyesno.return_value = True
        gui = MagicMock()
        dm = DialogManager(gui)

        res = dm.ask_yes_no("Confirm", "Are you sure?")
        assert res is True
        mock_askyesno.assert_called_once_with("Confirm", "Are you sure?", icon="question")

    @patch("zebtrack.ui.components.dialog_manager.messagebox.askokcancel")
    def test_ask_ok_cancel_delegation(self, mock_askokcancel: MagicMock):
        mock_askokcancel.return_value = False
        gui = MagicMock()
        dm = DialogManager(gui)

        res = dm.ask_ok_cancel("Proceed", "Do you want to proceed?")
        assert res is False
        mock_askokcancel.assert_called_once_with("Proceed", "Do you want to proceed?")

    def test_dialog_manager_gui_reference(self):
        gui = MagicMock()
        dm = DialogManager(gui)
        assert dm.gui is gui
