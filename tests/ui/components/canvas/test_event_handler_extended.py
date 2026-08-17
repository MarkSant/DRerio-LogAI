"""Extended unit tests for ui/components/canvas/event_handler.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler


class TestCanvasEventHandlerExtended:
    """Test CanvasEventHandler debounce constant, DI properties, masks, and bindings."""

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
