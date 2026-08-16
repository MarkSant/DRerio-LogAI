"""
Extended unit tests for os_opener cross-platform file opening.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zebtrack.utils.os_opener import open_path


class TestOsOpenerExtended:
    """Test open_path across platform handlers."""

    def test_open_path_nonexistent_raises(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            open_path(nonexistent)

    def test_open_path_win32(self, tmp_path: Path):
        target = tmp_path / "valid.txt"
        target.write_text("hello", encoding="utf-8")

        with (
            patch("sys.platform", "win32"),
            patch("os.startfile", create=True) as mock_startfile,
        ):
            open_path(target)
            mock_startfile.assert_called_once_with(str(target.resolve()))

    def test_open_path_darwin(self, tmp_path: Path):
        target = tmp_path / "valid.txt"
        target.write_text("hello", encoding="utf-8")

        with (
            patch("sys.platform", "darwin"),
            patch("subprocess.Popen") as mock_popen,
        ):
            open_path(target)
            mock_popen.assert_called_once_with(["open", str(target.resolve())])

    def test_open_path_linux(self, tmp_path: Path):
        target = tmp_path / "valid.txt"
        target.write_text("hello", encoding="utf-8")

        with (
            patch("sys.platform", "linux"),
            patch("subprocess.Popen") as mock_popen,
        ):
            open_path(target)
            mock_popen.assert_called_once_with(["xdg-open", str(target.resolve())])
