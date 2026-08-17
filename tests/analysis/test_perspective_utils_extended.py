"""Extended unit tests for analysis/perspective_utils.py."""

from __future__ import annotations

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective


class TestPerspectiveUtilsExtended:
    """Test aquarium perspective normalization."""

    def test_top_down_aliases(self):
        assert normalize_aquarium_perspective("top_down") == "top_down"
        assert normalize_aquarium_perspective("top-down") == "top_down"
        assert normalize_aquarium_perspective("topdown") == "top_down"
        assert normalize_aquarium_perspective("top") == "top_down"
        assert normalize_aquarium_perspective("dorsal") == "top_down"
        assert normalize_aquarium_perspective("overhead") == "top_down"
        assert normalize_aquarium_perspective("Top_Down_View") == "top_down"

    def test_lateral_fallback(self):
        assert normalize_aquarium_perspective("lateral") == "lateral"
        assert normalize_aquarium_perspective("side") == "lateral"
        assert normalize_aquarium_perspective("") == "lateral"
        assert normalize_aquarium_perspective(None) == "lateral"
        assert normalize_aquarium_perspective("unknown_perspective") == "lateral"
