"""Extended unit tests for utils/geometry.py."""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry import polygon_centroid, snap_point_to_axes


class TestGeometryExtended2:
    """Test polygon centroid calculations and axis snapping."""

    def test_polygon_centroid_fewer_than_3_points(self):
        assert polygon_centroid([]) is None
        assert polygon_centroid([(0.0, 0.0)]) is None
        assert polygon_centroid([(0.0, 0.0), (10.0, 10.0)]) is None

    def test_polygon_centroid_zero_area(self):
        # Collinear points have zero area
        assert polygon_centroid([(0.0, 0.0), (5.0, 5.0), (10.0, 10.0)]) is None

    def test_polygon_centroid_square(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = polygon_centroid(square)
        assert centroid is not None
        assert centroid[0] == pytest.approx(5.0)
        assert centroid[1] == pytest.approx(5.0)

    def test_snap_point_to_axes_no_anchors_or_centers(self):
        assert snap_point_to_axes((10.0, 20.0)) is None
        assert snap_point_to_axes((10.0, 20.0), anchors=[], centers=[]) is None

    def test_snap_point_to_axes_anchor_horizontal_and_vertical(self):
        # Point near vertical line of anchor
        res_v = snap_point_to_axes((10.5, 50.0), anchors=[(10.0, 20.0)], threshold=2.0)
        assert res_v is not None
        assert res_v[0] == pytest.approx(10.0)
        assert res_v[1] == pytest.approx(50.0)

        # Point near horizontal line of anchor
        res_h = snap_point_to_axes((50.0, 20.8), anchors=[(10.0, 20.0)], threshold=2.0)
        assert res_h is not None
        assert res_h[0] == pytest.approx(50.0)
        assert res_h[1] == pytest.approx(20.0)

    def test_snap_point_to_axes_center_vertical(self):
        # Point near center vertical axis
        res = snap_point_to_axes((100.2, 50.0), centers=[(100.0, 100.0)], threshold=2.0)
        assert res is not None
        assert res[0] == pytest.approx(100.0)
        assert res[1] == pytest.approx(50.0)

    def test_snap_point_to_axes_beyond_threshold(self):
        res = snap_point_to_axes((10.0, 10.0), anchors=[(100.0, 100.0)], threshold=5.0)
        assert res is None
