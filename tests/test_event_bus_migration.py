import tkinter as tk
import unittest
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events


class TestEventBusMigration(unittest.TestCase):
    def setUp(self):
        """Set up a Tkinter root window before each test."""
        self.root = tk.Tk()
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
            Events.ZONE_AUTO_DETECT,
            {"stabilization_frames": int(widget.stabilization_frames_var.get())},
        )

        widget.draw_arena_button.invoke()
        # Now emits component event using emit_event() which calls publish()
        # Check that publish was called with a NamedEvent
        self.mock_event_bus.publish.assert_called()
        call_args = self.mock_event_bus.publish.call_args[0][0]
        self.assertEqual(call_args.event_name, "zone.draw_arena")
        self.assertEqual(call_args.data, {})

        # Ensure no direct controller/view_model calls exist
        with self.assertRaises(AttributeError):
            widget.controller.some_method()

    @pytest.mark.skip(reason="Conceptual test - enforced by other widget tests")
    def test_no_direct_controller_references(self):
        """Check that UI components do not hold direct references to a controller."""
        # This test is more conceptual and is partially enforced by the other tests.
        # A full check might involve inspecting the __init__ of all widgets,
        # but for now, we'll rely on the individual widget tests.
        pass


if __name__ == "__main__":
    unittest.main()
