"""Tests for zebtrack.utils.geometry module."""

from __future__ import annotations

import itertools
import math
from types import SimpleNamespace

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from zebtrack.utils.geometry import (
    DEFAULT_POLYGON_EPSILON_FACTOR,
    Point,
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


# ---------------------------------------------------------------------------
# Property-based invariants (hypothesis)
# ---------------------------------------------------------------------------

#: The same examples on every machine: a CI failure must be one a developer can
#: reproduce, never a draw nobody saw locally.
_PROPERTY = settings(max_examples=120, database=None, derandomize=True, deadline=None)

_COORD = st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)


@st.composite
def _convex_polygons(draw: st.DrawFn) -> list[Point]:
    """Vertices on an ellipse, taken in angle order: always a convex polygon."""
    cx = draw(_COORD)
    cy = draw(_COORD)
    rx = draw(st.floats(min_value=1.0, max_value=1e3))
    ry = draw(st.floats(min_value=1.0, max_value=1e3))
    degrees = draw(st.lists(st.integers(0, 359), min_size=3, max_size=24, unique=True))
    return [
        (cx + rx * math.cos(math.radians(d)), cy + ry * math.sin(math.radians(d)))
        for d in sorted(degrees)
    ]


def _fan_centroid(polygon: list[Point]) -> Point:
    """Independent oracle: area-weighted mean of the fan triangles' vertex means."""
    ax, ay = polygon[0]
    weights, xs, ys = [], [], []
    for (bx, by), (cx, cy) in itertools.pairwise(polygon[1:]):
        ux, uy, vx, vy = bx - ax, by - ay, cx - ax, cy - ay
        weight = ux * vy - vx * uy
        weights.append(weight)
        xs.append(weight * (ux + vx) / 3.0)
        ys.append(weight * (uy + vy) / 3.0)
    total = math.fsum(weights)
    return ax + math.fsum(xs) / total, ay + math.fsum(ys) / total


def _scale(polygon: list[Point]) -> float:
    """Largest coordinate magnitude plus the polygon's extent: the error yardstick."""
    xs = [x for x, _ in polygon]
    ys = [y for _, y in polygon]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return span + max(abs(v) for v in xs + ys)


def _assert_same_point(got: Point | None, expected: Point, scale: float) -> None:
    assert got is not None
    tolerance = 1e-9 * scale + 1e-9
    assert abs(got[0] - expected[0]) <= tolerance
    assert abs(got[1] - expected[1]) <= tolerance


class TestPolygonCentroidProperties:
    @_PROPERTY
    @given(_convex_polygons())
    def test_it_is_the_area_weighted_mean_of_any_triangulation(self, polygon):
        _assert_same_point(polygon_centroid(polygon), _fan_centroid(polygon), _scale(polygon))

    @_PROPERTY
    @given(_convex_polygons())
    def test_a_convex_polygon_holds_its_centroid_inside_its_bounding_box(self, polygon):
        centroid = polygon_centroid(polygon)
        assert centroid is not None
        slack = 1e-9 * _scale(polygon)
        xs = [x for x, _ in polygon]
        ys = [y for _, y in polygon]
        assert min(xs) - slack <= centroid[0] <= max(xs) + slack
        assert min(ys) - slack <= centroid[1] <= max(ys) + slack

    @_PROPERTY
    @given(_convex_polygons(), st.integers(min_value=0, max_value=23), st.booleans())
    def test_neither_the_first_vertex_nor_the_orientation_matters(self, polygon, start, reverse):
        start %= len(polygon)
        relabelled = polygon[start:] + polygon[:start]
        if reverse:
            relabelled.reverse()
        expected = polygon_centroid(polygon)
        assert expected is not None
        _assert_same_point(polygon_centroid(relabelled), expected, _scale(polygon))

    @_PROPERTY
    @given(_convex_polygons(), _COORD, _COORD)
    def test_it_moves_with_a_translation(self, polygon, tx, ty):
        moved = [(x + tx, y + ty) for x, y in polygon]
        original = polygon_centroid(polygon)
        assert original is not None
        expected = (original[0] + tx, original[1] + ty)
        _assert_same_point(polygon_centroid(moved), expected, _scale(moved) + _scale(polygon))

    @_PROPERTY
    @given(
        _convex_polygons(),
        st.floats(min_value=0.01, max_value=100.0),
        st.booleans(),
    )
    def test_it_scales_with_the_polygon_including_a_point_reflection(
        self, polygon, factor, reflect
    ):
        k = -factor if reflect else factor
        scaled = [(k * x, k * y) for x, y in polygon]
        original = polygon_centroid(polygon)
        assert original is not None
        expected = (k * original[0], k * original[1])
        _assert_same_point(polygon_centroid(scaled), expected, _scale(scaled))

    @_PROPERTY
    @given(st.lists(st.tuples(_COORD, _COORD), max_size=2))
    def test_fewer_than_three_vertices_have_no_centroid(self, points):
        assert polygon_centroid(points) is None

    @_PROPERTY
    @given(
        st.tuples(_COORD, _COORD),
        st.tuples(
            st.floats(min_value=-1e3, max_value=1e3),
            st.floats(min_value=-1e3, max_value=1e3),
        ),
        st.lists(st.floats(min_value=-1.0, max_value=1.0), min_size=3, max_size=8),
    )
    def test_collinear_vertices_have_no_centroid(self, base, direction, offsets):
        # A polygon folded onto one line has no area, so it has no centroid —
        # even when float rounding leaves its signed area a hair off zero.
        (bx, by), (dx, dy) = base, direction
        points = [(bx + t * dx, by + t * dy) for t in offsets]
        assert polygon_centroid(points) is None

    def test_collinear_float_vertices_do_not_produce_a_centroid_off_the_line(self):
        # 0.3/0.4/1.1 on y = 3x: rounding leaves a signed area of ~1e-16, and
        # the shoelace then divided by it, placing the "centroid" at x = 0.233,
        # outside the segment it was computed from.
        points = [(0.3, 0.8999999999999999), (0.4, 1.2000000000000002), (1.1, 3.3000000000000003)]
        assert polygon_centroid(points) is None


