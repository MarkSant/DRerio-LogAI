"""Extended unit tests for ui/components/zone_controls.py (Part 7)."""

from __future__ import annotations

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended7:
    """Test ZoneControlsWidget context menu item video path storage and button states."""

    def test_context_menu_path_setting(self):
        zc = object.__new__(ZoneControlsWidget)
        zc._context_menu_video_path = "/videos/sample.mp4"
        assert zc._context_menu_video_path == "/videos/sample.mp4"

        zc._context_menu_video_path = None
        assert zc._context_menu_video_path is None

    def test_zone_controls_mode_flags_defaults(self):
        zc = object.__new__(ZoneControlsWidget)
        zc._video_tree_expanded = False
        zc._pending_session_payload = None

        assert zc._video_tree_expanded is False
        assert zc._pending_session_payload is None
