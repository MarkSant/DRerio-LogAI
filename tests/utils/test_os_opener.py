"""Tests for zebtrack.utils.os_opener (P1 audit fix).

Validates:
- open_path raises FileNotFoundError for missing paths
- open_path calls os.startfile on Windows
- open_path calls subprocess.Popen on non-Windows
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.utils.os_opener import open_path


class TestOpenPath:
    """Tests for the open_path utility."""

    def test_raises_on_missing_path(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            open_path(tmp_path / "nonexistent")

    @patch("zebtrack.utils.os_opener.sys")
    @patch("zebtrack.utils.os_opener.os")
    def test_windows_calls_startfile(self, mock_os, mock_sys, tmp_path: Path):
        # Create a real file so Path.resolve().exists() works
        target = tmp_path / "test.txt"
        target.write_text("hello")

        mock_sys.platform = "win32"
        mock_startfile = MagicMock()
        mock_os.startfile = mock_startfile

        open_path(target)
        mock_startfile.assert_called_once_with(str(target.resolve()))

    @patch("zebtrack.utils.os_opener.subprocess")
    @patch("zebtrack.utils.os_opener.sys")
    def test_darwin_calls_open(self, mock_sys, mock_subprocess, tmp_path: Path):
        target = tmp_path / "test.txt"
        target.write_text("hello")

        mock_sys.platform = "darwin"

        open_path(target)
        mock_subprocess.Popen.assert_called_once_with(["open", str(target.resolve())])

    @patch("zebtrack.utils.os_opener.subprocess")
    @patch("zebtrack.utils.os_opener.sys")
    def test_linux_calls_xdg_open(self, mock_sys, mock_subprocess, tmp_path: Path):
        target = tmp_path / "test.txt"
        target.write_text("hello")

        mock_sys.platform = "linux"

        open_path(target)
        mock_subprocess.Popen.assert_called_once_with(["xdg-open", str(target.resolve())])

    def test_accepts_string_path(self, tmp_path: Path):
        target = tmp_path / "test.txt"
        target.write_text("hello")

        with (
            patch("zebtrack.utils.os_opener.sys") as mock_sys,
            patch("zebtrack.utils.os_opener.os") as mock_os,
        ):
            mock_sys.platform = "win32"
            mock_os.startfile = MagicMock()
            # Should not raise when given string
            open_path(str(target))

    def test_accepts_directory(self, tmp_path: Path):
        with (
            patch("zebtrack.utils.os_opener.sys") as mock_sys,
            patch("zebtrack.utils.os_opener.os") as mock_os,
        ):
            mock_sys.platform = "win32"
            mock_os.startfile = MagicMock()
            open_path(tmp_path)
            mock_os.startfile.assert_called_once()
