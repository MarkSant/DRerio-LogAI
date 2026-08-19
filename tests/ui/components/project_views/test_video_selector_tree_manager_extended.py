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


class TestVideoSelectorTreeManagerExtended6:
    def test_payload_get_dict(self):
        d = {"reason": "load", "count": 10}
        assert _payload_get(d, "reason") == "load"
        assert _payload_get(d, "count") == 10
        assert _payload_get(d, "missing", "default") == "default"

    def test_video_selector_tree_manager_init(self):
        gui = MagicMock()
        event_bus = MagicMock()
        dialog_mgr = MagicMock()

        mgr = VideoSelectorTreeManager(
            gui,
            event_bus_v2=event_bus,
            dialog_manager=dialog_mgr,
        )

        assert mgr.gui is gui
        assert mgr.event_bus_v2 is event_bus
        assert mgr.dialog_manager is dialog_mgr
        assert mgr._overview_refresh_pending is False
        assert mgr._overview_refresh_after_id is None

    def test_dialog_manager_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        mgr = VideoSelectorTreeManager(gui, event_bus_v2=None)
        assert mgr.dialog_manager is gui.dialog_manager

    def test_overview_refresh_state_reset(self):
        gui = MagicMock()
        mgr = VideoSelectorTreeManager(gui, event_bus_v2=None)
        mgr._overview_refresh_pending = True
        mgr._overview_refresh_after_id = "after#1"

        mgr._overview_refresh_pending = False
        mgr._overview_refresh_after_id = None
        assert mgr._overview_refresh_pending is False
        assert mgr._overview_refresh_after_id is None

    def test_video_selector_tree_manager_gui_property(self):
        gui = MagicMock()
        mgr = VideoSelectorTreeManager(gui, event_bus_v2=None)
        assert mgr.gui is gui


class TestVideoSelectorTreeManagerExtended7:
    def test_video_selector_tree_manager_explicit_dialog_manager(self):
        gui = MagicMock()
        dm = MagicMock()
        mgr = VideoSelectorTreeManager(gui, dialog_manager=dm)
        assert mgr.dialog_manager is dm

    def test_video_selector_tree_manager_event_subscriptions_called(self):
        gui = MagicMock()
        event_bus = MagicMock()
        VideoSelectorTreeManager(gui, event_bus_v2=event_bus)
        assert event_bus.subscribe.call_count >= 3
