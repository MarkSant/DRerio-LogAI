"""Extended unit tests for utils/os_opener.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zebtrack.utils.os_opener import open_path


class TestOsOpenerExtended:
    """Test open_path cross-platform launcher and error guards."""

    def test_open_path_nonexistent_raises(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            open_path(missing)

    def test_open_path_windows(self, tmp_path: Path):
        existing = tmp_path / "file.txt"
        existing.write_text("content")

        with patch("sys.platform", "win32"), patch("os.startfile", create=True) as mock_startfile:
            open_path(existing)
            mock_startfile.assert_called_once_with(str(existing.resolve()))

    def test_open_path_darwin(self, tmp_path: Path):
        existing = tmp_path / "file.txt"
        existing.write_text("content")

        with patch("sys.platform", "darwin"), patch("subprocess.Popen") as mock_popen:
            open_path(existing)
            mock_popen.assert_called_once_with(["open", str(existing.resolve())])

    def test_open_path_linux(self, tmp_path: Path):
        existing = tmp_path / "file.txt"
        existing.write_text("content")

        with patch("sys.platform", "linux"), patch("subprocess.Popen") as mock_popen:
            open_path(existing)
            mock_popen.assert_called_once_with(["xdg-open", str(existing.resolve())])
