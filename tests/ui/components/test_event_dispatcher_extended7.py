"""Extended unit tests for ui/components/event_dispatcher.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.event_dispatcher import EventDispatcher


class TestEventDispatcherExtended7:
    """Test EventDispatcher require_gui validation, defaults, and interactive edit checks."""

    def test_require_gui_raises_when_none(self):
        dispatcher = object.__new__(EventDispatcher)
        dispatcher.gui = None

        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()

    def test_require_gui_returns_gui(self):
        dispatcher = object.__new__(EventDispatcher)
        mock_gui = MagicMock()
        dispatcher.gui = mock_gui

        assert dispatcher._require_gui() is mock_gui

    def test_finish_drawing_is_interactive_edit_no_points(self):
        mock_gui = MagicMock()
        mock_gui.current_editing_zone = "arena"
        mock_gui.edited_polygon_points = []

        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is False

    def test_has_meaningful_analysis_metadata_keys(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "Control"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": 1}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "Fish1"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"extra_field": "val"}) is False
