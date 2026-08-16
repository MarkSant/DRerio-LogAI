"""Extended unit tests for ui/icon_utils.py."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

from zebtrack.ui.icon_utils import get_icon_path, set_window_icon


class TestIconUtilsExtended:
    """Test icon path lookup and window icon configuration."""

    def test_get_icon_path_finds_file_or_returns_none(self):
        path = get_icon_path()
        # In this workspace, assets/drerio_logai.ico exists or returns Path
        if path is not None:
            assert isinstance(path, Path)
            assert path.suffix == ".ico"

    def test_get_icon_path_fallback_error_handling(self):
        with patch("pathlib.Path.exists", side_effect=OSError("Disk error")):
            result = get_icon_path()
            assert result is None

    def test_set_window_icon_none_path_skips(self):
        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=None):
            mock_win = MagicMock()
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_not_called()

    def test_set_window_icon_window_not_existing(self, tmp_path: Path):
        dummy_ico = tmp_path / "app.ico"
        dummy_ico.touch()

        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=dummy_ico):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = False
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_not_called()

    def test_set_window_icon_winfo_exists_raises_tcl_error(self, tmp_path: Path):
        dummy_ico = tmp_path / "app.ico"
        dummy_ico.touch()

        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=dummy_ico):
            mock_win = MagicMock()
            mock_win.winfo_exists.side_effect = tk.TclError("invalid window")
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_not_called()

    def test_set_window_icon_success_calls_iconbitmap(self, tmp_path: Path):
        dummy_ico = tmp_path / "app.ico"
        dummy_ico.touch()

        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=dummy_ico):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = True
            mock_win.title.return_value = "Main App"
            set_window_icon(mock_win)
            mock_win.iconbitmap.assert_called_once_with(default=str(dummy_ico))

    def test_set_window_icon_iconbitmap_raises_tcl_error(self, tmp_path: Path):
        dummy_ico = tmp_path / "app.ico"
        dummy_ico.touch()

        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=dummy_ico):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = True
            mock_win.iconbitmap.side_effect = tk.TclError("can't set icon")
            # Should catch and not raise
            set_window_icon(mock_win)

    def test_set_window_icon_iconbitmap_raises_generic_exception(self, tmp_path: Path):
        dummy_ico = tmp_path / "app.ico"
        dummy_ico.touch()

        with patch("zebtrack.ui.icon_utils.get_icon_path", return_value=dummy_ico):
            mock_win = MagicMock()
            mock_win.winfo_exists.return_value = True
            mock_win.iconbitmap.side_effect = RuntimeError("Platform unexpected error")
            # Should catch and log warning, not raise
            set_window_icon(mock_win)
