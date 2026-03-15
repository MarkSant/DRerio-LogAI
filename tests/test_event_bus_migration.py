import tkinter as tk
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBusV2 for testing."""
    return MagicMock(spec=EventBusV2)


@pytest.mark.gui
def test_control_panel_publishes_events(tkinter_root, mock_event_bus):
    """Verify that ControlPanelWidget publishes events via EventBusV2."""
    widget = ControlPanelWidget(tkinter_root, event_bus=mock_event_bus)
    widget.pack()
    tkinter_root.update()

    # Enable buttons before invoking
    assert widget.start_rec_btn is not None
    assert widget.stop_rec_btn is not None
    widget.start_rec_btn.config(state=tk.NORMAL)
    widget.stop_rec_btn.config(state=tk.NORMAL)

    # Simulate button clicks and check if the correct event is published
    widget.start_rec_btn.invoke()
    mock_event_bus.publish.assert_called_with(UIEvents.RECORDING_START, {})

    widget.stop_rec_btn.invoke()
    mock_event_bus.publish.assert_called_with(UIEvents.RECORDING_STOP, {})


@pytest.mark.gui
def test_zone_controls_publishes_events(tkinter_root, mock_event_bus):
    """Verify that ZoneControlsWidget publishes events via EventBusV2."""
    widget = ZoneControlsWidget(tkinter_root, event_bus=mock_event_bus)
    widget.pack()
    tkinter_root.update()

    # A more comprehensive test would check every button, but we'll sample a few
    assert widget.auto_detect_button is not None
    widget.auto_detect_button.invoke()
    mock_event_bus.publish.assert_called_with(
        UIEvents.ZONE_AUTO_DETECT_CLICKED,
        {"stabilization_frames": str(widget.stabilization_frames_var.get())},
    )

    widget.draw_arena_button.invoke()
    mock_event_bus.publish.assert_called_with(
        UIEvents.ZONE_DRAW_ARENA,
        {},
    )

    # Ensure no direct controller/view_model calls exist
    assert not hasattr(widget, "controller")
