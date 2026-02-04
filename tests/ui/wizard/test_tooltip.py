"""Tests for wizard tooltip helpers."""

from typing import cast
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.wizard import tooltip as tooltip_module


def _build_widget():
    widget = MagicMock()
    widget.after = MagicMock(return_value="after-id")
    widget.after_cancel = MagicMock()
    widget.bind = MagicMock()
    widget.winfo_rootx = MagicMock(return_value=100)
    widget.winfo_rooty = MagicMock(return_value=200)
    widget.winfo_height = MagicMock(return_value=30)
    return widget


def test_on_enter_schedules_tooltip_and_cancels_previous():
    widget = _build_widget()
    tooltip = tooltip_module.ToolTip(widget, "Help text", delay=250)
    tooltip.scheduled_id = "prev-id"

    tooltip._on_enter()

    widget.after_cancel.assert_called_once_with("prev-id")
    widget.after.assert_called_once()
    assert tooltip.scheduled_id == "after-id"


def test_on_leave_cancels_schedule_and_hides_tooltip():
    widget = _build_widget()
    tooltip = tooltip_module.ToolTip(widget, "Help text", delay=250)
    tooltip.scheduled_id = "scheduled"
    window = MagicMock()
    tooltip.tooltip_window = window

    tooltip._on_leave()

    widget.after_cancel.assert_called_once_with("scheduled")
    assert tooltip.scheduled_id is None
    window.destroy.assert_called_once()
    assert tooltip.tooltip_window is None


def test_show_tooltip_creates_window_and_label(monkeypatch):
    widget = _build_widget()
    tooltip = tooltip_module.ToolTip(widget, "Help text", delay=250)
    mock_window = MagicMock()
    mock_label = MagicMock()

    monkeypatch.setattr(tooltip_module.tk, "Toplevel", MagicMock(return_value=mock_window))
    monkeypatch.setattr(tooltip_module, "Label", MagicMock(return_value=mock_label))

    tooltip._show_tooltip()

    cast(MagicMock, tooltip_module.tk.Toplevel).assert_called_once_with(widget)
    mock_window.wm_overrideredirect.assert_called_once_with(True)
    mock_window.wm_geometry.assert_called_once_with("+120+235")
    mock_label.pack.assert_called_once()
    assert tooltip.tooltip_window is mock_window


def test_show_tooltip_skips_when_text_empty(monkeypatch):
    widget = _build_widget()
    tooltip = tooltip_module.ToolTip(widget, "", delay=250)

    toplevel = MagicMock()
    monkeypatch.setattr(tooltip_module.tk, "Toplevel", toplevel)

    tooltip._show_tooltip()

    toplevel.assert_not_called()


def test_create_help_label_builds_label_and_tooltip(monkeypatch):
    parent = MagicMock()
    label = MagicMock()
    tooltip_cls = MagicMock()

    monkeypatch.setattr(tooltip_module, "Label", MagicMock(return_value=label))
    monkeypatch.setattr(tooltip_module, "ToolTip", tooltip_cls)

    result = tooltip_module.create_help_label(parent, "Some help")

    assert result is label
    tooltip_cls.assert_called_once_with(label, "Some help")


@pytest.mark.parametrize(
    "text",
    ["A", "Longer help text"],
)
def test_show_tooltip_skips_if_already_visible(monkeypatch, text):
    widget = _build_widget()
    tooltip = tooltip_module.ToolTip(widget, text, delay=250)
    tooltip.tooltip_window = MagicMock()

    toplevel = MagicMock()
    monkeypatch.setattr(tooltip_module.tk, "Toplevel", toplevel)

    tooltip._show_tooltip()

    toplevel.assert_not_called()
