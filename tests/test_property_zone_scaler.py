"""Property-based tests for ZoneScaler geometry functions.

Tests polygon scaling, point-in-polygon, and mask building using
Hypothesis strategies to verify geometric invariants.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.core.detection.detection_types import ZoneData
from zebtrack.core.detection.zone_scaler import ZoneScaler

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_positive_dim = st.integers(min_value=100, max_value=4000)


@st.composite
def simple_rectangle_polygon(draw: st.DrawFn) -> np.ndarray:
    """Generate a rectangular polygon within frame bounds."""
    x1 = draw(st.integers(min_value=10, max_value=500))
    y1 = draw(st.integers(min_value=10, max_value=500))
    w = draw(st.integers(min_value=20, max_value=300))
    h = draw(st.integers(min_value=20, max_value=300))
    return np.array(
        [[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]],
        dtype=np.int32,
    )


# ---------------------------------------------------------------------------
# Identity Scaling
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestZoneScalerIdentityScaling:
    """When actual dimensions == base dimensions, polygons remain unchanged."""

    @given(
        base_w=st.integers(min_value=320, max_value=1920),
        base_h=st.integers(min_value=240, max_value=1080),
        polygon=simple_rectangle_polygon(),
    )
    @settings(max_examples=30, database=None)
    def test_identity_scaling_preserves_polygon(
        self,
        base_w: int,
        base_h: int,
        polygon: np.ndarray,
    ) -> None:
        """Scaling with actual == base dimensions produces identical polygon."""
        scaler = ZoneScaler(base_width=base_w, base_height=base_h)
        zones = ZoneData(polygon=polygon.tolist(), roi_polygons=[])

        scaler.update_scaling(zones, actual_width=base_w, actual_height=base_h)

        np.testing.assert_array_equal(scaler.scaled_polygon, polygon)

    @given(
        base_w=st.integers(min_value=320, max_value=1920),
        base_h=st.integers(min_value=240, max_value=1080),
    )
    @settings(max_examples=30, database=None)
    def test_empty_polygon_stays_empty(self, base_w: int, base_h: int) -> None:
        """An empty polygon is preserved through scaling."""
        scaler = ZoneScaler(base_width=base_w, base_height=base_h)
        zones = ZoneData(polygon=[], roi_polygons=[])

        scaler.update_scaling(zones, actual_width=base_w, actual_height=base_h)

        assert scaler.scaled_polygon.size == 0


# ---------------------------------------------------------------------------
# Proportional Scaling
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestZoneScalerProportionalScaling:
    """Scaling preserves proportional relationships."""

    @given(
        polygon=simple_rectangle_polygon(),
        scale_factor=st.floats(min_value=0.5, max_value=3.0),
    )
    @settings(max_examples=30, database=None)
    def test_uniform_scale_multiplies_coordinates(
        self,
        polygon: np.ndarray,
        scale_factor: float,
    ) -> None:
        """Uniform scaling multiplies all coordinates by the scale factor."""
        base_w, base_h = 1280, 720
        actual_w = int(base_w * scale_factor)
        actual_h = int(base_h * scale_factor)

        scaler = ZoneScaler(base_width=base_w, base_height=base_h)
        zones = ZoneData(polygon=polygon.tolist(), roi_polygons=[])

        scaler.update_scaling(zones, actual_width=actual_w, actual_height=actual_h)

        # Integer rounding means we compare with tolerance
        expected = (polygon.astype(np.float64) * scale_factor).astype(np.int32)
        np.testing.assert_array_almost_equal(scaler.scaled_polygon, expected, decimal=0)


# ---------------------------------------------------------------------------
# point_in_polygon
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestPointInPolygonProperties:
    """Property tests for ZoneScaler.point_in_polygon static method."""

    def test_empty_polygon_returns_false(self) -> None:
        """An empty polygon never contains any point."""
        assert ZoneScaler.point_in_polygon((50.0, 50.0), np.array([])) is False

    @given(
        x=st.floats(min_value=11.0, max_value=99.0),
        y=st.floats(min_value=11.0, max_value=99.0),
    )
    @settings(max_examples=30, database=None)
    def test_interior_point_in_large_square(self, x: float, y: float) -> None:
        """Points strictly inside a [10,10]-[100,100] square are inside."""
        square = np.array([[10, 10], [100, 10], [100, 100], [10, 100]], dtype=np.int32)
        assert ZoneScaler.point_in_polygon((x, y), square) is True

    @given(
        x=st.floats(min_value=200.0, max_value=500.0),
        y=st.floats(min_value=200.0, max_value=500.0),
    )
    @settings(max_examples=30, database=None)
    def test_exterior_point_outside_square(self, x: float, y: float) -> None:
        """Points far outside a [10,10]-[100,100] square are outside."""
        square = np.array([[10, 10], [100, 10], [100, 100], [10, 100]], dtype=np.int32)
        assert ZoneScaler.point_in_polygon((x, y), square) is False


# ---------------------------------------------------------------------------
# _build_single_mask
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestBuildSingleMaskProperties:
    """Property tests for ZoneScaler._build_single_mask."""

    @given(
        width=st.integers(min_value=100, max_value=800),
        height=st.integers(min_value=100, max_value=800),
    )
    @settings(max_examples=20, database=None)
    def test_mask_shape_and_dtype(self, width: int, height: int) -> None:
        """Mask has correct shape (height, width) and dtype uint8."""
        polygon = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.int32)
        mask = ZoneScaler._build_single_mask(polygon, width, height)

        assert mask.shape == (height, width)
        assert mask.dtype == np.uint8

    @given(
        width=st.integers(min_value=200, max_value=800),
        height=st.integers(min_value=200, max_value=800),
    )
    @settings(max_examples=20, database=None)
    def test_mask_values_binary(self, width: int, height: int) -> None:
        """Mask values are exclusively 0 or 255."""
        polygon = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.int32)
        mask = ZoneScaler._build_single_mask(polygon, width, height)

        unique = set(np.unique(mask))
        assert unique.issubset({0, 255})

    def test_mask_interior_is_filled(self) -> None:
        """Center of a rectangle polygon has mask value 255."""
        polygon = np.array([[20, 20], [80, 20], [80, 80], [20, 80]], dtype=np.int32)
        mask = ZoneScaler._build_single_mask(polygon, 100, 100)

        assert mask[50, 50] == 255  # center of polygon

    def test_mask_exterior_is_zero(self) -> None:
        """Corner of the frame outside the polygon has mask value 0."""
        polygon = np.array([[20, 20], [80, 20], [80, 80], [20, 80]], dtype=np.int32)
        mask = ZoneScaler._build_single_mask(polygon, 100, 100)

        assert mask[0, 0] == 0  # top-left corner outside polygon
