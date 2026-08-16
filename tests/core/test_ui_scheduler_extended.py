"""
Extended unit tests for UIScheduler.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.core.ui_scheduler import UIScheduler


class TestUISchedulerExtended:
    """Test UIScheduler scheduling, convenience methods, and fallback logic."""

    def test_schedule_with_no_root_falls_back_to_direct_call(self):
        called: list[str] = []
        scheduler = UIScheduler(root=None)
        scheduler.schedule(called.append, "hello")
        assert called == ["hello"]

    def test_schedule_with_root_uses_after(self):
        mock_root = MagicMock()
        scheduler = UIScheduler(root=mock_root)
        fn = MagicMock()
        scheduler.schedule(fn, 1, 2)
        mock_root.after.assert_called_once()
        # The after call is (0, lambda) - invoke the lambda to verify fn is called
        lam = mock_root.after.call_args[0][1]
        lam()
        fn.assert_called_once_with(1, 2)

    def test_schedule_with_root_tcl_error_falls_back_to_direct(self):
        mock_root = MagicMock()
        import tkinter as tk

        mock_root.after.side_effect = tk.TclError("dead window")
        called: list[str] = []
        scheduler = UIScheduler(root=mock_root)
        scheduler.schedule(called.append, "fallback")
        assert called == ["fallback"]

    def test_schedule_after_no_root_returns_none(self):
        scheduler = UIScheduler(root=None)
        result = scheduler.schedule_after(100, MagicMock())
        assert result is None

    def test_schedule_after_with_root(self):
        mock_root = MagicMock()
        mock_root.after.return_value = "after#1"
        scheduler = UIScheduler(root=mock_root)
        result = scheduler.schedule_after(200, MagicMock())
        assert result == "after#1"

    def test_cancel_scheduled_no_root(self):
        scheduler = UIScheduler(root=None)
        scheduler.cancel_scheduled("after#1")  # Should not raise

    def test_cancel_scheduled_calls_after_cancel(self):
        mock_root = MagicMock()
        scheduler = UIScheduler(root=mock_root)
        scheduler.cancel_scheduled("after#42")
        mock_root.after_cancel.assert_called_once_with("after#42")

    def test_update_view_none_view_is_no_op(self):
        scheduler = UIScheduler(root=None)
        scheduler.update_view(None, "set_status", "msg")  # Should not raise

    def test_update_view_missing_method_is_no_op(self):
        mock_view = MagicMock(spec=[])  # No methods at all
        scheduler = UIScheduler(root=None)
        scheduler.update_view(mock_view, "nonexistent_method")  # Should not raise

    def test_update_view_calls_method_directly(self):
        mock_view = MagicMock()
        scheduler = UIScheduler(root=None)
        scheduler.update_view(mock_view, "set_status", "Processing...")
        mock_view.set_status.assert_called_once_with("Processing...")

    def test_set_status_delegates_to_update_view(self):
        mock_view = MagicMock()
        scheduler = UIScheduler(root=None)
        scheduler.set_status(mock_view, "Done")
        mock_view.set_status.assert_called_once_with("Done")

    def test_update_progress(self):
        mock_view = MagicMock()
        scheduler = UIScheduler(root=None)
        scheduler.update_progress(mock_view, 0.75)
        mock_view.update_progress.assert_called_once_with(0.75)

    def test_update_button_state(self):
        mock_view = MagicMock()
        scheduler = UIScheduler(root=None)
        scheduler.update_button_state(mock_view, "start_btn", "disabled")
        mock_view.update_button_state.assert_called_once_with("start_btn", "disabled")

    def test_show_progress_and_hide_progress(self):
        mock_view = MagicMock()
        scheduler = UIScheduler(root=None)
        scheduler.show_progress_bar(mock_view)
        scheduler.hide_progress_bar(mock_view)
        mock_view.show_progress_bar.assert_called_once()
        mock_view.hide_progress_bar.assert_called_once()

    def test_ask_ok_cancel_tcl_error_returns_false(self):
        import tkinter as tk

        scheduler = UIScheduler(root=None)
        with patch("tkinter.messagebox.askokcancel", side_effect=tk.TclError("no display")):
            result = scheduler.ask_ok_cancel("Confirm", "Delete?")
        assert result is False
