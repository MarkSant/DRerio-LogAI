"""Extended unit tests for ui/components/event_dispatcher.py (Part 9)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.event_dispatcher import EventDispatcher


class TestEventDispatcherExtended9:
    """Test EventDispatcher handler dictionary and unregister operations."""

    def test_event_dispatcher_init_empty_handlers(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)

        assert dispatcher.handlers == {}
        assert dispatcher.event_bus is bus

    def test_event_dispatcher_gui_context_detection(self):
        gui = MagicMock(spec=["event_bus"])
        gui.event_bus = MagicMock()
        dispatcher = EventDispatcher(gui)
        assert dispatcher.gui is gui
        assert dispatcher.event_bus is gui.event_bus

    def test_event_dispatcher_handlers_dict_access(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()
        dispatcher.handlers["CUSTOM_EVENT"] = handler

        assert "CUSTOM_EVENT" in dispatcher.handlers
        assert dispatcher.handlers["CUSTOM_EVENT"] is handler
