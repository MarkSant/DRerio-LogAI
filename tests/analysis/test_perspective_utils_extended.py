"""Extended unit tests for normalize_aquarium_perspective in perspective_utils.py."""

from __future__ import annotations

import pytest

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective


class TestPerspectiveUtilsExtended:
    """Test perspective normalization across all aliases and synonyms."""

    @pytest.mark.parametrize(
        "alias",
        [
            "top_down",
            "TOP_DOWN",
            "Top_Down",
            "top-down",
            "TOP-DOWN",
            "top_down_view",
            "TOP_DOWN_VIEW",
            "topdown",
            "TOPDOWN",
            "top",
            "TOP",
            "dorsal",
            "DORSAL",
            "overhead",
            "OVERHEAD",
            "  top_down  ",
            "  dorsal  ",
        ],
    )
    def test_top_down_aliases(self, alias: str):
        assert normalize_aquarium_perspective(alias) == "top_down"

    @pytest.mark.parametrize(
        "alias",
        [
            "lateral",
            "LATERAL",
            "Lateral",
            "side",
            "SIDE",
            "front",
            "FRONT",
            "unknown",
            "3d",
            "perspective",
            "",
            "   ",
            None,
        ],
    )
    def test_lateral_and_fallback_aliases(self, alias: str | None):
        assert normalize_aquarium_perspective(alias) == "lateral"
