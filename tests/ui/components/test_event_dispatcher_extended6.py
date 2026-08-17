"""Extended unit tests for ui/components/event_dispatcher.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.event_dispatcher import EventDispatcher


class TestEventDispatcherExtended6:
    """Test EventDispatcher interactive edit checks, metadata filters, and thread dispatch."""

    def test_has_meaningful_analysis_metadata_empty(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({}) is False
        assert EventDispatcher._has_meaningful_analysis_metadata({"unknown": "val"}) is False

    def test_has_meaningful_analysis_metadata_valid(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "Control"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": "1"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "FishA"}) is True

    def test_finish_drawing_is_interactive_edit(self):
        gui = MagicMock()
        gui.canvas_manager.current_editing_zone = "zone_1"
        gui.edited_polygon_points = [(10, 10), (20, 20)]

        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is True

        gui.edited_polygon_points = []
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is False

    def test_run_on_ui_thread_fallback(self):
        dispatcher = object.__new__(EventDispatcher)
        gui = MagicMock()
        gui.root = None
        dispatcher.gui = gui

        called = False

        def cb():
            nonlocal called
            called = True

        dispatcher._run_on_ui_thread(cb)
        assert called is True
