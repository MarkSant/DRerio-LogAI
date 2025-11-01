"""
Unit tests for ZoneManagementFacade.

Tests the facade pattern for zone and ROI management operations,
ensuring proper coordination with ProjectManager and StateManager.
"""
from unittest.mock import Mock

import pytest

from zebtrack.core.zone_management_facade import ZoneManagementFacade


@pytest.fixture
def mock_project_manager():
    """Create mock ProjectManager."""
    pm = Mock()
    pm.set_arena_for_video = Mock()
    pm.get_arena_for_video = Mock(return_value=None)
    pm.set_rois_for_video = Mock()
    pm.get_rois_for_video = Mock(return_value={})
    pm.roi_template_manager = Mock()
    pm.roi_template_manager.load_template = Mock(return_value={})
    pm.roi_template_manager.list_templates = Mock(return_value=[])
    return pm


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    sm = Mock()
    sm.update_ui_state = Mock()
    sm.update_project_state = Mock()
    return sm


@pytest.fixture
def zone_facade(mock_project_manager, mock_state_manager):
    """Create ZoneManagementFacade with mocked dependencies."""
    return ZoneManagementFacade(
        project_manager=mock_project_manager,
        state_manager=mock_state_manager,
    )


class TestZoneManagementFacadeInitialization:
    """Test suite for ZoneManagementFacade initialization."""

    def test_init_with_all_dependencies(self, mock_project_manager, mock_state_manager):
        """Test initialization with all dependencies."""
        facade = ZoneManagementFacade(
            project_manager=mock_project_manager,
            state_manager=mock_state_manager,
        )

        assert facade.project_manager == mock_project_manager
        assert facade.state_manager == mock_state_manager


