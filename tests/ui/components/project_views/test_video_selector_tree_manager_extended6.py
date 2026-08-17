"""Extended unit tests for ui/components/project_views/video_selector_tree_manager.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
    _payload_get,
)


class TestVideoSelectorTreeManagerExtended6:
    """Test VideoSelectorTreeManager helper functions and event initialization."""

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