_GRID = st.integers(min_value=-20, max_value=20).map(float)
_GRID_POINT = st.tuples(_GRID, _GRID)


def _snap_candidates(point: Point, anchors: list[Point], centers: list[Point]) -> list[Point]:
    """The candidates ``snap_point_to_axes`` documents, in its documented order."""
    px, py = point
    candidates: list[Point] = []
    for ax, ay in anchors:
        candidates += [(ax, py), (px, ay)]
    for cx, cy in centers:
        candidates += [(cx, cy), (cx, py), (px, cy)]
    return candidates


class TestSnapPointToAxesProperties:
    @_PROPERTY
    @given(
        _GRID_POINT,
        st.lists(_GRID_POINT, max_size=5),
        st.lists(_GRID_POINT, max_size=3),
        st.integers(min_value=0, max_value=30).map(float),
    )
    def test_the_snap_is_the_first_nearest_candidate_within_the_threshold(
        self, point, anchors, centers, threshold
    ):
        snapped = snap_point_to_axes(point, anchors=anchors, centers=centers, threshold=threshold)

        distances = [(math.dist(point, c), c) for c in _snap_candidates(point, anchors, centers)]
        within = [(d, c) for d, c in distances if d < threshold]
        if not within:
            assert snapped is None
            return
        assert snapped is not None
        nearest = min(d for d, _ in within)
        # Strictly within the threshold, never beaten by another candidate, and
        # on a tie the candidate the documented order reaches first.
        assert math.dist(point, snapped) == nearest < threshold
        assert snapped == next(c for d, c in within if d == nearest)

    @_PROPERTY
    @given(
        _GRID_POINT,
        st.lists(_GRID_POINT, max_size=5),
        st.lists(_GRID_POINT, max_size=3),
        st.integers(min_value=0, max_value=30).map(float),
    )
    def test_a_snap_keeps_one_coordinate_or_lands_on_a_center(
        self, point, anchors, centers, threshold
    ):
        snapped = snap_point_to_axes(point, anchors=anchors, centers=centers, threshold=threshold)
        assume(snapped is not None)
        assert snapped is not None
        assert snapped[0] == point[0] or snapped[1] == point[1] or snapped in centers

    @_PROPERTY
    @given(
        _GRID_POINT,
        st.lists(_GRID_POINT, max_size=5),
        st.lists(_GRID_POINT, max_size=3),
        st.integers(min_value=0, max_value=30).map(float),
    )
    def test_one_shot_iterators_snap_like_lists(self, point, anchors, centers, threshold):
        from_lists = snap_point_to_axes(
            point, anchors=anchors, centers=centers, threshold=threshold
        )
        from_iterators = snap_point_to_axes(
            point, anchors=iter(anchors), centers=iter(centers), threshold=threshold
        )
        assert from_iterators == from_lists

    @_PROPERTY
    @given(
        _GRID_POINT,
        st.lists(_GRID_POINT, max_size=5),
        st.lists(_GRID_POINT, max_size=3),
        st.integers(min_value=-30, max_value=0).map(float),
    )
    def test_a_non_positive_threshold_never_snaps(self, point, anchors, centers, threshold):
        assert (
            snap_point_to_axes(point, anchors=anchors, centers=centers, threshold=threshold) is None
        )


