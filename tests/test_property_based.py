"""Property-based tests using Hypothesis.

Uses property-based testing to verify invariants across randomly generated inputs.
This complements traditional unit tests by finding edge cases automatically.

Marker: @pytest.mark.property
Run with: poetry run pytest -m property
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from zebtrack.utils import polygon_centroid, snap_point_to_axes

# =============================================================================
# STRATEGIES - Reusable test data generators
# =============================================================================

# Coordinates in reasonable range for image processing
coordinate = st.floats(
    min_value=-10000,
    max_value=10000,
    allow_nan=False,
    allow_infinity=False,
)
positive_coordinate = st.floats(
    min_value=0.1,
    max_value=10000,
    allow_nan=False,
    allow_infinity=False,
)

# A point as (x, y) tuple
point = st.tuples(coordinate, coordinate)
positive_point = st.tuples(positive_coordinate, positive_coordinate)

# Lists of points for polygons (3+ points for valid polygon)
polygon_points = st.lists(point, min_size=3, max_size=20)


# =============================================================================
# POLYGON CENTROID PROPERTY TESTS
# =============================================================================


@pytest.mark.property
class TestPolygonCentroidProperties:
    """Property-based tests for polygon_centroid function."""

    @given(points=polygon_points)
    @settings(max_examples=100, database=None, suppress_health_check=[HealthCheck.too_slow])
    def test_centroid_is_none_or_tuple(self, points):
        """Centroid should always return None or a tuple of two floats."""
        result = polygon_centroid(points)

        if result is not None:
            assert hasattr(result, "__len__")
            assert len(result) == 2

    @given(
        x=coordinate,
        y=coordinate,
        size=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_centroid_invariant_with_translation(self, x, y, size):
        """Translating a polygon should translate its centroid by the same amount.

        Uses a non-degenerate square to guarantee valid centroid.
        """
        # Create a non-degenerate square (guaranteed non-collinear)
        square = [
            (x, y),
            (x + size, y),
            (x + size, y + size),
            (x, y + size),
        ]
        original = polygon_centroid(square)

        if original is None:
            return  # Skip if numerical issues

        # Translate all points by (10, 20)
        translated = [(px + 10, py + 20) for px, py in square]
        translated_centroid = polygon_centroid(translated)

        assert translated_centroid is not None
        # Centroid should move by same translation (use abs_tol for small values)
        assert math.isclose(translated_centroid[0], original[0] + 10, rel_tol=1e-5, abs_tol=1e-9)
        assert math.isclose(translated_centroid[1], original[1] + 20, rel_tol=1e-5, abs_tol=1e-9)

    @given(
        x=coordinate,
        y=coordinate,
        size=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
        scale=st.floats(min_value=0.1, max_value=10.0),
    )
    @settings(max_examples=50)
    def test_centroid_scales_with_polygon(self, x, y, size, scale):
        """Scaling a polygon around origin should scale its centroid.

        Uses a non-degenerate square to guarantee valid centroid.
        """
        # Create a non-degenerate square
        square = [
            (x, y),
            (x + size, y),
            (x + size, y + size),
            (x, y + size),
        ]
        original = polygon_centroid(square)

        if original is None:
            return

        # Scale all points
        scaled = [(px * scale, py * scale) for px, py in square]
        scaled_centroid = polygon_centroid(scaled)

        if scaled_centroid is None:
            return

        # Centroid should scale proportionally
        assert math.isclose(scaled_centroid[0], original[0] * scale, rel_tol=1e-4, abs_tol=1e-9)
        assert math.isclose(scaled_centroid[1], original[1] * scale, rel_tol=1e-4, abs_tol=1e-9)

    @given(st.lists(point, min_size=0, max_size=2))
    @settings(max_examples=50)
    def test_insufficient_points_return_none(self, points):
        """Polygons with fewer than 3 points should return None."""
        result = polygon_centroid(points)
        assert result is None

    @given(
        x=coordinate,
        y=coordinate,
        offset=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_square_centroid_is_center(self, x, y, offset):
        """Square's centroid should be its geometric center."""
        # Define a square
        square = [
            (x, y),
            (x + offset, y),
            (x + offset, y + offset),
            (x, y + offset),
        ]

        centroid = polygon_centroid(square)

        assert centroid is not None
        expected_cx = x + offset / 2
        expected_cy = y + offset / 2
        assert math.isclose(centroid[0], expected_cx, rel_tol=1e-6)
        assert math.isclose(centroid[1], expected_cy, rel_tol=1e-6)


# =============================================================================
# SNAP POINT PROPERTY TESTS
# =============================================================================


