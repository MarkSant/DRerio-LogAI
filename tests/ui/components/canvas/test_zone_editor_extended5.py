"""Extended unit tests for ui/components/canvas/zone_editor.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.zone_editor import ZoneEditor


class TestZoneEditorExtended5:
    """Test ZoneEditor update_zone_listbox destroyed listbox guard and context service."""

    def test_update_zone_listbox_destroyed_widget_guard(self):
        cm = MagicMock()
        gui = MagicMock()
        cm.gui = gui
        mock_controls = MagicMock()
        mock_listbox = MagicMock()
        mock_listbox.winfo_exists.return_value = False
        mock_controls.zone_listbox = mock_listbox
        gui.zone_controls = mock_controls

        editor = ZoneEditor(cm)
        editor.update_zone_listbox()
        cm.renderer.redraw_zones.assert_not_called()

    def test_zone_context_service_property_injected(self):
        cm = MagicMock()
        mock_service = MagicMock()
        editor = ZoneEditor(cm, zone_context_service=mock_service)
        assert editor.zone_context_service is mock_service
