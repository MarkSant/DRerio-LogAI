"""Extended unit tests for ui/components/dialog_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.dialog_manager import DialogManager


class TestDialogManagerExtended2:
    """Test DialogManager suppression, message boxes, and delete mode logic."""

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
