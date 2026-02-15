"""Tests for window utility helpers."""

from __future__ import annotations

from tkinter import TclError
from unittest.mock import MagicMock

import pytest

from zebtrack.ui import window_utils


def test_maximize_window_uses_zoomed_state():
    window = MagicMock()
    window.state = MagicMock()

    window_utils.maximize_window(window)

    window.state.assert_called_with("zoomed")


def test_maximize_window_fallback_geometry():
    window = MagicMock()
    window.state.side_effect = Exception("state failed")
    window.attributes.side_effect = Exception("attr failed")
    window.winfo_screenwidth.return_value = 800
    window.winfo_screenheight.return_value = 600

    window_utils.maximize_window(window)

    window.geometry.assert_called_with("800x600+0+0")


def test_schedule_maximize_calls_after():
    window = MagicMock()
    window_utils.schedule_maximize(window)
    window.after.assert_called_once()


def test_reset_geometry_if_not_maximized():
    window = MagicMock()
    window.state.return_value = "normal"

    window_utils.reset_geometry_if_not_maximized(window)

    window.geometry.assert_called_once_with("")


def test_reset_geometry_if_maximized():
    window = MagicMock()
    window.state.return_value = "zoomed"

    window_utils.reset_geometry_if_not_maximized(window)

    window.geometry.assert_not_called()


def test_set_geometry_if_not_maximized():
    window = MagicMock()
    window.state.return_value = "normal"

    window_utils.set_geometry_if_not_maximized(window, "200x100")

    window.geometry.assert_called_once_with("200x100")


def test_set_geometry_if_maximized():
    window = MagicMock()
    window.state.return_value = "zoomed"

    window_utils.set_geometry_if_not_maximized(window, "200x100")

    window.geometry.assert_not_called()


def test_create_scrollbar_resets_style_on_tcl_error(monkeypatch):
    parent = MagicMock()

    calls = {"count": 0}

    def _scrollbar(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TclError("application has been destroyed")
        return "scrollbar"

    monkeypatch.setattr(window_utils.ttk, "Scrollbar", _scrollbar)
    cleared = {"value": False}

    def _needs_reset() -> bool:
        return True

    def _clear_style() -> None:
        cleared.update(value=True)

    monkeypatch.setattr(window_utils, "_ttkbootstrap_style_needs_reset", _needs_reset)
    monkeypatch.setattr(window_utils, "_clear_ttkbootstrap_style", _clear_style)

    assert window_utils.create_scrollbar(parent) == "scrollbar"
    assert cleared["value"] is True


def test_create_scrollbar_raises_other_tcl_errors(monkeypatch):
    parent = MagicMock()

    def _scrollbar(*args, **kwargs):
        raise TclError("other error")

    monkeypatch.setattr(window_utils.ttk, "Scrollbar", _scrollbar)

    with pytest.raises(TclError):
        window_utils.create_scrollbar(parent)
