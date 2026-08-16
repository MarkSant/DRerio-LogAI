"""
Extended unit tests for CameraConnectionHandler helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from zebtrack.core.recording.camera_connection_handler import _payload_get


@dataclass
class DummyPayload:
    camera_index: int
    name: str


class TestCameraConnectionHandlerExtended:
    """Test helper functions in camera_connection_handler."""

    def test_payload_get_dict(self):
        d = {"camera_index": 2, "name": "usb_cam"}
        assert _payload_get(d, "camera_index") == 2
        assert _payload_get(d, "name") == "usb_cam"
        assert _payload_get(d, "missing", default=99) == 99

    def test_payload_get_dataclass(self):
        payload = DummyPayload(camera_index=1, name="main_cam")
        assert _payload_get(payload, "camera_index") == 1
        assert _payload_get(payload, "name") == "main_cam"
        assert _payload_get(payload, "missing", default="none") == "none"

    def test_payload_get_other_or_none(self):
        assert _payload_get(None, "key", default="fallback") == "fallback"
        assert _payload_get("string_payload", "key", default=42) == 42
