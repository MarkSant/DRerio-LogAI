"""Tests for zebtrack.utils.geometry module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.utils.geometry import (
    DEFAULT_POLYGON_EPSILON_FACTOR,
    polygon_centroid,
    resolve_polygon_epsilon_factor,
    simplify_polygon,
    snap_point_to_axes,
)


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


class TestGeometryExtended:
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


class TestGeometryExtended2:
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


# ---------------------------------------------------------------------------
# simplify_polygon / resolve_polygon_epsilon_factor
# ---------------------------------------------------------------------------


def _dense_rectangle(width: int = 100, height: int = 60, step: int = 10) -> list[list[float]]:
    """A rectangle outline with a vertex every ``step`` px, as a mask contour has."""
    top = [[float(x), 0.0] for x in range(0, width, step)]
    right = [[float(width), float(y)] for y in range(0, height, step)]
    bottom = [[float(x), float(height)] for x in range(width, 0, -step)]
    left = [[0.0, float(y)] for y in range(height, 0, -step)]
    return top + right + bottom + left


class TestSimplifyPolygon:
    def test_a_dense_outline_collapses_to_its_corners(self):
        raw = _dense_rectangle()
        assert len(raw) == 32

        simplified = simplify_polygon(raw, epsilon_factor=0.01)

        assert sorted(simplified) == [[0, 0], [0, 60], [100, 0], [100, 60]]

    @pytest.mark.parametrize("epsilon_factor", [0.0, -0.5])
    def test_a_non_positive_factor_returns_the_raw_outline_as_integers(self, epsilon_factor):
        raw = [[0.9, 0.2], [10.7, 0.0], [10.0, 9.99]]
        assert simplify_polygon(raw, epsilon_factor=epsilon_factor) == [[0, 0], [10, 0], [10, 9]]

    def test_epsilon_never_drops_below_one_pixel(self):
        # 0.0001 of a 400 px perimeter is 0.04 px, which would keep the 0.6 px
        # bump on the top edge. The 1 px floor removes it.
        raw = [[0.0, 0.0], [50.0, 0.6], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        simplified = simplify_polygon(raw, epsilon_factor=0.0001)
        assert sorted(simplified) == [[0, 0], [0, 100], [100, 0], [100, 100]]

    def test_a_degenerate_outline_with_no_perimeter_is_returned_as_is(self):
        raw = [[5.0, 5.0], [5.0, 5.0], [5.0, 5.0]]
        assert simplify_polygon(raw, epsilon_factor=0.02) == [[5, 5], [5, 5], [5, 5]]

    def test_an_approximation_below_a_triangle_keeps_the_raw_outline(self):
        # A sliver: any useful epsilon reduces it to a segment, which is no arena.
        raw = [[0.0, 0.0], [100.0, 0.4], [200.0, 0.0], [100.0, -0.4]]
        assert simplify_polygon(raw, epsilon_factor=0.05) == [[0, 0], [100, 0], [200, 0], [100, 0]]

    def test_a_cv2_failure_keeps_the_raw_outline(self, monkeypatch):
        import cv2

        def _boom(*args, **kwargs):
            raise cv2.error("arcLength failed")

        monkeypatch.setattr(cv2, "arcLength", _boom)
        raw = _dense_rectangle()
        assert simplify_polygon(raw, epsilon_factor=0.01) == [[int(x), int(y)] for x, y in raw]

    def test_the_default_factor_is_used_when_none_is_given(self):
        assert DEFAULT_POLYGON_EPSILON_FACTOR > 0
        assert simplify_polygon(_dense_rectangle()) == simplify_polygon(
            _dense_rectangle(), epsilon_factor=DEFAULT_POLYGON_EPSILON_FACTOR
        )


class TestResolvePolygonEpsilonFactor:
    def test_the_configured_value_is_read_as_a_float(self):
        settings_obj = SimpleNamespace(yolo_model=SimpleNamespace(aquarium_polygon_epsilon="0.035"))
        assert resolve_polygon_epsilon_factor(settings_obj) == 0.035

    @pytest.mark.parametrize(
        "settings_obj",
        [None, SimpleNamespace(), SimpleNamespace(yolo_model=SimpleNamespace())],
    )
    def test_stripped_settings_fall_back_to_the_default(self, settings_obj):
        assert resolve_polygon_epsilon_factor(settings_obj) == DEFAULT_POLYGON_EPSILON_FACTOR

    def test_an_unparseable_value_falls_back_to_the_default(self):
        settings_obj = SimpleNamespace(yolo_model=SimpleNamespace(aquarium_polygon_epsilon="wide"))
        assert resolve_polygon_epsilon_factor(settings_obj) == DEFAULT_POLYGON_EPSILON_FACTOR
