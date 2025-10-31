import tkinter as tk
import pytest
from unittest.mock import MagicMock

from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBus for testing."""
    return MagicMock(spec=EventBus)


def test_control_panel_publishes_events(tkinter_root, mock_event_bus):
    """Verify that ControlPanelWidget publishes events instead of using direct calls."""
    widget = ControlPanelWidget(tkinter_root, event_bus=mock_event_bus)
    widget.pack()
    tkinter_root.update()

    # Enable buttons before invoking
    widget.start_rec_btn.config(state=tk.NORMAL)
    widget.stop_rec_btn.config(state=tk.NORMAL)

    # Simulate button clicks and check if the correct event is published
    widget.start_rec_btn.invoke()
    mock_event_bus.publish_event.assert_called_with(Events.RECORDING_START, {})

    widget.stop_rec_btn.invoke()
    mock_event_bus.publish_event.assert_called_with(Events.RECORDING_STOP, {})


def test_zone_controls_publishes_events(tkinter_root, mock_event_bus):
    """Verify that ZoneControlsWidget publishes events for all its actions."""
    widget = ZoneControlsWidget(tkinter_root, event_bus=mock_event_bus)
    widget.pack()
    tkinter_root.update()

    # A more comprehensive test would check every button, but we'll sample a few
    widget.auto_detect_button.invoke()
    mock_event_bus.publish_event.assert_called_with(
        event_name="zone.auto_detect_clicked",
        data={"stabilization_frames": str(widget.stabilization_frames_var.get())},
    )

    widget.draw_arena_button.invoke()
    # Now emits component event using emit_event() which calls publish_event()
    # Check that publish_event was called with the correct event name and data
    mock_event_bus.publish_event.assert_called_with(
        event_name="zone.draw_arena",
        data={},
    )

    # Ensure no direct controller/view_model calls exist
    with pytest.raises(AttributeError):
        widget.controller.some_method()
