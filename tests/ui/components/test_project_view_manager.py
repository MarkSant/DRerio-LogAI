"""
Tests for ProjectViewManager component.

Tests 33 methods organized in 7 categories:
1. Navegação e Window Management (2 métodos)
2. Project Overview Management (6 métodos)
3. Formatadores e Helpers (7 métodos)
4. Pipeline e Video Selector Management (6 métodos)
5. Processing Reports Management (6 métodos)
6. Reports Tree Management (3 métodos)
7. Event Handlers (3 métodos principais)
"""

from collections import Counter
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.project_view_manager import ProjectViewManager


@pytest.fixture
def mock_gui():
    """Create a mock GUI object with all required attributes."""
    gui = Mock()
    gui.root = Mock()
    gui.controller = Mock()
    gui.event_bus = Mock()
    gui.notebook = Mock()
    gui.controller.project_manager = Mock()
    gui.project_overview_widget = Mock()
    gui.processing_reports_widget = Mock()
    gui.event_dispatcher = Mock()
    gui.menu_manager = Mock()
    gui.widget_factory = Mock()
    gui._processing_reports_tree_metadata = {}
    gui._active_weight_display_var = Mock()
    gui._openvino_display_var = Mock()
    gui.delete_template_btn = Mock()
    gui.roi_template_var = Mock()
    gui._build_video_hierarchy_snapshot = Mock(return_value=[])
    gui._build_report_hierarchy = Mock(return_value={})
    gui.show_error = Mock()
    return gui


@pytest.fixture
def view_manager(mock_gui):
    """Create ProjectViewManager instance with mock GUI."""
    return ProjectViewManager(mock_gui)


# ==============================================================================
# CATEGORIA 1: NAVEGAÇÃO E WINDOW MANAGEMENT
# ==============================================================================


class TestNavegacaoWindowManagement:
    """Tests for navigation and window management methods."""

    def test_update_window_title_with_project(self, view_manager, mock_gui):
        """Test updating window title with project name."""
        view_manager.update_window_title("Test Project")
        mock_gui.root.title.assert_called_once_with("DRerio LogAI - Test Project")

    def test_update_window_title_without_project(self, view_manager, mock_gui):
        """Test updating window title without project name."""
        view_manager.update_window_title()
        mock_gui.root.title.assert_called_once_with("DRerio LogAI")

    def test_navigate_to_processing_reports_tab_success(self, view_manager, mock_gui):
        """Test navigating to processing reports tab successfully."""
        mock_gui.notebook.index.return_value = 3
        mock_gui.notebook.tab.side_effect = [
            "Controles",
            "Processamento e Relatórios",
        ]

        view_manager.navigate_to_processing_reports_tab()

        mock_gui.notebook.select.assert_called_once_with(1)

    def test_navigate_to_processing_reports_tab_no_notebook(self, view_manager, mock_gui):
        """Test navigating when notebook doesn't exist."""
        mock_gui.notebook = None
        view_manager.navigate_to_processing_reports_tab()
        # Should not raise exception

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_navigate_to_processing_reports_tab_not_found(self, mock_log, view_manager, mock_gui):
        """Test navigating when tab is not found."""
        mock_gui.notebook.index.return_value = 2
        mock_gui.notebook.tab.side_effect = ["Tab1", "Tab2"]

        view_manager.navigate_to_processing_reports_tab()

        mock_log.warning.assert_called_once()


# ==============================================================================
# CATEGORIA 2: PROJECT OVERVIEW MANAGEMENT
# ==============================================================================


