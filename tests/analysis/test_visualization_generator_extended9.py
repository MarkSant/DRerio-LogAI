"""Extended unit tests for analysis/visualization_generator.py (Part 9)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.analysis.visualization_generator import VisualizationGenerator


class TestVisualizationGeneratorExtended9:
    """Test VisualizationGenerator behavioral analyzer reference and default metadata."""

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
