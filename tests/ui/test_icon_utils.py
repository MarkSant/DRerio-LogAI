"""Tests for icon utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.ui import icon_utils


def test_get_icon_path_found(monkeypatch):
    def _exists(path: Path) -> bool:
        return str(path).endswith("drerio_logai.ico")

    monkeypatch.setattr(Path, "exists", _exists)

    result = icon_utils.get_icon_path()

    assert result is not None
    assert str(result).endswith("drerio_logai.ico")


def test_get_icon_path_not_found(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda _: False)

    assert icon_utils.get_icon_path() is None


def test_set_window_icon_skips_when_missing(monkeypatch):
    monkeypatch.setattr(icon_utils, "get_icon_path", lambda: None)
    window = MagicMock()

    icon_utils.set_window_icon(window)

    window.iconbitmap.assert_not_called()


def test_set_window_icon_applies(monkeypatch):
    monkeypatch.setattr(icon_utils, "get_icon_path", lambda: Path("icon.ico"))
    window = MagicMock()
    window.winfo_exists.return_value = True

    icon_utils.set_window_icon(window)

    window.iconbitmap.assert_called_once()
