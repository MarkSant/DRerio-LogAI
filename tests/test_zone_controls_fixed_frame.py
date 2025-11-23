"""Test that ZoneControlsWidget has a fixed button frame."""

import tkinter as tk
from tkinter import ttk

import pytest

from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus


@pytest.mark.gui
def test_zone_controls_has_fixed_button_frame(tkinter_root):
    """Verify ZoneControlsWidget exposes a fixed_button_frame."""
    root = tkinter_root
    event_bus = EventBus()
    container = ttk.Frame(root)
    container.pack()
    widget = ZoneControlsWidget(container, event_bus=event_bus)
    widget.pack()
    root.update()

    # Check that fixed_button_frame exists
    assert hasattr(widget, "fixed_button_frame"), "ZoneControlsWidget must have fixed_button_frame"
    assert isinstance(widget.fixed_button_frame, tk.Widget), "fixed_button_frame must be a widget"

    # Test that we can add a button to it
    test_button = tk.Button(widget.fixed_button_frame, text="Test Button")
    test_button.pack()
    root.update()

    # Verify button was added successfully
    assert test_button.winfo_exists(), "Button should exist in fixed_button_frame"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
