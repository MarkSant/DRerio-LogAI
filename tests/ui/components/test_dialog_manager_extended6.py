"""Extended unit tests for ui/components/dialog_manager.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended6:
    """Test DialogManager information, error, and warning popups."""

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
