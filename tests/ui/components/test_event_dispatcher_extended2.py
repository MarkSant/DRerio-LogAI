"""Extended unit tests for ui/components/event_dispatcher.py."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.event_dispatcher import (
    EventDispatcher,
    _payload_get,
    _payload_to_dict,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@dataclass
class SamplePayload:
    video_path: str
    frame_count: int = 100
    group: str = "Control"


class TestEventDispatcherHelpers:
    """Test payload extraction helper functions."""

    def test_payload_to_dict_with_dict(self):
        data = {"key": "val", "num": 42}
        assert _payload_to_dict(data) == data

    def test_payload_to_dict_with_dataclass(self):
        payload = SamplePayload(video_path="/path/v.mp4", frame_count=100)
        d = _payload_to_dict(payload)
        assert d == {"video_path": "/path/v.mp4", "frame_count": 100, "group": "Control"}

    def test_payload_to_dict_with_other_object(self):
        assert _payload_to_dict("string_payload") == {}  # type: ignore[arg-type]
        assert _payload_to_dict(None) == {}  # type: ignore[arg-type]

    def test_payload_get_with_dict(self):
        data = {"a": 1, "b": 2}
        assert _payload_get(data, "a") == 1
        assert _payload_get(data, "c", default=99) == 99

    def test_payload_get_with_dataclass(self):
        payload = SamplePayload(video_path="/path/v.mp4", frame_count=50)
        assert _payload_get(payload, "video_path") == "/path/v.mp4"
        assert _payload_get(payload, "frame_count") == 50
        assert _payload_get(payload, "non_existent", default="def") == "def"

    def test_payload_get_with_fallback(self):
        assert _payload_get(12345, "a", default="none") == "none"  # type: ignore[arg-type]


class TestEventDispatcherModes:
    """Test EventDispatcher dispatching modes (NO_PARAMS, KWARGS_ALL, KWARGS_GET, POSITIONAL)."""

    def test_init_with_none_context(self):
        dispatcher = EventDispatcher(None)
        assert dispatcher.event_bus is None
        assert dispatcher.gui is None

    def test_init_with_event_bus(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        assert dispatcher.event_bus is bus

    def test_require_gui_raises_when_none(self):
        dispatcher = EventDispatcher(None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()

    def test_mode_no_params(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.APP_CLOSE, handler, mode=EventDispatcher.MODE_NO_PARAMS
        )
        bus.publish(UIEvents.APP_CLOSE, {})

        handler.assert_called_once_with()

    def test_mode_kwargs_all(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES, handler, mode=EventDispatcher.MODE_KWARGS_ALL
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with(video_path="/path/v.mp4")

    def test_mode_kwargs_get(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path"],
            mode=EventDispatcher.MODE_KWARGS_GET,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with(video_path="/path/v.mp4")

    def test_mode_positional(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path"],
            mode=EventDispatcher.MODE_POSITIONAL,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with("/path/v.mp4")

    def test_mode_positional_optional(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path", "missing_param"],
            mode=EventDispatcher.MODE_POSITIONAL_OPTIONAL,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with("/path/v.mp4", None)

    def test_handler_exception_is_caught_and_logged(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        bad_handler = MagicMock(side_effect=ValueError("Handler failed"))

        dispatcher.register_handler(
            UIEvents.APP_CLOSE, bad_handler, mode=EventDispatcher.MODE_NO_PARAMS
        )
        # Should not raise exception out of publish
        bus.publish(UIEvents.APP_CLOSE, {})
        bad_handler.assert_called_once()

    def test_has_meaningful_analysis_metadata(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "A"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": "01"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "Zeb1"}) is True
        assert (
            EventDispatcher._has_meaningful_analysis_metadata({"group": None, "day": ""}) is False
        )
        assert EventDispatcher._has_meaningful_analysis_metadata({}) is False

    def test_finish_drawing_is_interactive_edit(self):
        mock_gui = MagicMock()
        mock_gui.canvas_manager.current_editing_zone = "arena"
        mock_gui.edited_polygon_points = [(0, 0), (10, 10)]
        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is True

        mock_gui.edited_polygon_points = []
        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is False
