"""Tests for BaseWidget behavior."""

from tkinter import ttk
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.base import BaseWidget


class _DummyWidget(BaseWidget):
    def _build_ui(self) -> None:
        self.button = ttk.Button(self, text="Test")
        self.button.pack()


@pytest.mark.gui
def test_emit_event_without_bus(tkinter_root):
    widget = _DummyWidget(tkinter_root, event_bus=None)

    widget.emit_event("event.test", {"a": 1})

    # No event bus, should not raise


@pytest.mark.gui
def test_emit_event_with_bus(tkinter_root):
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)

    widget.emit_event("event.test", {"a": 1})

    event_bus.publish_event.assert_called_once_with(event_name="event.test", data={"a": 1})


@pytest.mark.gui
def test_bind_callback_with_bus(tkinter_root):
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)
    handler = Mock()

    widget.bind_callback("event.test", handler)

    event_bus.subscribe.assert_called_once_with("event.test", handler)


@pytest.mark.gui
def test_set_enabled_updates_children(tkinter_root):
    widget = _DummyWidget(tkinter_root, event_bus=None)

    widget.set_enabled(False)
    assert str(widget.button.cget("state")) == "disabled"

    widget.set_enabled(True)
    assert str(widget.button.cget("state")) == "normal"
