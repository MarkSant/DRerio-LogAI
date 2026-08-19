"""Extended unit tests for ui/gui.py."""

from __future__ import annotations

from dataclasses import dataclass

from zebtrack.ui.gui import (
    PROJECT_STATUS_WIDGET_ORDER,
    STATUS_SYMBOLS,
    ApplicationGUI,
    _payload_get,
)


@dataclass
class DummyPayload:
    title: str
    count: int


class TestGuiExtended:
    """Test ApplicationGUI constants, helpers, and payload extraction."""

    def test_constants(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600

        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

        assert "total" in PROJECT_STATUS_WIDGET_ORDER
        assert "pending" in PROJECT_STATUS_WIDGET_ORDER
        assert "complete" in PROJECT_STATUS_WIDGET_ORDER
        assert "failed" in PROJECT_STATUS_WIDGET_ORDER

    def test_payload_get_dict(self):
        d = {"name": "test_exp", "val": 42}
        assert _payload_get(d, "name") == "test_exp"
        assert _payload_get(d, "val") == 42
        assert _payload_get(d, "missing", "default_val") == "default_val"

    def test_payload_get_dataclass(self):
        payload = DummyPayload(title="Alert", count=5)
        assert _payload_get(payload, "title") == "Alert"
        assert _payload_get(payload, "count") == 5
        assert _payload_get(payload, "nonexistent", "fallback") == "fallback"

    def test_payload_get_unsupported_types(self):
        assert _payload_get(None, "key", "default") == "default"
        assert _payload_get("string_payload", "key", 123) == 123
        assert _payload_get(42, "key", None) is None

    def test_extract_setting_nested(self):
        class Node:
            def __init__(self, child=None, val=None):
                self.child = child
                self.val = val

        root = Node(child=Node(val="target_value"))
        res = ApplicationGUI._extract_setting(root, ("child", "val"), "default")
        assert res == "target_value"

    def test_extract_setting_fallback(self):
        class Node:
            def __init__(self):
                self.other = 123

        root = Node()
        res = ApplicationGUI._extract_setting(root, ("missing", "path"), "fallback_value")
        assert res == "fallback_value"

        res_none = ApplicationGUI._extract_setting(None, ("any",), "fallback_value")
        assert res_none == "fallback_value"
