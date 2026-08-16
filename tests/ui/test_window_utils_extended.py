"""Extended unit tests for ui/window_utils.py cross-platform window management."""

from __future__ import annotations

import tkinter as tk
from tkinter import TclError
from unittest.mock import MagicMock, patch

from zebtrack.ui.window_utils import (
    _clear_ttkbootstrap_style,
    _try_actions,
    _ttkbootstrap_style_needs_reset,
    create_scrollbar,
    maximize_window,
    reset_geometry_if_not_maximized,
    schedule_maximize,
    set_geometry_if_not_maximized,
)


class TestWindowUtilsExtended:
    """Test window maximization, geometry management, and scrollbar resilience."""

    def test_try_actions_first_succeeds(self):
        action1 = MagicMock()
        action2 = MagicMock()
        result = _try_actions(None, (action1, action2))
        assert result is True
        action1.assert_called_once()
        action2.assert_not_called()

    def test_try_actions_second_succeeds(self):
        action1 = MagicMock(side_effect=TclError("Fail 1"))
        action2 = MagicMock()
        result = _try_actions(None, (action1, action2))
        assert result is True
        action1.assert_called_once()
        action2.assert_called_once()

    def test_try_actions_all_fail(self):
        action1 = MagicMock(side_effect=TclError("Fail 1"))
        action2 = MagicMock(side_effect=Exception("Fail 2"))
        result = _try_actions(None, (action1, action2))
        assert result is False

    def test_maximize_window_state_zoomed_succeeds(self):
        mock_win = MagicMock()
        maximize_window(mock_win)
        mock_win.update_idletasks.assert_called_once()
        mock_win.state.assert_called_with("zoomed")

    def test_maximize_window_fallback_to_geometry(self):
        mock_win = MagicMock()
        mock_win.state.side_effect = TclError("Zoomed not supported")
        mock_win.attributes.side_effect = TclError("Attributes not supported")
        mock_win.winfo_screenwidth.return_value = 1920
        mock_win.winfo_screenheight.return_value = 1080

        maximize_window(mock_win)
        mock_win.geometry.assert_called_once_with("1920x1080+0+0")

    def test_maximize_window_update_idletasks_error_handled(self):
        mock_win = MagicMock()
        mock_win.update_idletasks.side_effect = TclError("Destroyed")
        maximize_window(mock_win)

    def test_schedule_maximize(self):
        mock_win = MagicMock()
        schedule_maximize(mock_win)
        mock_win.after.assert_called_once()

    def test_schedule_maximize_tcl_error_handled(self):
        mock_win = MagicMock()
        mock_win.after.side_effect = TclError("Window destroyed")
        schedule_maximize(mock_win)

    def test_reset_geometry_when_zoomed_does_nothing(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "zoomed"
        reset_geometry_if_not_maximized(mock_win)
        mock_win.geometry.assert_not_called()

    def test_reset_geometry_when_normal_clears_geometry(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "normal"
        reset_geometry_if_not_maximized(mock_win)
        mock_win.geometry.assert_called_once_with("")

    def test_reset_geometry_state_tcl_error_handled(self):
        mock_win = MagicMock()
        mock_win.state.side_effect = TclError("Fail")
        reset_geometry_if_not_maximized(mock_win)
        mock_win.geometry.assert_called_once_with("")

    def test_set_geometry_when_zoomed_does_nothing(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "zoomed"
        set_geometry_if_not_maximized(mock_win, "800x600")
        mock_win.geometry.assert_not_called()

    def test_set_geometry_when_normal_applies_geometry(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "normal"
        set_geometry_if_not_maximized(mock_win, "800x600")
        mock_win.geometry.assert_called_once_with("800x600")

    def test_ttkbootstrap_style_needs_reset_when_none(self):
        with patch("zebtrack.ui.window_utils.ttkb", None):
            assert _ttkbootstrap_style_needs_reset() is False

    def test_clear_ttkbootstrap_style_when_none(self):
        with patch("zebtrack.ui.window_utils.ttkb", None):
            _clear_ttkbootstrap_style()  # should not raise

    def test_create_scrollbar(self, tkinter_root: tk.Tk):
        scrollbar = create_scrollbar(tkinter_root, orient="vertical")
        assert scrollbar is not None