@st.composite
def _mask_outlines(draw: st.DrawFn) -> list[list[int]]:
    """A star-shaped outline in integer pixels with distinct vertices."""
    count = draw(st.integers(min_value=3, max_value=40))
    cx = draw(st.integers(min_value=200, max_value=800))
    cy = draw(st.integers(min_value=200, max_value=800))
    radii = draw(st.lists(st.integers(5, 200), min_size=count, max_size=count))
    outline: list[list[int]] = []
    for k, radius in enumerate(radii):
        angle = 2.0 * math.pi * k / count
        vertex = [round(cx + radius * math.cos(angle)), round(cy + radius * math.sin(angle))]
        if vertex not in outline:
            outline.append(vertex)
    assume(len(outline) >= 3)
    return outline


_EPSILON_FACTOR = st.floats(min_value=0.0005, max_value=0.3)

#: Douglas-Peucker keeps every dropped vertex within epsilon of its replacing
#: edge; cv2's closed variant then drops isolated vertices within epsilon/sqrt(2)
#: of the next chord, so a vertex can end up 1 + 1/sqrt(2) epsilon away.
_CV2_CLOSED_DP_BOUND = 1.0 + 1.0 / math.sqrt(2.0)


def _distance_to_segment(p: list[int], a: list[int], b: list[int]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


class TestSimplifyPolygonProperties:
    @_PROPERTY
    @given(_mask_outlines(), _EPSILON_FACTOR)
    def test_the_result_is_the_input_with_vertices_removed_in_order(self, outline, factor):
        simplified = simplify_polygon(outline, epsilon_factor=factor)

        indices = [outline.index(vertex) for vertex in simplified]  # raises if not a vertex
        assert len(set(indices)) == len(indices) <= len(outline)
        start = indices.index(min(indices))
        rotated = indices[start:] + indices[:start]
        assert rotated == sorted(rotated)

    @_PROPERTY
    @given(_mask_outlines(), _EPSILON_FACTOR)
    def test_a_polygon_never_collapses_below_a_triangle(self, outline, factor):
        assert len(simplify_polygon(outline, epsilon_factor=factor)) >= 3

    @_PROPERTY
    @given(_mask_outlines(), _EPSILON_FACTOR)
    def test_every_input_vertex_stays_near_the_simplified_outline(self, outline, factor):
        simplified = simplify_polygon(outline, epsilon_factor=factor)

        perimeter = sum(
            math.dist(outline[i], outline[(i + 1) % len(outline)]) for i in range(len(outline))
        )
        epsilon = max(1.0, factor * perimeter)
        edges = list(zip(simplified, simplified[1:] + simplified[:1], strict=True))
        for vertex in outline:
            gap = min(_distance_to_segment(vertex, a, b) for a, b in edges)
            assert gap <= _CV2_CLOSED_DP_BOUND * epsilon + 1e-3

    @_PROPERTY
    @given(_mask_outlines(), st.floats(min_value=-1.0, max_value=0.0))
    def test_a_non_positive_factor_returns_the_outline_untouched(self, outline, factor):
        assert simplify_polygon(outline, epsilon_factor=factor) == outline


class TestResolvePolygonEpsilonFactorProperties:
    @_PROPERTY
    @given(st.floats(allow_nan=False, allow_infinity=False), st.booleans())
    def test_any_configured_number_is_read_back_unchanged(self, value, as_text):
        configured = repr(value) if as_text else value
        settings_obj = SimpleNamespace(
            yolo_model=SimpleNamespace(aquarium_polygon_epsilon=configured)
        )
        assert resolve_polygon_epsilon_factor(settings_obj) == value
