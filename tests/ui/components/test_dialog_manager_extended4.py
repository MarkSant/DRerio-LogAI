"""Extended unit tests for ui/components/dialog_manager.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended4:
    """Test DialogManager batch suppression for error, warning, info, and status bar."""

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