class TestProjectOverviewManagement:
    """Tests for project overview management methods."""

    def test_request_overview_refresh_basic(self, view_manager, mock_gui):
        """Test requesting overview refresh."""
        view_manager.request_overview_refresh("test reason")

        assert view_manager._overview_refresh_pending is True
        assert view_manager._overview_refresh_after_id is not None

    def test_request_overview_refresh_force(self, view_manager, mock_gui):
        """Test forcing overview refresh."""
        view_manager._refresh_project_overview = Mock()
        
        # Mock tree.get_children() to return empty list for iteration
        mock_gui.processing_reports_widget.tree.get_children.return_value = []

        view_manager.request_overview_refresh(force=True)

        assert view_manager._overview_refresh_pending is False
        view_manager._refresh_project_overview.assert_called_once()

    def test_request_overview_refresh_already_pending(self, view_manager, mock_gui):
        """Test requesting refresh when already pending."""
        view_manager._overview_refresh_pending = True

        view_manager.request_overview_refresh()

        # Should not schedule another refresh
        assert view_manager._overview_refresh_pending is True

    def test_refresh_project_views(self, view_manager, mock_gui):
        """Test refreshing all project views."""
        view_manager._refresh_project_overview = Mock()
        view_manager._refresh_pipeline_video_table = Mock()
        view_manager._refresh_processing_reports_tab = Mock()

        mock_gui.controller.project_manager.get_project_type.return_value = "pre-recorded"

        view_manager.refresh_project_views()

        view_manager._refresh_project_overview.assert_called_once()
        view_manager._refresh_pipeline_video_table.assert_called_once()
        view_manager._refresh_processing_reports_tab.assert_called_once()

    def test_refresh_project_views_live(self, view_manager, mock_gui):
        """Test refreshing views for live project."""
        view_manager._refresh_project_overview = Mock()
        view_manager._refresh_pipeline_video_table = Mock()
        view_manager._refresh_processing_reports_tab = Mock()

        mock_gui.controller.project_manager.get_project_type.return_value = "live"

        view_manager.refresh_project_views()

        view_manager._refresh_project_overview.assert_called_once()
        view_manager._refresh_pipeline_video_table.assert_not_called()
        view_manager._refresh_processing_reports_tab.assert_called_once()

    def test_refresh_project_overview_no_widget(self, view_manager, mock_gui):
        """Test refreshing overview when widget doesn't exist."""
        delattr(mock_gui, "project_overview_widget")
        view_manager._refresh_project_overview()
        # Should not raise exception

    def test_update_project_overview_summary(self, view_manager, mock_gui):
        """Test updating overview summary."""
        mock_gui.controller.project_manager.get_all_videos.return_value = [
            {"path": "/video1.mp4"},
            {"path": "/video2.mp4"},
        ]
        mock_gui.controller.project_manager.has_trajectory_data.return_value = True
        mock_gui.controller.project_manager.has_summary_data.return_value = False

        view_manager._update_project_overview_summary()

        mock_gui.project_overview_widget.update_summary.assert_called_once()
        call_args = mock_gui.project_overview_widget.update_summary.call_args[0][0]
        assert isinstance(call_args, Counter)
        assert call_args["total"] == 2

    def test_update_project_overview_tree(self, view_manager, mock_gui):
        """Test updating overview tree."""
        hierarchy_data = [{"group": "test", "videos": []}]
        mock_gui._build_video_hierarchy_snapshot.return_value = hierarchy_data

        view_manager._update_project_overview_tree()

        mock_gui.project_overview_widget.update_tree.assert_called_once_with(hierarchy_data)


# ==============================================================================
# CATEGORIA 3: FORMATADORES E HELPERS
# ==============================================================================


class TestFormatadoresHelpers:
    """Tests for formatter and helper methods."""

    def test_format_status_label_singular(self, view_manager):
        """Test formatting status label for single video."""
        result = view_manager.format_status_label(1)
        assert result == "1 vídeo"

    def test_format_status_label_plural(self, view_manager):
        """Test formatting status label for multiple videos."""
        result = view_manager.format_status_label(5)
        assert result == "5 vídeos"

    def test_format_status_summary(self, view_manager):
        """Test formatting status summary."""
        result = view_manager.format_status_summary(10, 3)
        assert "3 vídeos" in result
        assert "(30%)" in result

    def test_format_status_summary_zero_total(self, view_manager):
        """Test formatting status summary with zero total."""
        result = view_manager.format_status_summary(0, 0)
        assert result == "0 vídeos (0%)"

    def test_format_status_ratio(self, view_manager):
        """Test formatting ratio."""
        result = view_manager.format_status_ratio(5, 10)
        assert result == "5/10"

    def test_summarize_batch_data(self, view_manager, mock_gui):
        """Test summarizing batch data."""
        videos = [{"path": "/video1.mp4"}, {"path": "/video2.mp4"}]
        mock_gui.controller.project_manager.has_arena_data.return_value = True
        mock_gui.controller.project_manager.has_roi_data.return_value = False
        mock_gui.controller.project_manager.has_trajectory_data.return_value = True
        mock_gui.controller.project_manager.has_summary_data.return_value = False

        result = view_manager.summarize_batch_data(videos)

        assert result["total"] == 2
        assert result["with_arena"] == 2
        assert result["with_rois"] == 0
        assert result["with_trajectory"] == 2
        assert result["with_summary"] == 0

    def test_format_data_badges(self, view_manager, mock_gui):
        """Test formatting data badges."""
        mock_gui.controller.project_manager.has_arena_data.return_value = True
        mock_gui.controller.project_manager.has_roi_data.return_value = True
        mock_gui.controller.project_manager.has_trajectory_data.return_value = False

        result = view_manager.format_data_badges("/video.mp4")

        assert len(result) > 0
        assert "—" not in result

    def test_format_data_badges_none(self, view_manager, mock_gui):
        """Test formatting data badges when no data."""
        mock_gui.controller.project_manager.has_arena_data.return_value = False
        mock_gui.controller.project_manager.has_roi_data.return_value = False
        mock_gui.controller.project_manager.has_trajectory_data.return_value = False

        result = view_manager.format_data_badges("/video.mp4")

        assert result == "—"

    def test_format_video_metadata(self, view_manager):
        """Test formatting video metadata."""
        video = {
            "metadata": {
                "group": "Group1",
                "day": 1,
                "subject": "Subject1",
            }
        }

        result = view_manager.format_video_metadata(video)

        assert "Grupo: Group1" in result
        assert "Dia: 1" in result
        assert "Sujeito: Subject1" in result

    def test_format_video_metadata_empty(self, view_manager):
        """Test formatting video metadata when empty."""
        video = {"metadata": {}}

        result = view_manager.format_video_metadata(video)

        assert result == "Sem metadata"

    def test_format_status_token(self):
        """Test formatting status token."""
        result = ProjectViewManager.format_status_token("complete")
        assert result == "complete"

        result = ProjectViewManager.format_status_token("")
        assert result == "—"


