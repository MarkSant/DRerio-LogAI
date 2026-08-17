"""Extended unit tests for analysis/visualization_generator.py (Part 5)."""

from __future__ import annotations

import pytest

from zebtrack.analysis.visualization_generator import VisualizationGenerator


class TestVisualizationGeneratorExtended5:
    """Test VisualizationGenerator perspective normalization and figure sizing."""

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
