"""
Integration tests for Component -> GUI -> Component flows.

Task 3.1: Expand Integration Tests.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.detector import ZoneData


@pytest.mark.integration
class TestGUIComponentIntegration:
    """Tests for verifying the integrity of Component -> GUI communication."""

    def test_zone_creation_updates_ui(self, gui_fixture):
        """Test that updating zones updates the listbox via CanvasManager."""
        # Arrange
        zone_data = ZoneData(
            polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
            roi_polygons=[[(10, 10), (20, 10), (20, 20), (10, 20)]],
            roi_names=["ROI 1"],
        )

        # Mock the canvas manager's update method to verify call
        # We replace the real method with a spy-like mock
        with patch.object(gui_fixture.canvas_manager, "update_zone_listbox") as mock_update:
            # Act
            gui_fixture.update_zone_listbox(zone_data)

            # Assert
            mock_update.assert_called_once_with(zone_data)

    def test_setup_interactive_polygon(self, gui_fixture):
        """Test setup_interactive_polygon flow."""
        # Arrange
        polygon = np.array([(0, 0), (10, 10)])

        # Mock EventDispatcher since setup_interactive_polygon delegates to it
        with patch.object(gui_fixture.event_dispatcher, "setup_interactive_polygon") as mock_setup:
            # Act
            gui_fixture.setup_interactive_polygon(polygon)

            # Assert
            mock_setup.assert_called_once_with(polygon)

    def test_apply_pending_readiness_snapshot(self, gui_fixture):
        """Test apply_pending_readiness_snapshot delegation."""
        # Arrange
        snapshot = {
            "ready_with_trajectory": [],
            "ready_with_zones": [],
            "arena_only": [],
            "without_arena": [],
        }

        # Mock ProjectViewManager
        with patch.object(
            gui_fixture.project_view_manager, "apply_pending_readiness_snapshot"
        ) as mock_apply:
            # Act
            gui_fixture.apply_pending_readiness_snapshot(**snapshot)

            # Assert
            mock_apply.assert_called_once_with(**snapshot)

    def test_populate_video_selector_tree(self, gui_fixture):
        """Test video selector population delegation."""
        # Arrange
        filter_text = "test"

        # Mock ProjectViewManager
        with patch.object(
            gui_fixture.project_view_manager, "_populate_video_selector_tree"
        ) as mock_pop:
            # Act
            gui_fixture._populate_video_selector_tree(filter_text)

            # Assert
            mock_pop.assert_called_once_with(filter_text)

    def test_show_external_trigger_notice(self, gui_fixture):
        """Test show_external_trigger_notice delegation."""
        # Arrange
        label = "Session 1"
        details = {"timestamp": 12345}

        # Mock DialogManager
        with patch.object(gui_fixture.dialog_manager, "show_external_trigger_notice") as mock_show:
            # Act
            gui_fixture.show_external_trigger_notice(label, **details)

            # Assert
            mock_show.assert_called_once_with(label, **details)

    def test_clear_external_trigger_notice(self, gui_fixture):
        """Test clear_external_trigger_notice delegation."""
        # Mock DialogManager
        with patch.object(
            gui_fixture.dialog_manager, "clear_external_trigger_notice"
        ) as mock_clear:
            # Act
            gui_fixture.clear_external_trigger_notice()

            # Assert
            mock_clear.assert_called_once()

    def test_update_processing_stats(self, gui_fixture):
        """Test update_processing_stats delegation."""
        # Arrange
        stats = {
            "total_frames": 100,
            "processed_frames": 50,
            "detected_frames": 45,
            "start_time": 1000.0,
            "current_frame": 50,
        }

        # Mock StateSynchronizer
        with patch.object(gui_fixture.state_synchronizer, "update_processing_stats") as mock_update:
            # Act
            gui_fixture.update_processing_stats(**stats)

            # Assert
            mock_update.assert_called_once_with(**stats)

    def test_update_social_summary(self, gui_fixture):
        """Test update_social_summary delegation."""
        # Arrange
        kwargs = {"profile": "test_profile", "stats": {"mean_dist": 10}, "tracks": ["t1", "t2"]}

        # Mock StateSynchronizer
        with patch.object(gui_fixture.state_synchronizer, "update_social_summary") as mock_update:
            # Act
            gui_fixture.update_social_summary(**kwargs)

            # Assert
            mock_update.assert_called_once_with(**kwargs)

    def test_update_analysis_task_status(self, gui_fixture):
        """Test update_analysis_task_status delegation."""
        # Arrange
        kwargs = {"index": 1, "total": 5, "experiment_id": "exp1", "step": "tracking"}

        # Mock StateSynchronizer
        with patch.object(
            gui_fixture.state_synchronizer, "update_analysis_task_status"
        ) as mock_update:
            # Act
            gui_fixture.update_analysis_task_status(**kwargs)

            # Assert
            mock_update.assert_called_once_with(**kwargs)

    def test_refresh_project_views(self, gui_fixture):
        """Test refresh_project_views delegation."""
        # Arrange
        kwargs = {"reason": "test", "append_summary": True, "immediate": True}

        # Mock ProjectViewManager
        with patch.object(
            gui_fixture.project_view_manager, "refresh_project_views"
        ) as mock_refresh:
            # Act
            gui_fixture.refresh_project_views(**kwargs)

            # Assert
            mock_refresh.assert_called_once_with(**kwargs)

    def test_edit_selected_zone_vertices(self, gui_fixture):
        """Test edit_selected_zone_vertices delegation."""
        # Mock CanvasManager
        with patch.object(gui_fixture.canvas_manager, "edit_selected_zone_vertices") as mock_edit:
            # Act
            gui_fixture._edit_selected_zone_vertices()

            # Assert
            mock_edit.assert_called_once()

    def test_remove_selected_roi_confirm(self, gui_fixture):
        """Test removal of ROI triggers redraw."""
        # Arrange - Mock listbox selection
        mock_listbox = MagicMock()
        mock_listbox.selection.return_value = ["item1"]
        mock_listbox.item.return_value = {"values": ["📍 ROI 1"]}
        gui_fixture.zone_listbox = mock_listbox

        # Mock DialogManager to return True
        gui_fixture.dialog_manager.confirm_remove_roi = MagicMock(return_value=True)

        # Mock data retrieval
        zone_data = ZoneData(roi_names=["ROI 1"], roi_polygons=[[]], roi_colors=["red"])
        gui_fixture._get_zone_data_for_active_context = MagicMock(return_value=zone_data)

        # Mock CanvasManager redraw
        with patch.object(
            gui_fixture.canvas_manager, "redraw_zones_from_project_data"
        ) as mock_redraw:
            # Act
            gui_fixture._remove_selected_roi_confirm()

            # Assert
            mock_redraw.assert_called_once()
            # Verify data was modified
            assert "ROI 1" not in zone_data.roi_names

    def test_update_button_state(self, gui_fixture):
        """Test button state updates."""
        # Arrange
        mock_btn = MagicMock()
        gui_fixture.start_rec_btn = mock_btn

        # Act
        gui_fixture.update_button_state("start_rec", "disabled")

        # Assert
        mock_btn.config.assert_called_once_with(state="disabled")

    def test_show_progress_bar(self, gui_fixture):
        """Test show_progress_bar delegation."""
        # Arrange
        gui_fixture.analysis_display_widget = MagicMock()

        # Act
        gui_fixture.show_progress_bar()

        # Assert
        gui_fixture.analysis_display_widget.show_progress.assert_called_once()

    def test_rename_selected_roi(self, gui_fixture):
        """Test rename_selected_roi delegation."""
        # Mock DialogManager
        with patch.object(gui_fixture.dialog_manager, "rename_selected_roi") as mock_rename:
            # Act
            gui_fixture._rename_selected_roi()

            # Assert
            mock_rename.assert_called_once()
