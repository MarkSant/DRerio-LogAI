"""Extended unit tests for ui/components/event_dispatcher.py (Part 5)."""

from __future__ import annotations

from dataclasses import dataclass

from zebtrack.ui.components.event_dispatcher import (
    EventDispatcher,
    _payload_get,
    _payload_to_dict,
)


@dataclass
class MockPayload:
    param1: str
    param2: int


class TestEventDispatcherExtended5:
    """Test EventDispatcher payload conversion and handler mappings."""

    def test_payload_to_dict_dict(self):
        d = {"name": "unit_test", "code": 100}
        assert _payload_to_dict(d) == d

    def test_payload_to_dict_dataclass(self):
        payload = MockPayload(param1="hello", param2=42)
        converted = _payload_to_dict(payload)
        assert converted == {"param1": "hello", "param2": 42}

    def test_payload_to_dict_invalid(self):
        assert _payload_to_dict(None) == {}
        assert _payload_to_dict("string_payload") == {}
        assert _payload_to_dict(12345) == {}

    def test_payload_get_dataclass(self):
        payload = MockPayload(param1="test_val", param2=10)
        assert _payload_get(payload, "param1") == "test_val"
        assert _payload_get(payload, "param2") == 10
        assert _payload_get(payload, "nonexistent", "fallback") == "fallback"

    def test_initial_handlers_empty(self):
        dispatcher = EventDispatcher(context=None)
        assert dispatcher.handlers == {}
        assert dispatcher.event_bus is None
        assert dispatcher.gui is None
