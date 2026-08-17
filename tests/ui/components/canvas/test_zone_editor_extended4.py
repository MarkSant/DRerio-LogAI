"""Extended unit tests for ui/components/canvas/zone_editor.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.canvas.zone_editor import ZoneEditor


class TestZoneEditorExtended4:
    """Test ZoneEditor clipboard, property delegation, and drawing teardown."""

    def test_zone_clipboard_initial_none(self):
        cm = MagicMock()
        editor = ZoneEditor(cm)
        assert editor._zone_clipboard is None

    def test_dialog_manager_property_injected(self):
        cm = MagicMock()
        mock_dm = MagicMock()
        editor = ZoneEditor(cm, dialog_manager=mock_dm)
        assert editor.dialog_manager is mock_dm

    def test_stop_drawing_cleans_up_widgets_and_resets_mode(self):
        cm = MagicMock()
        gui = MagicMock()
        cm.gui = gui
        editor = ZoneEditor(cm)

        mock_label = MagicMock()
        mock_frame = MagicMock()
        gui.drawing_instruction_label = mock_label
        gui._drawing_buttons_frame = mock_frame

        editor.stop_drawing()
        mock_label.destroy.assert_called_once()
        mock_frame.destroy.assert_called_once()
        assert gui.drawing_instruction_label is None
        assert gui._drawing_buttons_frame is None
        assert gui.drawing_state_manager.mode is None
        assert gui.drawing_state_manager.drawing_type is None
