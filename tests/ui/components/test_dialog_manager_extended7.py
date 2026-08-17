"""Extended unit tests for ui/components/dialog_manager.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended7:
    """Test DialogManager askyesno and askokcancel confirmation popups."""

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
