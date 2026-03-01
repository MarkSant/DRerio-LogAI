"""Property-based tests for Recorder pure functions.

Tests IoU calculation, track ID normalisation, and snapshot deduplication
using Hypothesis strategies to verify mathematical invariants.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.io.recorder import Recorder

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Bounding box: (x1, y1, x2, y2) where x1 < x2, y1 < y2
_coord = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


@st.composite
def valid_bbox(draw: st.DrawFn) -> tuple[float, float, float, float]:
    """Generate a valid bounding box with x1 < x2 and y1 < y2."""
    x1 = draw(_coord)
    y1 = draw(_coord)
    x2 = draw(st.floats(min_value=x1 + 0.01, max_value=1001.0, allow_nan=False))
    y2 = draw(st.floats(min_value=y1 + 0.01, max_value=1001.0, allow_nan=False))
    return (x1, y1, x2, y2)


# Track ID values that should normalise to an integer
_int_like = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(min_value=-10_000.0, max_value=10_000.0, allow_nan=False, allow_infinity=False).map(
        lambda x: round(x)  # ensure integer-like float
    ),
    st.integers(min_value=-10_000, max_value=10_000).map(str),
    st.integers(min_value=-10_000, max_value=10_000).map(np.int64),
)

# Detection row for dedup tests
_frame_num = st.integers(min_value=0, max_value=1000)
_track_id = st.integers(min_value=0, max_value=100)


@st.composite
def detection_row(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a detection dict mimicking Recorder output."""
    return {
        "frame": draw(_frame_num),
        "track_id": draw(_track_id),
        "x1": draw(_coord),
        "y1": draw(_coord),
        "confidence": draw(st.floats(min_value=0.0, max_value=1.0)),
    }


# ---------------------------------------------------------------------------
# _calculate_iou
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestCalculateIoUProperties:
    """Property tests for Recorder._calculate_iou."""

    @given(box=valid_bbox())
    @settings(max_examples=50, database=None)
    def test_iou_identity(self, box: tuple[float, float, float, float]) -> None:
        """IoU of a box with itself is exactly 1.0."""
        assert Recorder._calculate_iou(box, box) == pytest.approx(1.0)

    @given(box1=valid_bbox(), box2=valid_bbox())
    @settings(max_examples=50, database=None)
    def test_iou_commutativity(
        self,
        box1: tuple[float, float, float, float],
        box2: tuple[float, float, float, float],
    ) -> None:
        """IoU(a, b) == IoU(b, a)."""
        assert Recorder._calculate_iou(box1, box2) == pytest.approx(
            Recorder._calculate_iou(box2, box1)
        )

    @given(box1=valid_bbox(), box2=valid_bbox())
    @settings(max_examples=50, database=None)
    def test_iou_bounds(
        self,
        box1: tuple[float, float, float, float],
        box2: tuple[float, float, float, float],
    ) -> None:
        """IoU is always in [0.0, 1.0]."""
        result = Recorder._calculate_iou(box1, box2)
        assert 0.0 <= result <= 1.0

    @given(box=valid_bbox())
    @settings(max_examples=30, database=None)
    def test_iou_disjoint_is_zero(self, box: tuple[float, float, float, float]) -> None:
        """A box far away from another has IoU == 0."""
        x1, y1, x2, y2 = box
        # Shift box2 far to the right so no overlap
        offset = max(x2, y2) + 10_000.0
        box2 = (x1 + offset, y1 + offset, x2 + offset, y2 + offset)
        assert Recorder._calculate_iou(box, box2) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _normalise_track_id
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestNormaliseTrackIdProperties:
    """Property tests for Recorder._normalise_track_id."""

    @given(value=st.integers(min_value=-10_000, max_value=10_000))
    @settings(max_examples=50, database=None)
    def test_int_round_trip(self, value: int) -> None:
        """An int always normalises to itself."""
        assert Recorder._normalise_track_id(value) == value

    @given(value=_int_like)
    @settings(max_examples=50, database=None)
    def test_idempotent(self, value: Any) -> None:
        """Normalising twice yields the same result as normalising once."""
        first = Recorder._normalise_track_id(value)
        second = Recorder._normalise_track_id(first)
        assert first == second

    @given(value=_int_like)
    @settings(max_examples=50, database=None)
    def test_result_type(self, value: Any) -> None:
        """Result is always int or None."""
        result = Recorder._normalise_track_id(value)
        assert result is None or isinstance(result, int)

    def test_none_returns_none(self) -> None:
        """None input maps to None."""
        assert Recorder._normalise_track_id(None) is None

    def test_nan_returns_none(self) -> None:
        """NaN float maps to None."""
        assert Recorder._normalise_track_id(float("nan")) is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string maps to None."""
        assert Recorder._normalise_track_id("") is None
        assert Recorder._normalise_track_id("   ") is None

    @given(value=st.integers(min_value=0, max_value=10_000))
    @settings(max_examples=30, database=None)
    def test_numpy_int_round_trip(self, value: int) -> None:
        """np.int64 values normalise to the equivalent Python int."""
        assert Recorder._normalise_track_id(np.int64(value)) == value


# ---------------------------------------------------------------------------
# _dedup_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestDedupSnapshotProperties:
    """Property tests for Recorder._dedup_snapshot."""

    @given(snapshot=st.lists(detection_row(), min_size=0, max_size=50))
    @settings(max_examples=50, database=None)
    def test_idempotent(self, snapshot: list[dict[str, Any]]) -> None:
        """Dedup applied twice gives the same result as once."""
        first = Recorder._dedup_snapshot(snapshot)
        second = Recorder._dedup_snapshot(first)
        assert first == second

    @given(snapshot=st.lists(detection_row(), min_size=0, max_size=50))
    @settings(max_examples=50, database=None)
    def test_length_non_increasing(self, snapshot: list[dict[str, Any]]) -> None:
        """Output length is always <= input length."""
        result = Recorder._dedup_snapshot(snapshot)
        assert len(result) <= len(snapshot)

    @given(snapshot=st.lists(detection_row(), min_size=0, max_size=50))
    @settings(max_examples=50, database=None)
    def test_no_duplicate_keys(self, snapshot: list[dict[str, Any]]) -> None:
        """Output has no duplicate (frame, track_id) pairs."""
        result = Recorder._dedup_snapshot(snapshot)
        keys = [(r.get("frame"), r.get("track_id")) for r in result]
        assert len(keys) == len(set(keys))

    @given(snapshot=st.lists(detection_row(), min_size=1, max_size=50))
    @settings(max_examples=50, database=None)
    def test_order_preserved(self, snapshot: list[dict[str, Any]]) -> None:
        """First occurrences appear in the same relative order."""
        result = Recorder._dedup_snapshot(snapshot)
        # Every element in result must be the first occurrence in snapshot
        seen: set[tuple[Any, Any]] = set()
        expected: list[dict[str, Any]] = []
        for row in snapshot:
            key = (row.get("frame"), row.get("track_id"))
            if key not in seen:
                seen.add(key)
                expected.append(row)
        assert result == expected

    def test_empty_input(self) -> None:
        """Empty list returns empty list."""
        assert Recorder._dedup_snapshot([]) == []
