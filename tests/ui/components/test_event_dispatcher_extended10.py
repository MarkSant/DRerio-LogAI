"""Extended unit tests for ui/components/event_dispatcher.py (Part 10)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.event_dispatcher import (
    EventDispatcher,
    _payload_get,
    _payload_to_dict,
)


class TestEventDispatcherExtended10:
    """Test EventDispatcher None context handling and fallback behavior."""

    def test_event_dispatcher_none_context(self):
        dispatcher = EventDispatcher(None)
        assert dispatcher.gui is None
        assert dispatcher.event_bus is None
        assert dispatcher.handlers == {}

    def test_event_dispatcher_with_event_bus_context(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)
        assert dispatcher.event_bus is bus
        assert dispatcher.gui is None

    def test_event_dispatcher_handlers_dict_operations(self):
        dispatcher = EventDispatcher(None)
        handler_fn = MagicMock()
        dispatcher.handlers["custom_event"] = handler_fn
        assert "custom_event" in dispatcher.handlers
        assert dispatcher.handlers["custom_event"] == handler_fn

    def test_payload_to_dict_with_dict(self):
        data = {"key": "value"}
        assert _payload_to_dict(data) == {"key": "value"}

    def test_payload_get_with_dict(self):
        data = {"key": "value"}
        assert _payload_get(data, "key") == "value"
        assert _payload_get(data, "missing", default=123) == 123
