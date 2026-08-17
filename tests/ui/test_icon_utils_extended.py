"""Extended unit tests for ui/icon_utils.py."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

from zebtrack.ui.icon_utils import get_icon_path, set_window_icon


class TestIconUtilsExtended:
    """Test icon resolution and window icon setting."""

    def test_get_icon_path(self):
        # Even if file doesn't exist, function returns Path or None safely
        res = get_icon_path()
        assert res is None or isinstance(res, Path)

    def test_set_window_icon_none_path(self):
        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=None):
            mock_win = MagicMock()
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_not_called()

    def test_set_window_icon_window_not_exists(self, tmp_path: Path):
        icon_file = tmp_path / "app.ico"
        icon_file.write_bytes(b"ico")
        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=icon_file):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = False
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_not_called()

    def test_set_window_icon_success(self, tmp_path: Path):
        icon_file = tmp_path / "app.ico"
        icon_file.write_bytes(b"ico")
        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=icon_file):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = True
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_called_once_with(default=str(icon_file))

    def test_set_window_icon_tcl_error_handled(self, tmp_path: Path):
        icon_file = tmp_path / "app.ico"
        icon_file.write_bytes(b"ico")
        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=icon_file):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = True
            mock_win.iconbitmap.side_effect = tk.TclError("bitmap error")
            # Should not raise
            set_window_icon(mock_win)