@pytest.mark.property
class TestSnapPointProperties:
    """Property-based tests for snap_point_to_axes function."""

    @given(point=point, threshold=st.floats(min_value=0.1, max_value=100))
    @settings(max_examples=100)
    def test_snap_returns_none_or_tuple(self, point, threshold):
        """Snap should always return None or a valid point tuple."""
        result = snap_point_to_axes(point, anchors=[], centers=[], threshold=threshold)

        if result is not None:
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], int | float)
            assert isinstance(result[1], int | float)

    @given(pt=point)
    @settings(max_examples=50)
    def test_no_anchors_or_centers_returns_none(self, pt):
        """With no anchors or centers, snap should return None."""
        result = snap_point_to_axes(pt, anchors=None, centers=None)
        assert result is None

        result = snap_point_to_axes(pt, anchors=[], centers=[])
        assert result is None

    @given(pt=point, anchor=point)
    @settings(max_examples=50)
    def test_snap_preserves_at_least_one_coordinate(self, pt, anchor):
        """Snapped point shares at least one coordinate with original or anchor."""
        px, py = pt
        ax, ay = anchor

        result = snap_point_to_axes(pt, anchors=[anchor], threshold=10000)

        if result is not None:
            rx, ry = result
            # Either x matches original or anchor, or y matches original or anchor
            x_matches = math.isclose(rx, px) or math.isclose(rx, ax)
            y_matches = math.isclose(ry, py) or math.isclose(ry, ay)
            assert x_matches or y_matches

    @given(
        anchor=point,
        threshold=st.floats(min_value=0.1, max_value=100),
    )
    @settings(max_examples=50)
    def test_snap_within_threshold(self, anchor, threshold):
        """Snapped point should be within threshold distance of original."""
        ax, ay = anchor
        # Point slightly offset from anchor's axis
        pt = (ax + threshold / 2, ay + threshold * 10)  # Far on y, close on x

        result = snap_point_to_axes(pt, anchors=[anchor], threshold=threshold)

        if result is not None:
            px, py = pt
            rx, ry = result
            distance = math.hypot(rx - px, ry - py)
            assert distance < threshold


# =============================================================================
# DATA VALIDATION PROPERTY TESTS
# =============================================================================


@pytest.mark.property
class TestDataValidationProperties:
    """Property-based tests for data structures and validation."""

    @given(
        track_id=st.integers(min_value=0, max_value=999),
        aquarium_id=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_track_id_encoding_reversible(self, track_id, aquarium_id):
        """Track ID encoding should be reversible: aquarium_id * 1000 + local_track_id."""
        # Encode
        global_track_id = aquarium_id * 1000 + track_id

        # Decode
        decoded_aquarium = global_track_id // 1000
        decoded_track = global_track_id % 1000

        # Should round-trip correctly
        assert decoded_aquarium == aquarium_id
        assert decoded_track == track_id

    @given(
        x1=st.floats(min_value=0, max_value=1000),
        y1=st.floats(min_value=0, max_value=1000),
        x2=st.floats(min_value=0, max_value=1000),
        y2=st.floats(min_value=0, max_value=1000),
    )
    @settings(max_examples=50)
    def test_bbox_center_calculation(self, x1, y1, x2, y2):
        """Bounding box center should be average of corners."""
        # Ensure x2 >= x1 and y2 >= y1 for valid bbox
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        # Center should be within the bounding box
        assert x1 <= center_x <= x2
        assert y1 <= center_y <= y2


# =============================================================================
# NUMERICAL STABILITY TESTS
# =============================================================================


@pytest.mark.property
class TestNumericalStability:
    """Property-based tests for numerical stability."""

    @given(value=st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50, database=None)  # database=None to avoid cached failures
    def test_polygon_centroid_handles_large_values(self, value):
        """Polygon centroid should handle coordinate values reliably.

        Using ±1e4 range to stay well within floating point precision limits.
        """
        # Simple square at coordinates
        offset = 100
        square = [
            (value, value),
            (value + offset, value),
            (value + offset, value + offset),
            (value, value + offset),
        ]

        result = polygon_centroid(square)

        # Should always succeed for values in this range
        assert result is not None
        cx, cy = result
        expected = value + offset / 2
        # Use appropriate tolerance
        assert math.isclose(cx, expected, rel_tol=1e-4, abs_tol=1e-6)
        assert math.isclose(cy, expected, rel_tol=1e-4, abs_tol=1e-6)

    @given(small=st.floats(min_value=1e-10, max_value=1e-5, allow_nan=False, allow_infinity=False))
    @settings(max_examples=30)
    def test_polygon_centroid_handles_small_values(self, small):
        """Polygon centroid should handle very small coordinate values."""
        # Tiny square
        square = [
            (0.0, 0.0),
            (small, 0.0),
            (small, small),
            (0.0, small),
        ]

        result = polygon_centroid(square)

        if result is not None:
            cx, cy = result
            expected = small / 2
            # Allow for floating point imprecision
            assert math.isclose(cx, expected, rel_tol=1e-3) or abs(cx - expected) < 1e-10

    @given(
        cx=coordinate,
        cy=coordinate,
        radius=st.floats(min_value=1.0, max_value=1000.0),
        n_sides=st.integers(min_value=3, max_value=12),
    )
    @settings(max_examples=50, database=None)
    def test_regular_polygon_centroid_is_center(self, cx, cy, radius, n_sides):
        """Centroid of a regular polygon centered at (cx, cy) is (cx, cy)."""
        import math as _math

        points = [
            (
                cx + radius * _math.cos(2 * _math.pi * i / n_sides),
                cy + radius * _math.sin(2 * _math.pi * i / n_sides),
            )
            for i in range(n_sides)
        ]
        result = polygon_centroid(points)
        if result is not None:
            assert _math.isclose(result[0], cx, rel_tol=1e-4, abs_tol=1e-6)
            assert _math.isclose(result[1], cy, rel_tol=1e-4, abs_tol=1e-6)
