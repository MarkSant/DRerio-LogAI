"""Extended unit tests for ui/components/dialog_manager.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended5:
    """Test DialogManager delete mode choices and yes/no confirmations."""

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
