"""Extended unit tests for analysis/visualization_generator.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import (
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


class TestVisualizationGeneratorExtended4:
    """Test VisualizationGenerator initialization defaults and color normalizer."""

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
