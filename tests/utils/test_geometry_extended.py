"""
Extended unit tests for geometry helpers.
"""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry import polygon_centroid, snap_point_to_axes


class TestGeometryExtended:
    """Test polygon centroid and axis snapping logic."""

    def test_polygon_centroid_under_3_points(self):
        assert polygon_centroid([]) is None
        assert polygon_centroid([(0.0, 0.0), (1.0, 1.0)]) is None

    def test_polygon_centroid_zero_area(self):
        # Collinear points
        assert polygon_centroid([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]) is None

    def test_polygon_centroid_square(self):
        # Square: (0,0), (10,0), (10,10), (0,10) -> centroid (5, 5)
        points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = polygon_centroid(points)
        assert centroid is not None
        assert centroid[0] == pytest.approx(5.0)
        assert centroid[1] == pytest.approx(5.0)

    def test_snap_point_to_axes_anchor(self):
        # Point near vertical line of anchor
        snapped_v = snap_point_to_axes((10.5, 50.0), anchors=[(10.0, 20.0)], threshold=2.0)
        assert snapped_v == (10.0, 50.0)

        # Point near horizontal line of anchor
        snapped_h = snap_point_to_axes((50.0, 20.5), anchors=[(10.0, 20.0)], threshold=2.0)
        assert snapped_h == (50.0, 20.0)

    def test_snap_point_to_axes_center(self):
        # Snap to center vertical axis
        snapped_cv = snap_point_to_axes((101.0, 50.0), centers=[(100.0, 100.0)], threshold=3.0)
        assert snapped_cv == (100.0, 50.0)

        # Snap to center horizontal axis
        snapped_ch = snap_point_to_axes((50.0, 101.0), centers=[(100.0, 100.0)], threshold=3.0)
        assert snapped_ch == (50.0, 100.0)

    def test_snap_point_to_axes_exceeds_threshold(self):
        # Distance > threshold
        snapped = snap_point_to_axes((15.0, 15.0), anchors=[(0.0, 0.0)], threshold=5.0)
        assert snapped is None
