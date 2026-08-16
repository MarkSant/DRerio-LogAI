"""
Extended unit tests for perspective_utils in analysis/perspective_utils.py.
"""

from __future__ import annotations

import pytest

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective


class TestPerspectiveUtilsExtended:
    """Test perspective alias normalization and robustness against edge cases."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("top_down", "top_down"),
            ("TOP_DOWN", "top_down"),
            ("Top-Down", "top_down"),
            ("top-down-view", "top_down"),
            ("top_down_view", "top_down"),
            ("TOPDOWN", "top_down"),
            ("topdown", "top_down"),
            ("Top", "top_down"),
            ("TOP", "top_down"),
            ("dorsal", "top_down"),
            ("DORSAL", "top_down"),
            ("overhead", "top_down"),
            ("OVERHEAD", "top_down"),
            ("  top_down  ", "top_down"),
            ("\ttop_down\n", "top_down"),
            ("lateral", "lateral"),
            ("LATERAL", "lateral"),
            ("Side", "lateral"),
            ("front", "lateral"),
            ("bottom_up", "lateral"),
            ("", "lateral"),
            ("   ", "lateral"),
            (None, "lateral"),
        ],
    )
    def test_normalize_aquarium_perspective_cases(self, input_val: str | None, expected: str):
        assert normalize_aquarium_perspective(input_val) == expected
