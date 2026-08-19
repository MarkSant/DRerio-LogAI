"""Extended unit tests for ui/components/canvas/event_handler.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler


class TestCanvasEventHandlerExtended:
    def test_constants(self):
        assert CanvasEventHandler.MOTION_DEBOUNCE_MS == 16
        assert CanvasEventHandler._SHIFT_MASK == 0x0001
        assert CanvasEventHandler._CTRL_MASK == 0x0004
        assert CanvasEventHandler._BODY_DRAG_EDGE_TOLERANCE == 8.0

    def test_dialog_manager_property_injected_and_fallback(self):
        manager = MagicMock()
        injected_dm = MagicMock()
        handler = CanvasEventHandler(manager, dialog_manager=injected_dm)
        assert handler.dialog_manager is injected_dm

        # Fallback to gui.dialog_manager
        manager.gui.dialog_manager = MagicMock()
        handler_fallback = CanvasEventHandler(manager, dialog_manager=None)
        assert handler_fallback.dialog_manager is manager.gui.dialog_manager

    def test_zone_context_service_property_injected_and_fallback(self):
        manager = MagicMock()
        injected_zcs = MagicMock()
        handler = CanvasEventHandler(manager, zone_context_service=injected_zcs)
        assert handler.zone_context_service is injected_zcs

        # Fallback to gui._zone_context_service
        manager.gui._zone_context_service = MagicMock()
        handler_fallback = CanvasEventHandler(manager, zone_context_service=None)
        assert handler_fallback.zone_context_service is manager.gui._zone_context_service

    def test_unbind_drawing_events(self):
        manager = MagicMock()
        mock_canvas = MagicMock()
        manager.gui.video_display.canvas = mock_canvas

        handler = CanvasEventHandler(manager)
        handler.unbind_drawing_events()

        mock_canvas.config.assert_called_with(cursor="")
        assert mock_canvas.unbind.call_count >= 8

    def test_handle_release_common(self):
        manager = MagicMock()
        handler = CanvasEventHandler(manager)
        manager.gui._dragged_handle_index = 2
        manager.gui._drag_offset = (10, 20)

        handler._handle_release_common()

        assert manager.gui._dragged_handle_index is None
        assert manager.gui._drag_offset == (0, 0)


class TestCanvasEventHandlerExtended2:
    def test_constants(self):
        assert CanvasEventHandler.MOTION_DEBOUNCE_MS == 16

    def test_dialog_manager_property_injected_and_fallback(self):
        cm = MagicMock()
        cm.gui.dialog_manager = MagicMock()

        mock_dm = MagicMock()
        handler_injected = CanvasEventHandler(cm, dialog_manager=mock_dm)
        assert handler_injected.dialog_manager is mock_dm

        handler_fallback = CanvasEventHandler(cm, dialog_manager=None)
        assert handler_fallback.dialog_manager is cm.gui.dialog_manager

    def test_zone_context_service_property_injected_and_fallback(self):
        cm = MagicMock()
        cm.gui._zone_context_service = MagicMock()

        mock_zcs = MagicMock()
        handler_injected = CanvasEventHandler(cm, zone_context_service=mock_zcs)
        assert handler_injected.zone_context_service is mock_zcs

        handler_fallback = CanvasEventHandler(cm, zone_context_service=None)
        assert handler_fallback.zone_context_service is cm.gui._zone_context_service

    def test_unbind_drawing_events(self):
        cm = MagicMock()
        canvas = MagicMock()
        cm.gui.video_display.canvas = canvas

        handler = CanvasEventHandler(cm)
        handler.unbind_drawing_events()

        canvas.config.assert_called_with(cursor="")
        assert canvas.unbind.call_count >= 8

    def test_initial_motion_debounce_state(self):
        cm = MagicMock()
        handler = CanvasEventHandler(cm)
        assert handler._motion_debounce_id is None


class TestEventHandlerExtended4:
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


class TestEventHandlerExtended5:
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
