"""Tests for zebtrack.utils.geometry module."""

from zebtrack.utils.geometry import polygon_centroid, snap_point_to_axes


class TestPolygonCentroid:
    """Tests for polygon_centroid function (duplicated from utils.py tests)."""

    def test_polygon_centroid_triangle(self):
        """polygon_centroid should calculate correct centroid for triangle."""
        triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
        centroid = polygon_centroid(triangle)

        assert centroid is not None
        cx, cy = centroid
        # Centroid of triangle with vertices at (0,0), (10,0), (5,10) is (5, 10/3)
        assert abs(cx - 5.0) < 0.001
        assert abs(cy - 10.0 / 3.0) < 0.001

    def test_polygon_centroid_square(self):
        """polygon_centroid should calculate correct centroid for square."""
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = polygon_centroid(square)

        assert centroid is not None
        cx, cy = centroid
        assert abs(cx - 5.0) < 0.001
        assert abs(cy - 5.0) < 0.001

    def test_polygon_centroid_returns_none_for_less_than_3_points(self):
        """polygon_centroid should return None for < 3 points."""
        assert polygon_centroid([]) is None
        assert polygon_centroid([(0.0, 0.0)]) is None
        assert polygon_centroid([(0.0, 0.0), (1.0, 1.0)]) is None

    def test_polygon_centroid_returns_none_for_degenerate_polygon(self):
        """polygon_centroid should return None for polygon with zero area."""
        # Collinear points (zero area)
        collinear = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        result = polygon_centroid(collinear)
        assert result is None

    def test_polygon_centroid_pentagon(self):
        """polygon_centroid should work with complex polygons."""
        # Regular pentagon (approximate)
        pentagon = [(5.0, 0.0), (10.0, 3.0), (8.0, 8.0), (2.0, 8.0), (0.0, 3.0)]
        centroid = polygon_centroid(pentagon)

        assert centroid is not None
        cx, cy = centroid
        # Centroid should be somewhere near the center
        assert 4.0 < cx < 6.0
        assert 4.0 < cy < 6.0


class TestSnapPointToAxes:
    """Tests for snap_point_to_axes function (duplicated from utils.py tests)."""

    def test_snap_point_to_axes_snaps_to_anchor_horizontal(self):
        """snap_point_to_axes should snap to horizontal axis of anchor."""
        point = (50.0, 103.0)  # 3 pixels away from y=100
        anchors = [(10.0, 100.0)]

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        assert snapped == (50.0, 100.0)  # Snapped to anchor's y

    def test_snap_point_to_axes_snaps_to_anchor_vertical(self):
        """snap_point_to_axes should snap to vertical axis of anchor."""
        point = (103.0, 50.0)  # 3 pixels away from x=100
        anchors = [(100.0, 10.0)]

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        assert snapped == (100.0, 50.0)  # Snapped to anchor's x

    def test_snap_point_to_axes_snaps_to_center(self):
        """snap_point_to_axes should snap to center axes."""
        point = (52.0, 48.0)  # Close to (50, 50)
        centers = [(50.0, 50.0)]

        snapped = snap_point_to_axes(point, centers=centers, threshold=5.0)

        assert snapped is not None
        # Snaps to one of the center's axes (horizontal or vertical alignment)
        assert snapped[0] == 50.0 or snapped[1] == 50.0

    def test_snap_point_to_axes_respects_threshold(self):
        """snap_point_to_axes should not snap if distance > threshold."""
        point = (50.0, 50.0)
        anchors = [(100.0, 100.0)]  # Far away

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is None

    def test_snap_point_to_axes_chooses_closest_snap(self):
        """snap_point_to_axes should choose the closest snap point."""
        point = (51.0, 49.0)
        anchors = [(50.0, 0.0), (0.0, 50.0)]  # Both within threshold

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        # Should snap to closest option (50, 49) - vertical snap from first anchor
        assert snapped == (50.0, 49.0)

    def test_snap_point_to_axes_handles_no_anchors_or_centers(self):
        """snap_point_to_axes should return None if no anchors/centers."""
        point = (50.0, 50.0)

        snapped = snap_point_to_axes(point, anchors=None, centers=None)

        assert snapped is None

    def test_snap_point_to_axes_handles_empty_iterables(self):
        """snap_point_to_axes should return None for empty iterables."""
        point = (50.0, 50.0)

        snapped = snap_point_to_axes(point, anchors=[], centers=[])

        assert snapped is None
