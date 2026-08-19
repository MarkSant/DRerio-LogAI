"""Extended unit tests for ui/components/project_views/video_selector_tree_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_views.project_view_helpers import (
    format_status_label,
    format_status_ratio,
    format_status_summary,
)
from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
    _payload_get,
)


class TestVideoSelectorTreeManagerExtended2:
    """Test VideoSelectorTreeManager DI properties and payload/formatting helpers."""

    def test_payload_get(self):
        d = {"video_path": "/test/vid.mp4", "status": "complete"}
        assert _payload_get(d, "video_path") == "/test/vid.mp4"
        assert _payload_get(d, "missing", "default") == "default"

    def test_dialog_manager_property_injected_and_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        mock_dm = MagicMock()
        mgr_injected = VideoSelectorTreeManager(gui, dialog_manager=mock_dm)
        assert mgr_injected.dialog_manager is mock_dm

        mgr_fallback = VideoSelectorTreeManager(gui, dialog_manager=None)
        assert mgr_fallback.dialog_manager is gui.dialog_manager

    def test_initial_state(self):
        gui = MagicMock()
        mgr = VideoSelectorTreeManager(gui)
        assert mgr._overview_refresh_pending is False
        assert mgr._overview_refresh_after_id is None

    def test_format_status_label(self):
        assert "1" in format_status_label(1)
        assert "5" in format_status_label(5)

    def test_format_status_summary(self):
        res_zero = format_status_summary(0, 0)
        assert "(0%)" in res_zero

        res_half = format_status_summary(10, 5)
        assert "(50%)" in res_half

    def test_format_status_ratio(self):
        res = format_status_ratio(3, 10)
        assert "3/10" in res or "3 / 10" in res
