"""Extended unit tests for ui/components/canvas/zone_editor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
from zebtrack.ui.components.canvas.zone_editor import ZoneEditor, bgr_color_names


class TestZoneEditorExtended:
    """Test ZoneEditor color mappings, DI properties, and clipboard lifecycle."""

    def test_bgr_color_names(self):
        colors = bgr_color_names()
        assert (0, 128, 0) in colors
        assert colors[(0, 128, 0)] == "Green" or "Verde" in colors[(0, 128, 0)]
        assert (255, 0, 0) in colors
        assert (0, 0, 255) in colors
        assert (0, 204, 204) in colors
        assert (255, 0, 255) in colors
        assert (255, 255, 0) in colors

    def test_dialog_manager_property_injected_and_fallback(self):
        manager = MagicMock()
        injected_dm = MagicMock()
        editor = ZoneEditor(manager, dialog_manager=injected_dm)
        assert editor.dialog_manager is injected_dm

        # Fallback to gui.dialog_manager
        manager.gui.dialog_manager = MagicMock()
        editor_fallback = ZoneEditor(manager, dialog_manager=None)
        assert editor_fallback.dialog_manager is manager.gui.dialog_manager

    def test_zone_context_service_property_injected_and_fallback(self):
        manager = MagicMock()
        injected_zcs = MagicMock()
        editor = ZoneEditor(manager, zone_context_service=injected_zcs)
        assert editor.zone_context_service is injected_zcs

        # Fallback to gui._zone_context_service
        manager.gui._zone_context_service = MagicMock()
        editor_fallback = ZoneEditor(manager, zone_context_service=None)
        assert editor_fallback.zone_context_service is manager.gui._zone_context_service

    def test_gui_property_and_initial_clipboard(self):
        manager = MagicMock()
        editor = ZoneEditor(manager)
        assert editor.gui is manager.gui
        assert editor._zone_clipboard is None

    def test_update_processing_mode_multi_aquarium(self):
        manager = MagicMock()
        editor = ZoneEditor(manager)
        mock_zcs = MagicMock()
        multi_data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=[[0, 0], [10, 10]])],
            video_width=640,
            video_height=480,
            sequential_processing=False,
        )
        mock_zcs.get_zone_data_for_active_context.return_value = multi_data
        editor._zone_context_service = mock_zcs
        manager.gui.controller.project_manager.get_active_zone_video.return_value = "video.mp4"
        manager.gui.controller.project_manager.project_path = "/proj"

        editor.update_processing_mode(True)
        assert multi_data.sequential_processing is True
        manager.gui.controller.project_manager.save_multi_aquarium_zone_data.assert_called_once_with(
            "video.mp4", multi_data, persist=True
        )

    def test_delete_zones_from_video_none_path(self):
        manager = MagicMock()
        editor = ZoneEditor(manager)
        editor.delete_zones_from_video(None)
        manager.gui.set_status.assert_called_once()
