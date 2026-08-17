"""Extended unit tests for analysis/visualization_generator.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import VisualizationGenerator


class TestVisualizationGeneratorExtended6:
    """Test VisualizationGenerator attributes, roi colors, and configuration fallbacks."""

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
