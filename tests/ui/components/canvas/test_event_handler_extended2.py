"""Extended unit tests for ui/components/canvas/event_handler.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler


class TestCanvasEventHandlerExtended2:
    """Test CanvasEventHandler debounce constants, bindings, and DI properties."""

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
