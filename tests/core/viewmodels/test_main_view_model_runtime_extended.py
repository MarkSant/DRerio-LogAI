"""
Extended unit tests for MainViewModelRuntime.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from zebtrack.core.viewmodels.main_view_model_runtime import (
    MainViewModelRuntime,
    _payload_get,
    _payload_to_dict,
)


@dataclass
class DummyPayload:
    video_path: str
    flag: bool


class TestMainViewModelRuntimeExtended:
    """Test payload helpers and event dispatcher generator."""

    def test_payload_to_dict_none_dict_dataclass(self):
        assert _payload_to_dict(None) == {}
        assert _payload_to_dict({"a": 1}) == {"a": 1}
        payload = DummyPayload(video_path="vid.mp4", flag=True)
        assert _payload_to_dict(payload) == {"video_path": "vid.mp4", "flag": True}

    def test_payload_get_variants(self):
        assert _payload_get(None, "key", default=10) == 10
        assert _payload_get({"key": 20}, "key") == 20
        payload = DummyPayload(video_path="vid.mp4", flag=True)
        assert _payload_get(payload, "video_path") == "vid.mp4"
        assert _payload_get(payload, "missing", default="none") == "none"

    def test_register_event_handlers_when_event_bus_none(self):
        mock_vm = MagicMock()
        mock_vm.ui_event_bus = None
        runtime = MainViewModelRuntime(mock_vm)
        runtime.register_event_handlers()  # Should not raise

    def test_register_event_handlers_subscribes_all(self):
        mock_vm = MagicMock()
        mock_event_bus = MagicMock()
        mock_vm.ui_event_bus = mock_event_bus
        runtime = MainViewModelRuntime(mock_vm)
        runtime.register_event_handlers()
        # +1 for the extra UIEvents.PROJECT_MANAGER_REPLACED subscription
        assert (
            mock_event_bus.subscribe.call_count == len(MainViewModelRuntime._EVENTS_TO_HANDLE) + 1
        )
