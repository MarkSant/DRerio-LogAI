"""Extended unit tests for ui/components/canvas/event_handler.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler


class TestEventHandlerExtended4:
    """Test CanvasEventHandler event unbinding, drag updates, and handle press initialization."""

    def test_unbind_drawing_events(self):
        cm = MagicMock()
        gui = MagicMock()
        cm.gui = gui
        handler = CanvasEventHandler(cm)

        handler.unbind_drawing_events()
        gui.video_display.canvas.config.assert_called_once_with(cursor="")
        assert gui.video_display.canvas.unbind.call_count >= 8

    def test_on_handle_drag_no_dragged_handle(self):
        cm = MagicMock()
        gui = MagicMock()
        gui._dragged_handle_index = None
        cm.gui = gui
        handler = CanvasEventHandler(cm)

        event = MagicMock()
        # Should return early
        handler.on_handle_drag(event)

    def test_on_handle_drag_single_vertex(self):
        cm = MagicMock()
        gui = MagicMock()
        gui._dragged_handle_index = 0
        gui._drag_offset = (0.0, 0.0)
        gui.edited_polygon_points = [[10.0, 10.0], [20.0, 20.0]]
        gui.current_editing_zone = "arena"
        gui.video_display.canvas.winfo_width.return_value = 800
        gui.video_display.canvas.winfo_height.return_value = 600

        cm.gui = gui
        cm.selected_vertex_indices = set()
        cm.apply_snapping.return_value = None
        cm._canvas_to_video.return_value = (50.0, 50.0)

        handler = CanvasEventHandler(cm)
        event = MagicMock()
        event.x = 50.0
        event.y = 50.0

        handler.on_handle_drag(event)
        assert gui.edited_polygon_points[0] == [50.0, 50.0]
        cm.renderer.draw_interactive_polygon.assert_called_once()
