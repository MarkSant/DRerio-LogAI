"""
Extended unit tests for GeometryService.
"""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry_service import GeometryService


class TestGeometryServiceExtended:
    def test_apply_snapping_axis_alignment(self):
        # Square: (0,0), (100,0), (100,100), (0,100)
        polygons = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]
        # Point near (100, 0) snaps to horizontal axis y=0
        snapped = GeometryService.apply_snapping(98.0, 2.0, polygons, threshold=5.0)
        assert snapped == (98.0, 0.0)

    def test_apply_snapping_exclude_index(self):
        poly0 = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        poly1 = [(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)]

        # Near poly0, but exclude_polygon_index=0
        snapped = GeometryService.apply_snapping(
            1.0, 1.0, [poly0, poly1], threshold=5.0, exclude_polygon_index=0
        )
        assert snapped is None

    def test_clamp_point_to_polygon_inside(self):
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        point = (50.0, 50.0)
        # Inside -> point returned unchanged
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped == (50.0, 50.0)

    def test_clamp_point_to_polygon_outside(self):
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        point = (120.0, 50.0)  # Outside on right
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped[0] == pytest.approx(100.0)
        assert clamped[1] == pytest.approx(50.0)

    def test_apply_snapping_vertex_and_edge(self):
        poly = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]

        # Near vertex (0, 0) - axis snap to horizontal axis through anchor
        snapped_vertex = GeometryService.apply_snapping(1.0, 1.0, poly, threshold=3.0)
        assert snapped_vertex == (1.0, 0.0)

        # Near edge y=0 between x=20 and x=80 (away from center x=50)
        snapped_edge = GeometryService.apply_snapping(60.0, 2.0, poly, threshold=3.0)
        assert snapped_edge is not None
        assert snapped_edge[0] == pytest.approx(60.0)
        assert snapped_edge[1] == pytest.approx(0.0)

    def test_point_to_segment_distance_degenerate_segment(self):
        res = GeometryService._point_to_segment_distance(10.0, 10.0, 0.0, 0.0, 0.0, 0.0)
        assert res is not None
        assert res["x"] == 0.0
        assert res["y"] == 0.0
        assert res["distance"] == pytest.approx(14.142, 0.01)


class TestGeometryServiceExtended2:
    def test_apply_snapping_empty_polygons(self):
        res = GeometryService.apply_snapping(10.0, 20.0, existing_polygons=[])
        assert res is None

    def test_apply_snapping_to_edge(self):
        poly = [[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]]
        # Point near edge x=100 (99.0, 40.0) -> projects to edge (100.0, 40.0)
        snapped = GeometryService.apply_snapping(99.0, 40.0, poly, threshold=5.0)
        assert snapped is not None
        assert snapped[0] == pytest.approx(100.0)
        assert snapped[1] == pytest.approx(40.0)

    def test_apply_snapping_with_exclusion(self):
        poly1 = [[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]]
        poly2 = [[[200.0, 200.0], [300.0, 200.0], [300.0, 300.0], [200.0, 300.0]]]
        # Exclude poly1 (index 0), should not snap to (100, 40)
        snapped = GeometryService.apply_snapping(
            99.0, 40.0, [poly1[0], poly2[0]], threshold=5.0, exclude_polygon_index=0
        )
        assert snapped is None

    def test_clamp_point_inside_polygon(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        point = (50.0, 50.0)
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped == point

    def test_clamp_point_outside_polygon(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        point = (150.0, 50.0)
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped[0] == pytest.approx(100.0)
        assert clamped[1] == pytest.approx(50.0)
