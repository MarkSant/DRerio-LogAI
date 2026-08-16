"""Extended unit tests for utils/os_opener.py."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from zebtrack.utils.os_opener import open_path


class TestOsOpenerExtended:
    """Test cross-platform open_path utility across Windows, macOS, and Linux."""

    def test_open_path_raises_file_not_found(self, tmp_path: Path):
        non_existent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            open_path(non_existent)

    @patch("sys.platform", "win32")
    @patch("os.startfile", create=True)
    def test_open_path_win32_success(self, mock_startfile, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.touch()

        open_path(test_file)
        mock_startfile.assert_called_once_with(str(test_file.resolve()))

    @patch("sys.platform", "win32")
    def test_open_path_win32_no_startfile_raises_oserror(self, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.touch()

        with patch.object(os, "startfile", None, create=True):
            with pytest.raises(OSError, match="os.startfile not available"):
                open_path(test_file)

    @patch("sys.platform", "darwin")
    @patch("subprocess.Popen")
    def test_open_path_darwin(self, mock_popen, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.touch()

        open_path(test_file)
        mock_popen.assert_called_once_with(["open", str(test_file.resolve())])

    @patch("sys.platform", "linux")
    @patch("subprocess.Popen")
    def test_open_path_linux(self, mock_popen, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.touch()

        open_path(test_file)
        mock_popen.assert_called_once_with(["xdg-open", str(test_file.resolve())])
