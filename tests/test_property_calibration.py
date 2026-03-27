"""Property-based tests for Calibration geometry functions.

Tests _order_points idempotency, permutation invariance, and
transform_bbox envelope property using Hypothesis strategies.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from zebtrack.core.detection.calibration import Calibration

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_coord = st.floats(min_value=10.0, max_value=900.0, allow_nan=False, allow_infinity=False)


@st.composite
def four_points(draw: st.DrawFn) -> np.ndarray:
    """Generate 4 arbitrary 2D points as float32 array."""
    points: list[list[float]] = []
    for _ in range(4):
        x = draw(_coord)
        y = draw(_coord)
        points.append([x, y])
    return np.array(points, dtype=np.float32)


@st.composite
def rectangle_corners(draw: st.DrawFn) -> np.ndarray:
    """Generate 4 corners of an axis-aligned rectangle."""
    x1 = draw(st.floats(min_value=50.0, max_value=400.0))
    y1 = draw(st.floats(min_value=50.0, max_value=400.0))
    w = draw(st.floats(min_value=20.0, max_value=300.0))
    h = draw(st.floats(min_value=20.0, max_value=300.0))
    return np.array(
        [[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]],
        dtype=np.float32,
    )


def _make_calibration_with_matrix(polygon: np.ndarray) -> Calibration:
    """Create a Calibration instance with a valid homography from a polygon.

    Uses reasonable real-world dimensions for a zebrafish aquarium.
    """
    return Calibration(
        polygon=polygon,
        real_width_cm=30.0,
        real_height_cm=15.0,
    )


# ---------------------------------------------------------------------------
# _order_points
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestOrderPointsProperties:
    """Property tests for Calibration._order_points."""

    @given(pts=four_points())
    @settings(
        max_examples=50,
        database=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_idempotent(self, pts: np.ndarray) -> None:
        """Ordering twice produces the same result as ordering once.

        Skips degenerate cases where sum/diff ties make argmin/argmax
        ordering ambiguous (identical or collinear points).
        """
        sums = pts.sum(axis=1).tolist()
        diffs = (pts[:, 0] - pts[:, 1]).tolist()
        assume(len(set(sums)) == 4)
        assume(len(set(diffs)) == 4)

        first = Calibration._order_points(pts)
        second = Calibration._order_points(first)
        np.testing.assert_array_equal(first, second)

    @given(pts=four_points())
    @settings(max_examples=50, database=None)
    def test_output_shape(self, pts: np.ndarray) -> None:
        """Output is always (4, 2) float32."""
        result = Calibration._order_points(pts)
        assert result.shape == (4, 2)
        assert result.dtype == np.float32

    @given(pts=rectangle_corners())
    @settings(max_examples=30, database=None)
    def test_permutation_invariant(self, pts: np.ndarray) -> None:
        """Any permutation of rectangle corners gives the same ordered output.

        Uses rectangle corners to avoid degenerate cases where sum/diff
        ties cause ambiguous ordering.
        """
        original = Calibration._order_points(pts)

        # Try a different permutation
        shuffled_idx = np.array([2, 0, 3, 1])
        shuffled = pts[shuffled_idx]
        reordered = Calibration._order_points(shuffled)

        np.testing.assert_array_almost_equal(original, reordered, decimal=3)

    @given(pts=rectangle_corners())
    @settings(max_examples=30, database=None)
    def test_consistent_winding(self, pts: np.ndarray) -> None:
        """Output corners follow TL → TR → BR → BL convention.

        For an axis-aligned rectangle:
        - corner[0] (TL) has smallest sum
        - corner[2] (BR) has largest sum
        - corner[1] (TR) has smallest diff
        - corner[3] (BL) has largest diff
        """
        result = Calibration._order_points(pts)

        sums = result.sum(axis=1)
        diffs = np.diff(result, axis=1).flatten()

        assert np.argmin(sums) == 0, "TL should have smallest sum"
        assert np.argmax(sums) == 2, "BR should have largest sum"
        assert np.argmin(diffs) == 1, "TR should have smallest diff"
        assert np.argmax(diffs) == 3, "BL should have largest diff"


# ---------------------------------------------------------------------------
# pixel_per_cm_ratio (from valid polygon)
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestPixelPerCmRatioProperties:
    """Property tests for calibration pixel_per_cm_ratio."""

    @given(polygon=rectangle_corners())
    @settings(max_examples=20, database=None)
    def test_ratio_positive(self, polygon: np.ndarray) -> None:
        """pixel_per_cm_ratio components are always positive when polygon is valid."""
        cal = _make_calibration_with_matrix(polygon)
        px_x, px_y = cal.pixel_per_cm_ratio
        # If calibration processed successfully, ratios should be positive
        if cal.homography_matrix is not None:
            assert px_x > 0.0
            assert px_y > 0.0

    @given(polygon=rectangle_corners())
    @settings(max_examples=20, database=None)
    def test_target_dims_positive(self, polygon: np.ndarray) -> None:
        """Target dimensions are positive when calibration succeeds."""
        cal = _make_calibration_with_matrix(polygon)
        if cal.homography_matrix is not None:
            w, h = cal.target_dims_px
            assert w > 0
            assert h > 0


# ---------------------------------------------------------------------------
# transform_bbox (envelope property)
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestTransformBboxProperties:
    """Property tests for Calibration.transform_bbox."""

    def test_identity_without_matrix(self) -> None:
        """Without a homography, transform_bbox returns the input unchanged."""
        cal = Calibration(polygon=None, real_width_cm=30.0, real_height_cm=15.0)
        result = cal.transform_bbox(10.0, 20.0, 100.0, 200.0)
        assert result == (10.0, 20.0, 100.0, 200.0)

    @given(polygon=rectangle_corners())
    @settings(max_examples=20, database=None)
    def test_transform_preserves_bbox_ordering(self, polygon: np.ndarray) -> None:
        """Transformed bbox has x1 <= x2 and y1 <= y2."""
        cal = _make_calibration_with_matrix(polygon)
        if cal.homography_matrix is None:
            return  # skip if calibration failed

        # Use a bbox within the polygon bounds
        bx = polygon[:, 0]
        by = polygon[:, 1]
        cx, cy = bx.mean(), by.mean()
        half = 10.0

        x1_w, y1_w, x2_w, y2_w = cal.transform_bbox(cx - half, cy - half, cx + half, cy + half)
        assert x1_w <= x2_w
        assert y1_w <= y2_w


# ---------------------------------------------------------------------------
# Aspect ratio consistency
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestCalibrationAspectRatioProperties:
    """Property tests for calibration aspect ratio preservation."""

    @given(
        real_w=st.floats(min_value=5.0, max_value=100.0),
        real_h=st.floats(min_value=5.0, max_value=100.0),
        polygon=rectangle_corners(),
    )
    @settings(max_examples=20, database=None)
    def test_px_per_cm_ratio_respects_real_dims(
        self,
        real_w: float,
        real_h: float,
        polygon: np.ndarray,
    ) -> None:
        """pixel_per_cm ratio is inversely proportional to real dimensions."""
        cal = Calibration(polygon=polygon, real_width_cm=real_w, real_height_cm=real_h)
        if cal.homography_matrix is None:
            return
        px_x, px_y = cal.pixel_per_cm_ratio
        w_px, h_px = cal.target_dims_px
        # px_per_cm = target_px / real_cm
        assert abs(px_x - w_px / real_w) < 0.01
        assert abs(px_y - h_px / real_h) < 0.01


# ---------------------------------------------------------------------------
# Null polygon safety
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestCalibrationNullSafetyProperties:
    """Property tests for null polygon handling."""

    @given(
        real_w=st.floats(min_value=1.0, max_value=100.0),
        real_h=st.floats(min_value=1.0, max_value=100.0),
    )
    @settings(max_examples=20, database=None)
    def test_none_polygon_no_homography(self, real_w: float, real_h: float) -> None:
        """Calibration with None polygon produces no homography matrix."""
        cal = Calibration(polygon=None, real_width_cm=real_w, real_height_cm=real_h)
        assert cal.homography_matrix is None
        assert cal.pixel_per_cm_ratio == (0.0, 0.0)

    @given(
        real_w=st.floats(min_value=1.0, max_value=100.0),
        real_h=st.floats(min_value=1.0, max_value=100.0),
    )
    @settings(max_examples=20, database=None)
    def test_none_polygon_warp_passthrough(self, real_w: float, real_h: float) -> None:
        """warp_frame returns original frame when polygon is None."""
        cal = Calibration(polygon=None, real_width_cm=real_w, real_height_cm=real_h)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = cal.warp_frame(frame)
        np.testing.assert_array_equal(result, frame)
