"""Extended unit tests for ui/components/project_views/video_selector_tree_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
    _payload_get,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.payloads import VideoPathPayload


class TestVideoSelectorTreeManagerExtended:
    """Test VideoSelectorTreeManager helper functions, properties, navigation,
    and event handling.
    """

    def test_payload_get(self):
        d = {"video_path": "/path/v.mp4", "count": 2}
        assert _payload_get(d, "video_path") == "/path/v.mp4"
        assert _payload_get(d, "missing", default=10) == 10

        p = VideoPathPayload(video_path="/other/v.mp4")
        assert _payload_get(p, "video_path") == "/other/v.mp4"
        assert _payload_get(p, "missing", default=None) is None

    def test_dialog_manager_property(self):
        mock_gui = MagicMock()
        mock_gui.dialog_manager = MagicMock()
        mgr_default = VideoSelectorTreeManager(mock_gui)
        assert mgr_default.dialog_manager == mock_gui.dialog_manager

        mock_custom_dialog = MagicMock()
        mgr_custom = VideoSelectorTreeManager(mock_gui, dialog_manager=mock_custom_dialog)
        assert mgr_custom.dialog_manager == mock_custom_dialog

    def test_event_subscriptions_and_handlers(self):
        event_bus = EventBusV2()
        mock_gui = MagicMock()
        mgr = VideoSelectorTreeManager(mock_gui, event_bus_v2=event_bus)

        mgr._populate_video_selector_tree = MagicMock()  # type: ignore[assignment]
        mgr.refresh_project_views = MagicMock()  # type: ignore[assignment]

        # Trigger VIDEO_TREE_REFRESH_REQUESTED
        event_bus.publish(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, {"filter_text": "sample"})
        mgr._populate_video_selector_tree.assert_called_once_with("sample")

        # Trigger PROJECT_VIEWS_REFRESH_REQUESTED
        event_bus.publish(
            UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
            {"reason": "update", "immediate": True},
        )
        mgr.refresh_project_views.assert_called_once_with(
            reason="update", append_summary=None, immediate=True
        )

    def test_update_window_title(self):
        mock_gui = MagicMock()
        mgr = VideoSelectorTreeManager(mock_gui)

        mgr.update_window_title("ProjectAlpha")
        mock_gui.root.title.assert_called_with("DRerio LogAI - ProjectAlpha")

        mgr.update_window_title(None)
        mock_gui.root.title.assert_called_with("DRerio LogAI")

    def test_navigate_to_processing_reports_tab(self):
        mock_gui = MagicMock()
        mock_gui.notebook = MagicMock()
        mock_gui.processing_reports_tab_frame = MagicMock()
        mgr = VideoSelectorTreeManager(mock_gui)

        mgr.navigate_to_processing_reports_tab()
        mock_gui.notebook.select.assert_called_once_with(mock_gui.processing_reports_tab_frame)

    def test_on_request_process_videos(self):
        mock_gui = MagicMock()
        mgr = VideoSelectorTreeManager(mock_gui)
        mgr.trigger_batch_trajectory_processing = MagicMock()  # type: ignore[assignment]

        mgr._on_request_process_videos({})
        mgr.trigger_batch_trajectory_processing.assert_called_once_with(fallback_to_pending=True)
