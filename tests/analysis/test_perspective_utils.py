"""
Unit tests for zebtrack.analysis.perspective_utils.
"""

from __future__ import annotations

import pytest

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective


@pytest.mark.parametrize(
    "raw_input,expected",
    [
        ("top_down", "top_down"),
        ("top_down_view", "top_down"),
        ("topdown", "top_down"),
        ("top", "top_down"),
        ("dorsal", "top_down"),
        ("overhead", "top_down"),
        ("top-down", "top_down"),
        ("TOP_DOWN", "top_down"),
        ("  top_down  ", "top_down"),
        ("lateral", "lateral"),
        ("side", "lateral"),
        ("front", "lateral"),
        ("", "lateral"),
        (None, "lateral"),
        ("unknown_perspective", "lateral"),
    ],
)
def test_normalize_aquarium_perspective(raw_input: str | None, expected: str):
    assert normalize_aquarium_perspective(raw_input) == expected
