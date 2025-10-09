import math

from zebtrack.utils import polygon_centroid, snap_point_to_axes


def test_polygon_centroid_returns_expected_value():
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    centroid = polygon_centroid(square)
    assert centroid is not None
    x, y = centroid
    assert math.isclose(x, 1.0)
    assert math.isclose(y, 1.0)


def test_polygon_centroid_returns_none_for_degenerate_polygon():
    line = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    assert polygon_centroid(line) is None


def test_snap_point_to_axes_uses_anchor_alignment():
    point = (10.5, 19.3)
    anchors = [(5.0, 5.0)]
    snapped = snap_point_to_axes(point, anchors=anchors, threshold=6.0)
    assert snapped is not None
    assert math.isclose(snapped[0], 5.0)
    assert math.isclose(snapped[1], 19.3)


def test_snap_point_to_axes_uses_center_alignment_to_crosshair():
    point = (8.4, 12.6)
    centers = [(10.0, 10.0)]
    snapped = snap_point_to_axes(point, centers=centers, threshold=5.0)
    assert snapped is not None
    assert math.isclose(snapped[0], centers[0][0])
    assert math.isclose(snapped[1], centers[0][1]) or math.isclose(snapped[1], point[1])


def test_snap_point_to_axes_returns_none_when_out_of_threshold():
    point = (0.0, 0.0)
    anchors = [(10.0, 10.0)]
    assert snap_point_to_axes(point, anchors=anchors, threshold=1.0) is None
