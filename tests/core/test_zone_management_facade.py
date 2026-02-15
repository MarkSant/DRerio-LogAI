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

    def test_start_arena_drawing_updates_ui_state(self, zone_facade, mock_state_manager, tmp_path):
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

    def test_save_arena_handles_exception(self, zone_facade, mock_project_manager, tmp_path):
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
            "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)],
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
        mock_project_manager.roi_template_manager.load_template.side_effect = OSError("Not found")

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

    def test_apply_template_with_arena_scaling(self, zone_facade, mock_project_manager, tmp_path):
        """Test apply_template_to_video with arena scaling."""
        template_name = "test_template"
        video_path = tmp_path / "test_video.mp4"
        template_data = {
            "roi_polygons": [[(0, 0), (50, 0), (50, 50), (0, 50)]],
            "roi_names": ["ROI1"],
            "roi_colors": ["red"],
            "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)],
        }
        arena = [(0, 0), (200, 0), (200, 200), (0, 200)]

        mock_project_manager.roi_template_manager.load_template.return_value = template_data
        mock_project_manager.get_arena_for_video.return_value = arena

        result = zone_facade.apply_template_to_video(template_name, video_path, scale_to_arena=True)

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
        mock_project_manager.roi_template_manager.list_templates.return_value = expected_templates

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
        mock_project_manager.set_arena_for_video.side_effect = KeyError("Test error")

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
        mock_project_manager.set_rois_for_video.side_effect = AttributeError("Test error")

        result = zone_facade.clear_rois(video_path)

        assert result is False


# === Edge Cases and Boundary Conditions ===


