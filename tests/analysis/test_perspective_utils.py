"""Golden + property tests for ``normalize_aquarium_perspective``.

This helper is the single canonical resolver for aquarium perspective aliases
(``analysis_service``, ``data_transformer`` and ``reporter_context`` all delegate
to it). It decides whether geotaxis/lateral metrics apply, so a wrong answer
silently changes which behavioural numbers reach the paper. The golden cases
pin every documented alias; the property tests pin the invariants the callers
rely on (idempotence, a closed two-value image, and insensitivity to the
hyphen/underscore/case/whitespace cosmetics users type).

Mirrors the style of ``tests/test_property_zone_scaler.py`` (``.map``-based
strategies, ``database=None``, ``@pytest.mark.property``).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective

# ASCII-only text keeps the case-folding invariants free of Unicode corner
# cases (e.g. ``"ß".upper()`` -> ``"SS"``) that are irrelevant to this resolver.
_ascii_text = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    max_size=24,
)

# Every alias the implementation maps to the canonical top-down value, plus the
# hyphen/case/whitespace cosmetics it is expected to absorb.
TOP_DOWN_INPUTS = [
    "top_down",
    "top_down_view",
    "topdown",
    "top",
    "dorsal",
    "overhead",
    "top-down",
    "Top-Down",
    "TOP_DOWN",
    "TopDown",
    "  top  ",
    "\tdorsal\n",
    "OVERHEAD",
    "Top_Down_View",
]

# Anything that is not a recognised top-down alias must fall back to lateral.
LATERAL_INPUTS = [
    "lateral",
    "Lateral",
    "side",
    "front",
    "left",
    "lateral_view",
    "",
    "   ",
    None,
    "qualquer",
    "top_down_x",  # superset of an alias -> not an alias
    "xtop",
    "downtop",
    "bottom_up",
]


class TestNormalizeGolden:
    """Known-answer cases for the documented alias table."""

    @pytest.mark.parametrize("value", TOP_DOWN_INPUTS)
    def test_top_down_aliases(self, value: str) -> None:
        assert normalize_aquarium_perspective(value) == "top_down"

    @pytest.mark.parametrize("value", LATERAL_INPUTS)
    def test_lateral_default(self, value: str | None) -> None:
        assert normalize_aquarium_perspective(value) == "lateral"


@pytest.mark.property
class TestNormalizeProperties:
    """Invariants every caller relies on."""

    @given(value=_ascii_text)
    @settings(max_examples=100, database=None)
    def test_image_is_closed(self, value: str) -> None:
        """Output is always one of the two canonical values."""
        assert normalize_aquarium_perspective(value) in {"top_down", "lateral"}

    @given(value=_ascii_text)
    @settings(max_examples=100, database=None)
    def test_idempotent(self, value: str) -> None:
        """Normalising an already-normalised value is a no-op."""
        once = normalize_aquarium_perspective(value)
        assert normalize_aquarium_perspective(once) == once

    @given(value=_ascii_text)
    @settings(max_examples=100, database=None)
    def test_case_invariant(self, value: str) -> None:
        """Resolution ignores ASCII case."""
        expected = normalize_aquarium_perspective(value)
        assert normalize_aquarium_perspective(value.upper()) == expected
        assert normalize_aquarium_perspective(value.lower()) == expected

    @given(value=_ascii_text)
    @settings(max_examples=100, database=None)
    def test_hyphen_underscore_invariant(self, value: str) -> None:
        """Hyphens and underscores are interchangeable separators."""
        expected = normalize_aquarium_perspective(value)
        assert normalize_aquarium_perspective(value.replace("_", "-")) == expected
        assert normalize_aquarium_perspective(value.replace("-", "_")) == expected

    @given(value=_ascii_text)
    @settings(max_examples=100, database=None)
    def test_outer_whitespace_invariant(self, value: str) -> None:
        """Leading/trailing whitespace is stripped before resolution."""
        expected = normalize_aquarium_perspective(value)
        assert normalize_aquarium_perspective(f"  {value}  ") == expected
