"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended4:
    """Test ZoneControlsWidget banner and tree state defaults."""

    def test_widget_attributes_initial(self):
        widget = object.__new__(ZoneControlsWidget)
        widget._video_tree_expanded = True
        widget._pending_session_payload = None
        widget._context_menu_video_path = None

        assert widget._video_tree_expanded is True
        assert widget._pending_session_payload is None
        assert widget._context_menu_video_path is None

    def test_interactive_buttons_initial(self):
        widget = object.__new__(ZoneControlsWidget)
        widget.draw_roi_button = None
        widget.toggle_view_btn = None
        widget.save_arena_btn = None

        assert widget.draw_roi_button is None
        assert widget.toggle_view_btn is None
        assert widget.save_arena_btn is None
