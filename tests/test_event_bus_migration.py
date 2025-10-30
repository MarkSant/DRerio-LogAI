import tkinter as tk
import unittest
from unittest.mock import MagicMock

from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events


class TestEventBusMigration(unittest.TestCase):
    def setUp(self):
        """Set up a Tkinter root window before each test."""
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - headless CI fallback
            self.skipTest(f"Tkinter unavailable: {exc}")
        self.mock_event_bus = MagicMock(spec=EventBus)

    def tearDown(self):
        """Destroy the Tkinter root window after each test."""
        self.root.destroy()

    def test_control_panel_publishes_events(self):
        """Verify that ControlPanelWidget publishes events instead of using direct calls."""
        widget = ControlPanelWidget(self.root, event_bus=self.mock_event_bus)
        widget.pack()
        self.root.update()

        # Enable buttons before invoking
        widget.start_rec_btn.config(state=tk.NORMAL)
        widget.stop_rec_btn.config(state=tk.NORMAL)

        # Simulate button clicks and check if the correct event is published
        widget.start_rec_btn.invoke()
        self.mock_event_bus.publish_event.assert_called_with(Events.RECORDING_START, {})

        widget.stop_rec_btn.invoke()
        self.mock_event_bus.publish_event.assert_called_with(Events.RECORDING_STOP, {})

    def test_zone_controls_publishes_events(self):
        """Verify that ZoneControlsWidget publishes events for all its actions."""
        widget = ZoneControlsWidget(self.root, event_bus=self.mock_event_bus)
        widget.pack()
        self.root.update()

        # A more comprehensive test would check every button, but we'll sample a few
        widget.auto_detect_button.invoke()
        self.mock_event_bus.publish_event.assert_called_with(
            event_name="zone.auto_detect_clicked",
            data={"stabilization_frames": str(widget.stabilization_frames_var.get())},
        )

        widget.draw_arena_button.invoke()
        # Now emits component event using emit_event() which calls publish_event()
        # Check that publish_event was called with the correct event name and data
        self.mock_event_bus.publish_event.assert_called_with(
            event_name="zone.draw_arena",
            data={},
        )

        # Ensure no direct controller/view_model calls exist
        with self.assertRaises(AttributeError):
            widget.controller.some_method()


if __name__ == "__main__":
    unittest.main()
