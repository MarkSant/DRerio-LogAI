"""Extended unit tests for analysis/visualization_generator.py (Part 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import VisualizationGenerator


class TestVisualizationGeneratorExtended8:
    """Test VisualizationGenerator metadata storage and export defaults."""

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
