"""Extended unit tests for analysis/visualization_generator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from shapely.geometry import MultiPolygon, Polygon

from zebtrack.analysis.visualization_generator import (
    PLOT_GENERATION_TIMEOUT_SECONDS,
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


class TestVisualizationGeneratorExtended:
    """Test visualization helper methods, color normalizations,
    perspective normalization, and geometry utilities.
    """

    def test_constants(self):
        assert PLOT_GENERATION_TIMEOUT_SECONDS == 60

    def test_normalize_color_for_matplotlib(self):
        # 0-255 RGB tuple
        assert _normalize_color_for_matplotlib((255, 0, 128)) == (1.0, 0.0, 128 / 255.0)

        # Already normalized float tuple
        assert _normalize_color_for_matplotlib((0.5, 0.2, 0.8)) == (0.5, 0.2, 0.8)

        # String color
        assert _normalize_color_for_matplotlib("red") == "red"

    def test_normalize_perspective(self):
        assert VisualizationGenerator._normalize_perspective("top_down") == "top_down"
        assert VisualizationGenerator._normalize_perspective("top") == "top_down"
        assert VisualizationGenerator._normalize_perspective("top-down") == "top_down"
        assert VisualizationGenerator._normalize_perspective("lateral") == "lateral"
        assert VisualizationGenerator._normalize_perspective("other") == "lateral"
        assert VisualizationGenerator._normalize_perspective(None) == "lateral"

    def test_figure_size_from_bounds(self):
        # Normal aspect (2:1)
        w, h = VisualizationGenerator._figure_size_from_bounds(0, 0, 20, 10)
        assert h == 5.5
        assert 5.0 <= w <= 10.0

        # Extreme aspect ratio clamping
        w_narrow, h_narrow = VisualizationGenerator._figure_size_from_bounds(0, 0, 1, 100)
        assert w_narrow == 5.0  # Clamped to min 5.0

    def test_iter_polygon_parts(self):
        # None
        assert VisualizationGenerator._iter_polygon_parts(None) == []

        # Single Polygon
        p1 = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
        parts = VisualizationGenerator._iter_polygon_parts(p1)
        assert len(parts) == 1
        assert parts[0] == p1

        # MultiPolygon
        p2 = Polygon([(2, 2), (2, 3), (3, 3), (3, 2)])
        mp = MultiPolygon([p1, p2])
        parts_mp = VisualizationGenerator._iter_polygon_parts(mp)
        assert len(parts_mp) == 2

    def test_roi_geometry_to_cm(self):
        mock_b_analyzer = MagicMock()
        gen = VisualizationGenerator(
            b_analyzer=mock_b_analyzer,
            metadata={"experiment_id": "exp1"},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=1000,
        )

        mock_roi_cm = MagicMock()
        mock_roi_cm.geometry = Polygon([(0, 0), (0, 5), (5, 5), (5, 0)])
        mock_roi_cm.coordinate_space = "cm"

        # Already in cm -> returns geometry directly
        assert gen._roi_geometry_to_cm(mock_roi_cm) == mock_roi_cm.geometry

        # Empty geometry -> returns None
        mock_roi_empty = MagicMock()
        mock_roi_empty.geometry = Polygon()
        assert gen._roi_geometry_to_cm(mock_roi_empty) is None
