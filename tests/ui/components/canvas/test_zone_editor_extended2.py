"""Extended unit tests for ui/components/canvas/zone_editor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.zone_editor import ZoneEditor, bgr_color_names


class TestZoneEditorExtended2:
    """Test ZoneEditor colors, clipboard, and DI properties."""

    def test_bgr_color_names(self):
        colors = bgr_color_names()
        assert (0, 128, 0) in colors
        assert (255, 0, 0) in colors
        assert (0, 0, 255) in colors
        assert (0, 204, 204) in colors
        assert (255, 0, 255) in colors
        assert (255, 255, 0) in colors

    def test_dialog_manager_property_injected_and_fallback(self):
        cm = MagicMock()
        cm.gui.dialog_manager = MagicMock()

        mock_dm = MagicMock()
        editor_injected = ZoneEditor(cm, dialog_manager=mock_dm)
        assert editor_injected.dialog_manager is mock_dm

        editor_fallback = ZoneEditor(cm, dialog_manager=None)
        assert editor_fallback.dialog_manager is cm.gui.dialog_manager

    def test_zone_context_service_property_injected_and_fallback(self):
        cm = MagicMock()
        cm.gui._zone_context_service = MagicMock()

        mock_zcs = MagicMock()
        editor_injected = ZoneEditor(cm, zone_context_service=mock_zcs)
        assert editor_injected.zone_context_service is mock_zcs

        editor_fallback = ZoneEditor(cm, zone_context_service=None)
        assert editor_fallback.zone_context_service is cm.gui._zone_context_service

    def test_gui_property_and_initial_clipboard(self):
        cm = MagicMock()
        editor = ZoneEditor(cm)

        assert editor.gui is cm.gui
        assert editor._zone_clipboard is None

    def test_delete_zones_from_video_none_path(self):
        cm = MagicMock()
        editor = ZoneEditor(cm)
        # Calling with None or empty path should safely return without raising
        editor.delete_zones_from_video(None)
        editor.delete_zones_from_video("")

    def test_zone_clipboard_state(self):
        cm = MagicMock()
        editor = ZoneEditor(cm)
        assert editor._zone_clipboard is None

        editor._zone_clipboard = {"polygon": [[0, 0], [10, 10]]}
        assert editor._zone_clipboard is not None
