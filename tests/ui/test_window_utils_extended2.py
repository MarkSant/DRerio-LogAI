"""Extended unit tests for ui/window_utils.py."""

from __future__ import annotations

from tkinter import TclError
from unittest.mock import MagicMock

from zebtrack.ui.window_utils import (
    _clear_ttkbootstrap_style,
    _try_actions,
    _ttkbootstrap_style_needs_reset,
    reset_geometry_if_not_maximized,
    set_geometry_if_not_maximized,
)


class TestWindowUtilsExtended2:
    """Test cross-platform window management and ttkbootstrap resilience."""

    def test_try_actions_first_succeeds(self):
        act1 = MagicMock()
        act2 = MagicMock()
        res = _try_actions(None, (act1, act2))
        assert res is True
        act1.assert_called_once()
        act2.assert_not_called()

    def test_try_actions_first_fails_second_succeeds(self):
        act1 = MagicMock(side_effect=TclError("fail"))
        act2 = MagicMock()
        res = _try_actions(None, (act1, act2))
        assert res is True
        act1.assert_called_once()
        act2.assert_called_once()

    def test_try_actions_all_fail(self):
        act1 = MagicMock(side_effect=TclError("fail1"))
        act2 = MagicMock(side_effect=RuntimeError("fail2"))
        res = _try_actions(None, (act1, act2))
        assert res is False

    def test_reset_geometry_if_not_maximized(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "normal"
        reset_geometry_if_not_maximized(mock_win)
        mock_win.geometry.assert_called_once_with("")

        # When zoomed, should NOT reset geometry
        mock_win.reset_mock()
        mock_win.state.return_value = "zoomed"
        reset_geometry_if_not_maximized(mock_win)
        mock_win.geometry.assert_not_called()

    def test_set_geometry_if_not_maximized(self):
        mock_win = MagicMock()
        mock_win.state.return_value = "normal"
        set_geometry_if_not_maximized(mock_win, "800x600")
        mock_win.geometry.assert_called_once_with("800x600")

        # When zoomed, should NOT set geometry
        mock_win.reset_mock()
        mock_win.state.return_value = "zoomed"
        set_geometry_if_not_maximized(mock_win, "800x600")
        mock_win.geometry.assert_not_called()

    def test_ttkbootstrap_style_resilience_functions(self):
        # Functions should execute safely without throwing
        assert isinstance(_ttkbootstrap_style_needs_reset(), bool)
        _clear_ttkbootstrap_style()
