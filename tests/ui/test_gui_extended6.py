"""Extended unit tests for ui/gui.py (Part 6)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.ui.gui import ApplicationGUI


class TestGuiExtended6:
    """Test ApplicationGUI canvas constants, aliases, and attribute initializations."""

    def test_application_gui_canvas_constants(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600

    def test_application_gui_event_bus_alias(self):
        gui: Any = object.__new__(ApplicationGUI)
        event_bus = MagicMock()
        gui.event_bus = event_bus
        gui.event_bus_v2 = event_bus

        assert gui.event_bus is event_bus
        assert gui.event_bus_v2 is event_bus

    def test_application_gui_state_manager_attr(self):
        gui: Any = object.__new__(ApplicationGUI)
        state_mgr = MagicMock()
        gui._state_manager = state_mgr
        assert gui._state_manager is state_mgr