class TestZoneManagementFacadeArenaDrawing:
    """Test suite for arena drawing methods."""

    def test_start_arena_drawing_success(self, zone_facade, mock_state_manager, tmp_path):
        """Test successful start of arena drawing mode."""
        video_path = tmp_path / "test_video.mp4"

        result = zone_facade.start_arena_drawing(video_path)

        assert result is True
        mock_state_manager.update_ui_state.assert_called_once()
        mock_state_manager.update_project_state.assert_called_once()

    def test_start_arena_drawing_updates_ui_state(
        self, zone_facade, mock_state_manager, tmp_path
    ):
        """Test that start_arena_drawing updates UI state."""
        video_path = tmp_path / "test_video.mp4"

        zone_facade.start_arena_drawing(video_path)

        call_kwargs = mock_state_manager.update_ui_state.call_args[1]
        assert "canvas_view_mode" in call_kwargs

    def test_save_arena_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful save of arena polygon."""
        video_path = tmp_path / "test_video.mp4"
        polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

        result = zone_facade.save_arena(polygon, video_path)

        assert result is True
        mock_project_manager.set_arena_for_video.assert_called_once()

    def test_save_arena_invalid_polygon(self, zone_facade, tmp_path):
        """Test save_arena with invalid polygon (< 3 points)."""
        video_path = tmp_path / "test_video.mp4"
        polygon = [(0, 0), (100, 0)]  # Only 2 points

        result = zone_facade.save_arena(polygon, video_path)

        assert result is False

    def test_save_arena_handles_exception(
        self, zone_facade, mock_project_manager, tmp_path
    ):
        """Test save_arena handles exceptions gracefully."""
        video_path = tmp_path / "test_video.mp4"
        polygon = [(0, 0), (100, 0), (100, 100)]

        mock_project_manager.set_arena_for_video.side_effect = RuntimeError("Test error")

        result = zone_facade.save_arena(polygon, video_path)

        assert result is False


class TestZoneManagementFacadeROITemplates:
    """Test suite for ROI template operations."""

    def test_load_roi_template_success(self, zone_facade, mock_project_manager):
        """Test successful loading of ROI template."""
        template_name = "test_template"
        expected_data = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
        }
        mock_project_manager.roi_template_manager.load_template.return_value = expected_data

        result = zone_facade.load_roi_template(template_name)

        assert result == expected_data
        mock_project_manager.roi_template_manager.load_template.assert_called_once_with(
            template_name
        )

    def test_load_roi_template_not_found(self, zone_facade, mock_project_manager):
        """Test load_roi_template when template doesn't exist."""
        template_name = "nonexistent"
        mock_project_manager.roi_template_manager.load_template.side_effect = Exception(
            "Not found"
        )

        result = zone_facade.load_roi_template(template_name)

        assert result == {}

    def test_apply_template_to_video_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful application of template to video."""
        template_name = "test_template"
        video_path = tmp_path / "test_video.mp4"
        template_data = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
        }
        mock_project_manager.roi_template_manager.load_template.return_value = template_data

        result = zone_facade.apply_template_to_video(template_name, video_path)

        assert result is True
        mock_project_manager.set_rois_for_video.assert_called_once()

    def test_apply_template_to_video_template_not_found(self, zone_facade, tmp_path):
        """Test apply_template_to_video with nonexistent template."""
        template_name = "nonexistent"
        video_path = tmp_path / "test_video.mp4"

        result = zone_facade.apply_template_to_video(template_name, video_path)

        assert result is False

    def test_apply_template_with_arena_scaling(
        self, zone_facade, mock_project_manager, tmp_path
    ):
        """Test apply_template_to_video with arena scaling."""
        template_name = "test_template"
        video_path = tmp_path / "test_video.mp4"
        template_data = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
        }
        arena = [(0, 0), (200, 0), (200, 200), (0, 200)]

        mock_project_manager.roi_template_manager.load_template.return_value = template_data
        mock_project_manager.get_arena_for_video.return_value = arena

        result = zone_facade.apply_template_to_video(
            template_name, video_path, scale_to_arena=True
        )

        assert result is True

    def test_apply_template_without_arena_scaling(
        self, zone_facade, mock_project_manager, tmp_path
    ):
        """Test apply_template_to_video without arena scaling."""
        template_name = "test_template"
        video_path = tmp_path / "test_video.mp4"
        template_data = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
        }

        mock_project_manager.roi_template_manager.load_template.return_value = template_data

        result = zone_facade.apply_template_to_video(
            template_name, video_path, scale_to_arena=False
        )

        assert result is True

    def test_list_available_templates(self, zone_facade, mock_project_manager):
        """Test listing available ROI templates."""
        expected_templates = ["template1", "template2", "template3"]
        mock_project_manager.roi_template_manager.list_templates.return_value = (
            expected_templates
        )

        result = zone_facade.list_available_templates()

        assert result == expected_templates


class TestZoneManagementFacadeGetters:
    """Test suite for getter methods."""

    def test_get_arena_for_video_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful retrieval of arena."""
        video_path = tmp_path / "test_video.mp4"
        expected_arena = [(0, 0), (100, 0), (100, 100), (0, 100)]
        mock_project_manager.get_arena_for_video.return_value = expected_arena

        result = zone_facade.get_arena_for_video(video_path)

        assert result == expected_arena

    def test_get_arena_for_video_not_found(self, zone_facade, mock_project_manager, tmp_path):
        """Test get_arena_for_video when arena not set."""
        video_path = tmp_path / "test_video.mp4"
        mock_project_manager.get_arena_for_video.return_value = None

        result = zone_facade.get_arena_for_video(video_path)

        assert result is None

    def test_get_rois_for_video_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful retrieval of ROIs."""
        video_path = tmp_path / "test_video.mp4"
        expected_rois = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
        }
        mock_project_manager.get_rois_for_video.return_value = expected_rois

        result = zone_facade.get_rois_for_video(video_path)

        assert result == expected_rois

    def test_get_rois_for_video_not_found(self, zone_facade, mock_project_manager, tmp_path):
        """Test get_rois_for_video when ROIs not set."""
        video_path = tmp_path / "test_video.mp4"
        mock_project_manager.get_rois_for_video.return_value = None

        result = zone_facade.get_rois_for_video(video_path)

        assert result == {}


class TestZoneManagementFacadeClearOperations:
    """Test suite for clear operations."""

    def test_clear_arena_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful clearing of arena."""
        video_path = tmp_path / "test_video.mp4"

        result = zone_facade.clear_arena(video_path)

        assert result is True
        mock_project_manager.set_arena_for_video.assert_called_once_with(
            video_path=str(video_path),
            polygon=None,
        )

    def test_clear_arena_handles_exception(self, zone_facade, mock_project_manager, tmp_path):
        """Test clear_arena handles exceptions gracefully."""
        video_path = tmp_path / "test_video.mp4"
        mock_project_manager.set_arena_for_video.side_effect = RuntimeError("Test error")

        result = zone_facade.clear_arena(video_path)

        assert result is False

    def test_clear_rois_success(self, zone_facade, mock_project_manager, tmp_path):
        """Test successful clearing of ROIs."""
        video_path = tmp_path / "test_video.mp4"

        result = zone_facade.clear_rois(video_path)

        assert result is True
        mock_project_manager.set_rois_for_video.assert_called_once()

    def test_clear_rois_handles_exception(self, zone_facade, mock_project_manager, tmp_path):
        """Test clear_rois handles exceptions gracefully."""
        video_path = tmp_path / "test_video.mp4"
        mock_project_manager.set_rois_for_video.side_effect = RuntimeError("Test error")

        result = zone_facade.clear_rois(video_path)

        assert result is False
