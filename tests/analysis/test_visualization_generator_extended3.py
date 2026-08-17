"""Extended unit tests for analysis/visualization_generator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import (
    PLOT_GENERATION_TIMEOUT_SECONDS,
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


class TestVisualizationGeneratorExtended3:
    """Test VisualizationGenerator timeouts, initialization, and color normalization."""

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
