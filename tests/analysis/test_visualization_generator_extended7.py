"""Extended unit tests for analysis/visualization_generator.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import VisualizationGenerator


class TestVisualizationGeneratorExtended7:
    """Test VisualizationGenerator custom behavioral config and threshold properties."""

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
