"""Extended unit tests for ui/components/canvas/event_handler.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler


class TestEventHandlerExtended5:
    """Test CanvasEventHandler canvas availability check, editing bindings, and release reset."""

    def test_editing_canvas_missing(self):
        cm = MagicMock()
        cm.gui = None
        handler = CanvasEventHandler(cm)
        assert handler._editing_canvas() is None

    def test_editing_canvas_destroyed(self):
        cm = MagicMock()
        gui = MagicMock()
        mock_canvas = MagicMock()
        mock_canvas.winfo_exists.return_value = False
        gui.video_display.canvas = mock_canvas
        cm.gui = gui

        handler = CanvasEventHandler(cm)
        assert handler._editing_canvas() is None

    def test_bind_and_unbind_editing_events(self):
        cm = MagicMock()
        gui = MagicMock()
        mock_canvas = MagicMock()
        mock_canvas.winfo_exists.return_value = True
        gui.video_display.canvas = mock_canvas
        cm.gui = gui

        handler = CanvasEventHandler(cm)
        handler.bind_editing_events()
        assert mock_canvas.bind.call_count >= 4
        mock_canvas.focus_set.assert_called_once()

        handler.unbind_editing_events()
        assert mock_canvas.unbind.call_count >= 6

    def test_handle_release_common_resets_state(self):
        cm = MagicMock()
        gui = MagicMock()
        gui._dragged_handle_index = 2
        gui._drag_offset = (5, 5)
        cm.gui = gui

        handler = CanvasEventHandler(cm)
        handler._handle_release_common()
        assert gui._dragged_handle_index is None
        assert gui._drag_offset == (0, 0)
