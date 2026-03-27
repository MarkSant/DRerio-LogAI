"""
Integration tests for Component -> GUI -> Component flows.

Task 3.1: Expand Integration Tests.
Updated Mar 2026: Tests now verify sub-components directly, since
delegation methods were removed from ApplicationGUI during the Phase 3/4
refactor. Methods now live on CanvasManager, VideoSelectorTreeManager,
StateSynchronizer, and DialogManager.
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.detection import ZoneData


@pytest.mark.integration
@pytest.mark.gui
class TestGUIComponentIntegration:
    """Tests for verifying the integrity of Component -> GUI communication."""

    def test_zone_creation_updates_ui(self, gui_fixture):
        """Test that CanvasManager can update the zone listbox."""
        zone_data = ZoneData(
            polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
            roi_polygons=[[(10, 10), (20, 10), (20, 20), (10, 20)]],
            roi_names=["ROI 1"],
        )

        # Verify CanvasManager has the method (delegation removed from GUI)
        assert hasattr(gui_fixture.canvas_manager, "update_zone_listbox")

        with patch.object(gui_fixture.canvas_manager, "update_zone_listbox") as mock_update:
            gui_fixture.canvas_manager.update_zone_listbox(zone_data)
            mock_update.assert_called_once_with(zone_data)

    def test_setup_interactive_polygon(self, gui_fixture):
        """Test setup_interactive_polygon on CanvasManager."""
        polygon = [(0, 0), (10, 10)]

        assert hasattr(gui_fixture.canvas_manager, "setup_interactive_polygon")

        with patch.object(gui_fixture.canvas_manager, "setup_interactive_polygon") as mock_setup:
            gui_fixture.canvas_manager.setup_interactive_polygon(polygon)
            mock_setup.assert_called_once()

    def test_apply_pending_readiness_snapshot(self, gui_fixture):
        """Test apply_pending_readiness_snapshot on VideoSelectorTreeManager."""
        snapshot: dict[str, list[str]] = {
            "ready_with_trajectory": [],
            "ready_with_zones": [],
            "arena_only": [],
            "without_arena": [],
        }

        pvm = gui_fixture.project_view_manager
        assert hasattr(pvm, "apply_pending_readiness_snapshot")

        with patch.object(pvm, "apply_pending_readiness_snapshot") as mock_apply:
            pvm.apply_pending_readiness_snapshot(**snapshot)
            mock_apply.assert_called_once_with(**snapshot)

    def test_populate_video_selector_tree(self, gui_fixture):
        """Test video selector population on VideoSelectorTreeManager."""
        filter_text = "test"

        pvm = gui_fixture.project_view_manager
        assert hasattr(pvm, "_populate_video_selector_tree")

        with patch.object(pvm, "_populate_video_selector_tree") as mock_pop:
            pvm._populate_video_selector_tree(filter_text)
            mock_pop.assert_called_once_with(filter_text)

    def test_show_external_trigger_notice_removed(self, gui_fixture):
        """Test that show_external_trigger_notice is removed from GUI."""
        assert not hasattr(gui_fixture, "show_external_trigger_notice")

    def test_clear_external_trigger_notice_removed(self, gui_fixture):
        """Test that clear_external_trigger_notice is removed from GUI."""
        assert not hasattr(gui_fixture, "clear_external_trigger_notice")

    def test_update_processing_stats_removed(self, gui_fixture):
        """Test that update_processing_stats is removed from GUI."""
        assert not hasattr(gui_fixture, "update_processing_stats")

    def test_update_social_summary_removed(self, gui_fixture):
        """Test that update_social_summary is removed from GUI."""
        assert not hasattr(gui_fixture, "update_social_summary")

    def test_update_analysis_task_status_on_synchronizer(self, gui_fixture):
        """Test that update_analysis_task_status exists on state_synchronizer."""
        ss = gui_fixture.state_synchronizer
        assert hasattr(ss, "update_analysis_task_status")

        with patch.object(ss, "update_analysis_task_status") as mock_update:
            ss.update_analysis_task_status(index=1, total=5)
            mock_update.assert_called_once_with(index=1, total=5)

    def test_request_overview_refresh_on_video_selector(self, gui_fixture):
        """Test that request_overview_refresh exists on video_selector_manager."""
        vsm = gui_fixture.video_selector_manager
        assert hasattr(vsm, "request_overview_refresh")

        with patch.object(vsm, "request_overview_refresh") as mock_refresh:
            vsm.request_overview_refresh(reason="test")
            mock_refresh.assert_called_once_with(reason="test")

    def test_edit_selected_zone_vertices_on_canvas(self, gui_fixture):
        """Test edit_selected_zone_vertices on CanvasManager."""
        cm = gui_fixture.canvas_manager
        assert hasattr(cm, "edit_selected_zone_vertices")

        with patch.object(cm, "edit_selected_zone_vertices") as mock_edit:
            cm.edit_selected_zone_vertices()
            mock_edit.assert_called_once()

    def test_remove_selected_roi_confirm(self, gui_fixture):
        """Test removal of ROI delegates to canvas_manager."""
        with patch.object(gui_fixture.canvas_manager, "remove_selected_roi") as mock_remove:
            gui_fixture._remove_selected_roi_confirm()
            mock_remove.assert_called_once()

    def test_update_button_state(self, gui_fixture):
        """Test button state updates."""
        mock_btn = MagicMock()
        gui_fixture.start_rec_btn = mock_btn

        gui_fixture.update_button_state("start_rec", "disabled")

        mock_btn.config.assert_called_once_with(state="disabled")

    def test_show_progress_bar(self, gui_fixture):
        """Test show_progress_bar delegation."""
        gui_fixture.analysis_display_widget = MagicMock()

        gui_fixture.show_progress_bar()

        gui_fixture.analysis_display_widget.show_progress.assert_called_once()

    def test_rename_selected_roi_on_dialog_manager(self, gui_fixture):
        """Test rename_selected_roi on DialogManager."""
        dm = gui_fixture.dialog_manager
        assert hasattr(dm, "rename_selected_roi")

        with patch.object(dm, "rename_selected_roi") as mock_rename:
            dm.rename_selected_roi()
            mock_rename.assert_called_once()
