"""Extended unit tests for ui/components/project_views/video_selector_tree_manager.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
)


class TestVideoSelectorTreeManagerExtended7:
    """Test VideoSelectorTreeManager event subscriptions and dialog manager injection."""

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
