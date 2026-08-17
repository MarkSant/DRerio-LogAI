"""Extended unit tests for ui/components/event_dispatcher.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from zebtrack.ui.components.event_dispatcher import (
    EventDispatcher,
    _payload_get,
    _payload_to_dict,
)


@dataclass
class SamplePayload:
    project_id: str
    count: int


class TestEventDispatcherExtended3:
    """Test EventDispatcher payload conversion, modes, and context validation."""

    def test_payload_modes_constants(self):
        assert EventDispatcher.MODE_NO_PARAMS == "no_params"
        assert EventDispatcher.MODE_KWARGS_ALL == "kwargs_all"
        assert EventDispatcher.MODE_KWARGS_GET == "kwargs_get"
        assert EventDispatcher.MODE_POSITIONAL == "positional"
        assert EventDispatcher.MODE_POSITIONAL_OPTIONAL == "positional_optional"

    def test_payload_to_dict_with_dict_and_dataclass(self):
        d = {"name": "test", "value": 10}
        assert _payload_to_dict(d) == d

        sample = SamplePayload(project_id="prj_1", count=42)
        res = _payload_to_dict(sample)
        assert res == {"project_id": "prj_1", "count": 42}

        assert _payload_to_dict("invalid_type") == {}

    def test_payload_get_with_dict_and_dataclass(self):
        d = {"alpha": "val1"}
        assert _payload_get(d, "alpha") == "val1"
        assert _payload_get(d, "beta", "default_val") == "default_val"

        sample = SamplePayload(project_id="prj_2", count=99)
        assert _payload_get(sample, "project_id") == "prj_2"
        assert _payload_get(sample, "missing_field", "fallback") == "fallback"

    def test_require_gui_raises_when_gui_is_none(self):
        dispatcher = EventDispatcher(context=None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()
