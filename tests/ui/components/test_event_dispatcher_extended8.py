"""Extended unit tests for ui/components/event_dispatcher.py (Part 8)."""

from __future__ import annotations

from dataclasses import dataclass

from zebtrack.ui.components.event_dispatcher import (
    _payload_get,
    _payload_to_dict,
)


@dataclass
class SamplePayload:
    name: str
    count: int


class TestEventDispatcherExtended8:
    """Test EventDispatcher helper functions and parameter modes."""

    def test_payload_to_dict_dataclass(self):
        sample = SamplePayload(name="test", count=5)
        d = _payload_to_dict(sample)
        assert d == {"name": "test", "count": 5}

    def test_payload_to_dict_dict(self):
        sample = {"a": 1, "b": 2}
        assert _payload_to_dict(sample) == {"a": 1, "b": 2}

    def test_payload_to_dict_fallback(self):
        assert _payload_to_dict("non_dict") == {}

    def test_payload_get_dataclass(self):
        sample = SamplePayload(name="zebrafish", count=10)
        assert _payload_get(sample, "name") == "zebrafish"
        assert _payload_get(sample, "missing", "default") == "default"

    def test_payload_get_dict(self):
        sample = {"val": 42}
        assert _payload_get(sample, "val") == 42
        assert _payload_get(sample, "nonexistent", 0) == 0