# ==============================================================================
# CATEGORIA 4: PIPELINE E VIDEO SELECTOR MANAGEMENT
# ==============================================================================


class TestPipelineVideoSelectorManagement:
    """Tests for pipeline and video selector management."""

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_refresh_pipeline_video_table_deprecated(self, mock_log, view_manager):
        """Test deprecated pipeline video table refresh."""
        view_manager.refresh_pipeline_video_table()
        mock_log.warning.assert_called_once()

    def test_resolve_processing_reports_video_paths(self, view_manager, mock_gui):
        """Test resolving selected video paths."""
        tree = Mock()
        tree.selection.return_value = ["item1", "item2"]
        tree.set.side_effect = ["/video1.mp4", "/video2.mp4"]

        mock_gui.processing_reports_widget.tree = tree
        mock_gui.controller.project_manager.video_exists.return_value = True

        result = view_manager.resolve_processing_reports_video_paths()

        assert len(result) == 2
        assert "/video1.mp4" in result
        assert "/video2.mp4" in result

    def test_resolve_processing_reports_video_paths_no_widget(self, view_manager, mock_gui):
        """Test resolving paths when widget doesn't exist."""
        del mock_gui.processing_reports_widget

        result = view_manager.resolve_processing_reports_video_paths()

        assert result == []

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_update_pipeline_buttons_state_deprecated(self, mock_log, view_manager):
        """Test deprecated pipeline buttons state update."""
        view_manager.update_pipeline_buttons_state()
        mock_log.warning.assert_called_once()

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_populate_video_selector_tree_deprecated(self, mock_log, view_manager):
        """Test deprecated populate video selector tree."""
        view_manager.populate_video_selector_tree("search")
        mock_log.warning.assert_called_once()

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_refresh_video_selector_tree_deprecated(self, mock_log, view_manager):
        """Test deprecated refresh video selector tree."""
        view_manager.refresh_video_selector_tree()
        mock_log.warning.assert_called_once()


# ==============================================================================
# CATEGORIA 5: PROCESSING REPORTS MANAGEMENT
# ==============================================================================


