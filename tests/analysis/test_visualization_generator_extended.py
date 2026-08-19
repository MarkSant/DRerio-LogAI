"""Extended unit tests for analysis/visualization_generator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from shapely.geometry import MultiPolygon, Polygon

from zebtrack.analysis.visualization_generator import (
    PLOT_GENERATION_TIMEOUT_SECONDS,
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


class TestVisualizationGeneratorExtended:
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


class TestVisualizationGeneratorExtended2:
    def test_constants(self):
        assert PLOT_GENERATION_TIMEOUT_SECONDS == 60

    def test_normalize_color_for_matplotlib_rgb_255(self):
        rgb_255 = (255, 128, 0)
        norm = _normalize_color_for_matplotlib(rgb_255)
        assert norm[0] == pytest.approx(1.0)
        assert norm[1] == pytest.approx(128 / 255.0)
        assert norm[2] == pytest.approx(0.0)

    def test_normalize_color_for_matplotlib_already_normalized(self):
        rgb_1 = (1.0, 0.5, 0.0)
        assert _normalize_color_for_matplotlib(rgb_1) == (1.0, 0.5, 0.0)

    def test_normalize_color_for_matplotlib_string_color(self):
        assert _normalize_color_for_matplotlib("red") == "red"
        assert _normalize_color_for_matplotlib("#FF0000") == "#FF0000"


class TestVisualizationGeneratorExtended3:
    def test_constants(self):
        assert PLOT_GENERATION_TIMEOUT_SECONDS == 60

    def test_normalize_color_rgb_tuples(self):
        assert _normalize_color_for_matplotlib((255, 0, 0)) == (1.0, 0.0, 0.0)
        assert _normalize_color_for_matplotlib((0, 255, 127.5)) == (0.0, 1.0, 0.5)

    def test_normalize_color_string_and_passthrough(self):
        assert _normalize_color_for_matplotlib("red") == "red"
        assert _normalize_color_for_matplotlib("#ff0000") == "#ff0000"

    def test_generator_initialization(self):
        b_analyzer = MagicMock()
        meta = {"experiment_id": "test_exp_1"}

        gen = VisualizationGenerator(
            b_analyzer=b_analyzer,
            metadata=meta,
            sharp_turn_threshold=75.0,
            pixelcm_x=12.5,
            pixelcm_y=12.5,
        )

        assert gen.b_analyzer is b_analyzer
        assert gen.metadata == meta
        assert gen.sharp_turn_threshold == 75.0
        assert gen._pixelcm_x == 12.5
        assert gen._pixelcm_y == 12.5


class TestVisualizationGeneratorExtended4:
    def test_normalize_color_edge_cases(self):
        # Non-tuple input (string)
        assert _normalize_color_for_matplotlib("cyan") == "cyan"
        assert _normalize_color_for_matplotlib("#ff00ff") == "#ff00ff"

        # Float tuple already in 0-1
        normalized_tuple = (0.2, 0.4, 0.8)
        assert _normalize_color_for_matplotlib(normalized_tuple) == normalized_tuple

    def test_generator_sharp_turn_default(self):
        b_mock = MagicMock()
        gen = VisualizationGenerator(
            b_analyzer=b_mock,
            metadata={"experiment_id": "test_exp"},
            sharp_turn_threshold=90.0,
        )

        assert gen.sharp_turn_threshold == 90.0
        assert gen.metadata["experiment_id"] == "test_exp"


class TestVisualizationGeneratorExtended5:
    def test_normalize_perspective(self):
        assert VisualizationGenerator._normalize_perspective("top_down") == "top_down"
        assert VisualizationGenerator._normalize_perspective("topdown") == "top_down"
        assert VisualizationGenerator._normalize_perspective("top") == "top_down"
        assert VisualizationGenerator._normalize_perspective("lateral") == "lateral"
        assert VisualizationGenerator._normalize_perspective(None) == "lateral"

    def test_figure_size_from_bounds(self):
        width, height = VisualizationGenerator._figure_size_from_bounds(0.0, 0.0, 10.0, 10.0)
        assert height == 5.5
        assert width == pytest.approx(5.5)

        # Wide arena
        w_wide, h_wide = VisualizationGenerator._figure_size_from_bounds(0.0, 0.0, 100.0, 10.0)
        assert w_wide == 10.0  # Clamped to max 10.0


class TestVisualizationGeneratorExtended6:
    def test_visualization_generator_attributes_defaults(self):
        b_analyzer = MagicMock()
        metadata = {"experiment_id": "test_exp"}
        gen = VisualizationGenerator(b_analyzer=b_analyzer, metadata=metadata)

        assert gen.b_analyzer is b_analyzer
        assert gen.metadata == {"experiment_id": "test_exp"}
        assert gen.r_analyzer is None
        assert gen.roi_colors == {}
        assert gen.calibration is None
        assert gen.sharp_turn_threshold == 90.0
        assert gen.behavioral_config == {}

    def test_visualization_generator_custom_roi_colors(self):
        b_analyzer = MagicMock()
        metadata = {"experiment_id": "test_exp"}
        colors = {"ZoneA": (255, 0, 0), "ZoneB": (0, 255, 0)}
        gen = VisualizationGenerator(
            b_analyzer=b_analyzer,
            metadata=metadata,
            roi_colors=colors,
            sharp_turn_threshold=45.0,
        )

        assert gen.roi_colors == colors
        assert gen.sharp_turn_threshold == 45.0


class TestVisualizationGeneratorExtended7:
    def test_custom_behavioral_config(self):
        b_analyzer = MagicMock()
        metadata = {"experiment_id": "test_exp_02"}
        config = {"freezing_speed_threshold": 0.5, "burst_speed_threshold": 5.0}

        gen = VisualizationGenerator(
            b_analyzer=b_analyzer,
            metadata=metadata,
            behavioral_config=config,
        )
        assert gen.behavioral_config == config

    def test_sharp_turn_threshold_custom(self):
        b_analyzer = MagicMock()
        metadata = {"experiment_id": "test_exp_03"}

        gen = VisualizationGenerator(
            b_analyzer=b_analyzer,
            metadata=metadata,
            sharp_turn_threshold=60.0,
        )
        assert gen.sharp_turn_threshold == 60.0


class TestVisualizationGeneratorExtended8:
    def test_visualization_generator_metadata_dict(self):
        b_analyzer = MagicMock()
        metadata = {"experiment_id": "exp_42", "group": "Control"}

        gen = VisualizationGenerator(
            b_analyzer=b_analyzer,
            metadata=metadata,
        )
        assert gen.metadata == metadata
        assert gen.metadata["experiment_id"] == "exp_42"
        assert gen.b_analyzer is b_analyzer

    def test_visualization_generator_config_default_empty_dict(self):
        b_analyzer = MagicMock()
        gen = VisualizationGenerator(b_analyzer=b_analyzer, metadata={})
        assert gen.behavioral_config == {}


class TestVisualizationGeneratorExtended9:
    def test_visualization_generator_empty_metadata_default(self):
        b_analyzer = MagicMock()
        gen = VisualizationGenerator(b_analyzer=b_analyzer, metadata={})
        assert gen.metadata == {}
        assert gen.b_analyzer is b_analyzer

    def test_visualization_generator_with_metadata(self):
        b_analyzer = MagicMock()
        meta = {"group": "Control", "fish_id": "Fish_01"}
        gen = VisualizationGenerator(b_analyzer=b_analyzer, metadata=meta)
        assert gen.b_analyzer is b_analyzer
        assert gen.metadata["group"] == "Control"
        assert gen.metadata["fish_id"] == "Fish_01"