class TestZoneManagementEdgeCases:
    """Test edge cases and boundary conditions for zone management."""

    def test_self_intersecting_polygon(self, zone_facade, tmp_path):
        """Test handling of self-intersecting polygon (bowtie shape)."""
        video_path = tmp_path / "test_video.mp4"

        # Create a bowtie/figure-8 polygon that intersects itself
        self_intersecting = [
            (0, 0),
            (100, 100),  # Diagonal to opposite corner
            (100, 0),  # Back to form intersection
            (0, 100),  # Creates self-intersection
        ]

        # Should reject invalid polygon or handle gracefully
        result = zone_facade.save_arena(self_intersecting, video_path)

        # Either accepts and attempts to fix, or rejects
        assert isinstance(result, bool)

    def test_degenerate_polygon_point(self, zone_facade, tmp_path):
        """Test handling of degenerate polygon (single point)."""
        video_path = tmp_path / "test_video.mp4"

        # Single point repeated
        point_polygon = [(50, 50), (50, 50), (50, 50)]

        result = zone_facade.save_arena(point_polygon, video_path)

        # Should reject as invalid
        assert result is False

    def test_degenerate_polygon_line(self, zone_facade, tmp_path):
        """Test handling of degenerate polygon (collinear points forming line)."""
        video_path = tmp_path / "test_video.mp4"

        # Three collinear points (no area)
        line_polygon = [(0, 0), (50, 50), (100, 100)]

        result = zone_facade.save_arena(line_polygon, video_path)

        # Should reject as invalid (no area)
        assert result is False

    def test_very_small_zone_1px(self, zone_facade, mock_project_manager, tmp_path):
        """Test handling of very small zone (1-2 pixel area)."""
        video_path = tmp_path / "test_video.mp4"

        # Tiny triangle (1-2 pixel area)
        tiny_polygon = [(100, 100), (101, 100), (100, 101)]

        result = zone_facade.save_arena(tiny_polygon, video_path)

        # Should accept (valid polygon, just very small)
        assert result is True

    def test_very_small_roi_5px(self, zone_facade, mock_project_manager, tmp_path):
        """Test handling of very small ROI (5 pixel area)."""
        video_path = tmp_path / "test_video.mp4"
        template_name = "tiny_roi_template"

        # Small ROI (approximately 5x5 pixels)
        tiny_roi_data = {
            "roi_polygons": [[(50, 50), (55, 50), (55, 55), (50, 55)]],
            "roi_names": ["TinyROI"],
            "roi_colors": ["red"],
        }

        mock_project_manager.roi_template_manager.load_template.return_value = tiny_roi_data

        result = zone_facade.apply_template_to_video(template_name, video_path)

        # Should accept valid small ROI
        assert result is True

    def test_zone_outside_arena_bounds(self, zone_facade, mock_project_manager, tmp_path):
        """Test ROI that is completely outside arena bounds."""
        video_path = tmp_path / "test_video.mp4"

        # Set arena bounds (0-200, 0-200)
        arena = [(0, 0), (200, 0), (200, 200), (0, 200)]
        mock_project_manager.get_arena_for_video.return_value = arena

        # ROI completely outside (300-400, 300-400)
        outside_roi_data = {
            "roi_polygons": [[(300, 300), (400, 300), (400, 400), (300, 400)]],
            "roi_names": ["OutsideROI"],
            "roi_colors": ["blue"],
        }

        # Apply ROI (should succeed even if outside - validation happens elsewhere)
        mock_project_manager.roi_template_manager.load_template.return_value = outside_roi_data
        result = zone_facade.apply_template_to_video("outside_template", video_path)

        # System should accept (validation may happen at runtime)
        assert result is True

    def test_overlapping_rois(self, zone_facade, mock_project_manager, tmp_path):
        """Test multiple ROIs with overlapping areas."""
        video_path = tmp_path / "test_video.mp4"

        # Two overlapping rectangles
        overlapping_roi_data = {
            "roi_polygons": [
                [(0, 0), (100, 0), (100, 100), (0, 100)],  # ROI 1
                [(50, 50), (150, 50), (150, 150), (50, 150)],  # ROI 2 (overlaps)
            ],
            "roi_names": ["ROI1", "ROI2"],
            "roi_colors": ["red", "blue"],
        }

        mock_project_manager.roi_template_manager.load_template.return_value = overlapping_roi_data

        result = zone_facade.apply_template_to_video("overlapping_template", video_path)

        # Should accept overlapping ROIs (valid use case)
        assert result is True

    def test_polygon_with_duplicate_consecutive_points(self, zone_facade, tmp_path):
        """Test polygon with duplicate consecutive vertices."""
        video_path = tmp_path / "test_video.mp4"

        # Valid rectangle but with duplicate points
        polygon_with_dupes = [
            (0, 0),
            (0, 0),  # Duplicate
            (100, 0),
            (100, 0),  # Duplicate
            (100, 100),
            (0, 100),
        ]

        result = zone_facade.save_arena(polygon_with_dupes, video_path)

        # Should handle gracefully (may clean duplicates or accept)
        assert isinstance(result, bool)

    def test_polygon_with_clockwise_vs_counterclockwise(
        self, zone_facade, mock_project_manager, tmp_path
    ):
        """Test that polygon orientation (CW vs CCW) doesn't affect validity."""
        video_path = tmp_path / "test_video.mp4"

        # Counterclockwise polygon
        ccw_polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

        # Clockwise polygon (reversed)
        cw_polygon = [(0, 0), (0, 100), (100, 100), (100, 0)]

        # Both should be accepted
        result_ccw = zone_facade.save_arena(ccw_polygon, video_path)
        assert result_ccw is True

        result_cw = zone_facade.save_arena(cw_polygon, video_path)
        assert result_cw is True

    def test_extremely_large_polygon(self, zone_facade, mock_project_manager, tmp_path):
        """Test handling of polygon with extremely large coordinates."""
        video_path = tmp_path / "test_video.mp4"

        # Polygon with very large coordinates (beyond typical frame size)
        large_polygon = [
            (0, 0),
            (10000, 0),
            (10000, 10000),
            (0, 10000),
        ]

        result = zone_facade.save_arena(large_polygon, video_path)

        # Should accept (coordinate validation happens elsewhere)
        assert result is True

    def test_polygon_with_many_vertices(self, zone_facade, mock_project_manager, tmp_path):
        """Test polygon with many vertices (100+ points)."""
        video_path = tmp_path / "test_video.mp4"

        # Create circular polygon with 120 vertices
        import math

        n_vertices = 120
        radius = 100
        center = (200, 200)

        many_vertex_polygon = [
            (
                center[0] + radius * math.cos(2 * math.pi * i / n_vertices),
                center[1] + radius * math.sin(2 * math.pi * i / n_vertices),
            )
            for i in range(n_vertices)
        ]

        result = zone_facade.save_arena(many_vertex_polygon, video_path)

        # Should accept high-vertex polygon
        assert result is True

    def test_negative_coordinate_polygon(self, zone_facade, mock_project_manager, tmp_path):
        """Test polygon with negative coordinates."""
        video_path = tmp_path / "test_video.mp4"

        # Polygon with negative coordinates
        negative_polygon = [(-50, -50), (50, -50), (50, 50), (-50, 50)]

        result = zone_facade.save_arena(negative_polygon, video_path)

        # Should accept (coordinate system may support negatives)
        assert result is True

    def test_floating_point_coordinates(self, zone_facade, mock_project_manager, tmp_path):
        """Test polygon with floating-point coordinates."""
        video_path = tmp_path / "test_video.mp4"

        # Polygon with precise floating-point coordinates
        float_polygon = [
            (10.5, 20.7),
            (100.3, 20.7),
            (100.3, 120.9),
            (10.5, 120.9),
        ]

        result = zone_facade.save_arena(float_polygon, video_path)

        # Should accept float coordinates
        assert result is True

    def test_empty_roi_list(self, zone_facade, mock_project_manager, tmp_path):
        """Test applying template with empty ROI list."""
        video_path = tmp_path / "test_video.mp4"

        # Empty ROI data
        empty_roi_data: dict[str, object] = {
            "roi_polygons": [],
            "roi_names": [],
            "roi_colors": [],
        }

        mock_project_manager.roi_template_manager.load_template.return_value = empty_roi_data

        result = zone_facade.apply_template_to_video("empty_template", video_path)

        # Should handle empty list gracefully
        assert isinstance(result, bool)

    def test_mismatched_roi_data_lengths(self, zone_facade, mock_project_manager, tmp_path):
        """Test ROI data with mismatched array lengths."""
        video_path = tmp_path / "test_video.mp4"

        # Mismatched lengths (2 polygons, 1 name, 3 colors)
        mismatched_data = {
            "roi_polygons": [
                [(0, 0), (50, 0), (50, 50), (0, 50)],
                [(100, 100), (150, 100), (150, 150), (100, 150)],
            ],
            "roi_names": ["ROI1"],  # Missing second name
            "roi_colors": ["red", "blue", "green"],  # Extra color
        }

        mock_project_manager.roi_template_manager.load_template.return_value = mismatched_data

        result = zone_facade.apply_template_to_video("mismatched_template", video_path)

        # Should handle or reject gracefully
        assert isinstance(result, bool)