class TestProcessingReportsManagement:
    """Tests for processing reports management."""

    def test_refresh_processing_reports_tab(self, view_manager, mock_gui):
        """Test refreshing processing reports tab."""
        mock_gui.controller.project_manager.get_all_videos.return_value = []
        mock_gui.processing_reports_widget.tree = Mock()
        mock_gui.processing_reports_widget.tree.get_children.return_value = []

        view_manager.refresh_processing_reports_tab()

        mock_gui.processing_reports_widget.tree.get_children.assert_called_once()

    def test_refresh_processing_reports_tab_no_widget(self, view_manager, mock_gui):
        """Test refreshing when widget doesn't exist."""
        del mock_gui.processing_reports_widget
        view_manager.refresh_processing_reports_tab()
        # Should not raise exception

    @patch("zebtrack.ui.components.project_view_manager.os.path.exists")
    @patch("zebtrack.ui.components.project_view_manager.os.listdir")
    def test_append_processing_reports_artifacts(
        self, mock_listdir, mock_exists, view_manager, mock_gui
    ):
        """Test appending report artifacts."""
        mock_exists.return_value = True
        mock_listdir.return_value = ["report.docx", "summary.xlsx"]

        tree = Mock()
        metadata_store = {}
        mock_gui.widget_factory.build_processing_report_artifact_id.side_effect = [
            "id1",
            "id2",
        ]

        view_manager.append_processing_reports_artifacts(tree, "parent", "/results", metadata_store)

        assert tree.insert.call_count == 2
        assert len(metadata_store) == 2

    @patch("zebtrack.ui.components.project_view_manager.os.path.exists")
    def test_append_processing_reports_artifacts_no_dir(self, mock_exists, view_manager):
        """Test appending artifacts when directory doesn't exist."""
        mock_exists.return_value = False

        tree = Mock()
        view_manager.append_processing_reports_artifacts(tree, "parent", "/nonexistent", {})

        tree.insert.assert_not_called()

    def test_on_processing_reports_item_double_click_file(self, view_manager, mock_gui):
        """Test double-click on file node."""
        tree = Mock()
        tree.identify_row.return_value = "item1"
        tree.selection.return_value = []

        mock_gui.processing_reports_widget.tree = tree
        mock_gui._processing_reports_tree_metadata = {
            "item1": {"type": "file", "file_path": "/report.docx"}
        }
        view_manager._handle_report_file_node = Mock()

        event = Mock()
        event.y = 100

        view_manager.on_processing_reports_item_double_click(event)

        view_manager._handle_report_file_node.assert_called_once()

    @patch("zebtrack.ui.components.project_view_manager.os.path.exists")
    @patch("zebtrack.ui.components.project_view_manager.subprocess")
    @patch("zebtrack.ui.components.project_view_manager.os.name", "posix")
    def test_on_processing_reports_item_double_click_video(
        self, mock_subprocess, mock_exists, view_manager, mock_gui
    ):
        """Test double-click on video node."""
        tree = Mock()
        tree.identify_row.return_value = "item1"

        mock_exists.return_value = True
        mock_gui.processing_reports_widget.tree = tree
        mock_gui._processing_reports_tree_metadata = {
            "item1": {"type": "video", "results_dir": "/results"}
        }

        event = Mock()
        event.y = 100

        view_manager.on_processing_reports_item_double_click(event)

        mock_subprocess.Popen.assert_called_once_with(["xdg-open", "/results"])

    @patch("zebtrack.ui.components.project_view_manager.os.path.exists")
    @patch("zebtrack.ui.components.project_view_manager.sys.platform", "darwin")
    @patch("zebtrack.ui.components.project_view_manager.subprocess")
    def test_handle_report_file_node_macos(self, mock_subprocess, mock_exists, view_manager):
        """Test handling report file node on macOS."""
        mock_exists.return_value = True
        metadata = {"file_path": "/report.docx"}

        view_manager._handle_report_file_node(metadata)

        mock_subprocess.Popen.assert_called_once_with(["open", "/report.docx"])

    def test_on_processing_reports_generate_partial(self, view_manager, mock_gui):
        """Test generating partial report."""
        mock_gui.processing_reports_widget.get_selection.return_value = ["item1"]
        mock_gui.controller.project_manager.get_all_videos.return_value = [{"path": "/video1.mp4"}]
        mock_gui._processing_reports_tree_metadata = {
            "item1": {"type": "video", "video_path": "/video1.mp4"}
        }

        view_manager.on_processing_reports_generate_partial()

        mock_gui.event_dispatcher.publish_event.assert_called_once()


# ==============================================================================
# CATEGORIA 6: REPORTS TREE MANAGEMENT
# ==============================================================================


class TestReportsTreeManagement:
    """Tests for reports tree management."""

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_update_reports_tree_deprecated(self, mock_log, view_manager):
        """Test deprecated update reports tree."""
        view_manager.update_reports_tree()
        mock_log.warning.assert_called_once()

    def test_populate_reports_tree_from_hierarchy(self, view_manager, mock_gui):
        """Test populating reports tree from hierarchy."""
        tree = Mock()
        hierarchy = {
            "group1": {
                "display": "Group 1",
                "days": {
                    "day1": {
                        "display": "Dia 1",
                        "videos": [
                            {
                                "video_path": "/video1.mp4",
                                "metadata": {"subject": "S1"},
                                "has_arena": True,
                                "has_rois": False,
                                "has_trajectory": True,
                                "results_dir": "/results",
                            }
                        ],
                    }
                },
            }
        }

        metadata_store = {}
        view_manager.append_processing_reports_artifacts = Mock()

        view_manager._populate_reports_tree_from_hierarchy(tree, hierarchy, "", metadata_store)

        # Should have created group, day, and video nodes
        assert tree.insert.call_count >= 3
        assert len(metadata_store) >= 3

    def test_append_report_artifacts(self, view_manager):
        """Test appending report artifacts (legacy method)."""
        tree = Mock()
        view_manager.append_processing_reports_artifacts = Mock()

        view_manager.append_report_artifacts(tree, "parent", "/dir", {})

        view_manager.append_processing_reports_artifacts.assert_called_once()


