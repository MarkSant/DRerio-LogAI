"""Extended unit tests for ui/components/canvas/zone_editor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
from zebtrack.ui.components.canvas.zone_editor import ZoneEditor, bgr_color_names


class TestZoneEditorExtended:
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


class TestZoneEditorExtended2:
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


class TestZoneEditorExtended4:
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


class TestZoneEditorExtended5:
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


class TestZoneEditorNoVideoSelected:
    """The Zones sidebar when the tab is rendered before a video is chosen.

    ``get_zone_data_for_active_context`` falls back to the project-global
    ``detection_zones``. In a pre-recorded project that global entry is just
    whatever video was touched last, so listing it labels one video's arena as
    another's. The sidebar shows nothing instead, and the canvas shows the app
    logo.
    """

    @staticmethod
    def _editor(*, project_type="pre-recorded", active_video=None, pending=None):
        from zebtrack.core.detection import ZoneData

        manager = MagicMock()
        editor = ZoneEditor(manager)

        pm = manager.gui.controller.project_manager
        pm.get_project_type.return_value = project_type
        pm.get_active_zone_video.return_value = active_video

        manager.gui.pending_single_video_path = pending

        zcs = MagicMock()
        zcs.get_zone_data_for_active_context.return_value = ZoneData(
            polygon=[[0, 0], [10, 0], [10, 10]]
        )
        editor._zone_context_service = zcs
        return editor, manager

    def test_empty_state_clears_list_and_shows_logo(self):
        editor, manager = self._editor()

        editor.update_zone_listbox()

        controls = manager.gui.zone_controls
        controls.clear_zone_list.assert_called_once()
        controls.add_zone_to_list.assert_not_called()
        controls.set_draw_roi_enabled.assert_called_once_with(False)
        manager.renderer.draw_placeholder_logo.assert_called_once()
        manager.renderer.redraw_zones.assert_not_called()

    def test_selected_video_lists_its_arena(self):
        editor, manager = self._editor(active_video="C:/videos/CECT_4.mp4")

        editor.update_zone_listbox()

        controls = manager.gui.zone_controls
        listed = [call.args[0] for call in controls.add_zone_to_list.call_args_list]
        assert listed == ["arena"]
        manager.renderer.draw_placeholder_logo.assert_not_called()

    def test_pending_single_video_is_a_selection(self):
        """The single-video flow selects by ``pending_single_video_path``."""
        editor, manager = self._editor(pending="C:/videos/solo.mp4")

        editor.update_zone_listbox()

        assert manager.gui.zone_controls.add_zone_to_list.call_count == 1
        manager.renderer.draw_placeholder_logo.assert_not_called()

    def test_live_project_keeps_its_global_arena(self):
        """Live zones are project-wide, so no video selection is expected."""
        editor, manager = self._editor(project_type="live")

        editor.update_zone_listbox()

        assert manager.gui.zone_controls.add_zone_to_list.call_count == 1
        manager.renderer.draw_placeholder_logo.assert_not_called()

    def test_explicit_zone_data_is_never_blanked(self):
        """Callers passing zone_data (e.g. ZONES_UPDATED) describe a context."""
        from zebtrack.core.detection import ZoneData

        editor, manager = self._editor()

        editor.update_zone_listbox(ZoneData(polygon=[[0, 0], [5, 0], [5, 5]]))

        assert manager.gui.zone_controls.add_zone_to_list.call_count == 1
        manager.renderer.draw_placeholder_logo.assert_not_called()