# ==============================================================================
# CATEGORIA 7: EVENT HANDLERS
# ==============================================================================


class TestEventHandlers:
    """Tests for event handler methods."""

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_on_report_item_select_deprecated(self, mock_log, view_manager):
        """Test deprecated on report item select."""
        view_manager.on_report_item_select()
        mock_log.warning.assert_called_once()

    @patch("zebtrack.ui.components.project_view_manager.log")
    def test_on_report_item_double_click_deprecated(self, mock_log, view_manager):
        """Test deprecated on report item double click."""
        view_manager.on_report_item_double_click()
        mock_log.warning.assert_called_once()

    def test_on_project_overview_tree_double_click(self, view_manager, mock_gui):
        """Test double-click on project overview tree."""
        tree = Mock()
        tree.identify_row.return_value = "item1"
        tree.set.return_value = "/video1.mp4"

        mock_gui.project_overview_widget.tree = tree
        mock_gui.controller.project_manager.get_video_results_dir.return_value = "/results"

        event = Mock()
        event.y = 100

        view_manager._on_project_overview_tree_double_click_impl = Mock()

        view_manager.on_project_overview_tree_double_click(event)

        view_manager._on_project_overview_tree_double_click_impl.assert_called_once()

    @patch("zebtrack.ui.components.project_view_manager.os.path.exists")
    @patch("zebtrack.ui.components.project_view_manager.subprocess")
    @patch("zebtrack.ui.components.project_view_manager.os.name", "posix")
    def test_on_project_overview_tree_double_click_impl(
        self, mock_subprocess, mock_exists, view_manager, mock_gui
    ):
        """Test implementation of double-click handler."""
        tree = Mock()
        tree.identify_row.return_value = "item1"
        tree.set.return_value = "/video1.mp4"

        mock_exists.return_value = True
        mock_gui.project_overview_widget.tree = tree
        mock_gui.controller.project_manager.get_video_results_dir.return_value = "/results"

        event = Mock()
        event.y = 100

        view_manager._on_project_overview_tree_double_click_impl(event)

        mock_subprocess.Popen.assert_called_once_with(["xdg-open", "/results"])

    def test_on_project_overview_right_click(self, view_manager, mock_gui):
        """Test right-click on project overview tree."""
        tree = Mock()
        tree.identify_row.return_value = "item1"

        mock_gui.project_overview_widget.tree = tree

        event = Mock()
        event.y = 100

        view_manager.on_project_overview_right_click(event)

        tree.selection_set.assert_called_once_with("item1")
        mock_gui.menu_manager.show_project_overview_context_menu.assert_called_once()

    def test_update_delete_template_button_state_with_selection(self, view_manager, mock_gui):
        """Test updating delete template button state with selection."""
        mock_gui.roi_template_var.get.return_value = "template1"

        view_manager.update_delete_template_button_state()

        mock_gui.delete_template_btn.config.assert_called_once_with(state="normal")

    def test_update_delete_template_button_state_no_selection(self, view_manager, mock_gui):
        """Test updating delete template button state without selection."""
        mock_gui.roi_template_var.get.return_value = "Nenhum"

        view_manager.update_delete_template_button_state()

        mock_gui.delete_template_btn.config.assert_called_once_with(state="disabled")

    def test_refresh_openvino_summary(self, view_manager, mock_gui):
        """Test refreshing OpenVINO summary."""
        mock_gui.controller.get_openvino_cache_status.return_value = "Cache OK"

        view_manager.refresh_openvino_summary()

        mock_gui._openvino_display_var.set.assert_called_once_with("Cache OK")

    def test_refresh_openvino_summary_no_var(self, view_manager, mock_gui):
        """Test refreshing OpenVINO summary when var doesn't exist."""
        del mock_gui._openvino_display_var
        view_manager.refresh_openvino_summary()
        # Should not raise exception
