"""Unit tests for GeometryService in utils/geometry_service.py."""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry_service import GeometryService


class TestGeometryServiceExtended:
    """Test GeometryService snapping, clamping, and segment-distance."""

    def test_apply_snapping_empty_polygons_returns_none(self):
        result = GeometryService.apply_snapping(5.0, 5.0, existing_polygons=[])
        assert result is None

    def test_apply_snapping_snaps_to_vertex(self):
        # Point close to (10, 10) vertex
        poly = [[10, 10], [20, 10], [20, 20], [10, 20]]
        result = GeometryService.apply_snapping(10.5, 10.5, [poly], threshold=5.0)
        assert result is not None
        assert result[0] == pytest.approx(10.0, abs=1.0)
        assert result[1] == pytest.approx(10.0, abs=1.0)

    def test_apply_snapping_exclude_polygon_index(self):
        poly1 = [[0, 0], [10, 0], [10, 10], [0, 10]]
        poly2 = [[100, 100], [110, 100], [110, 110], [100, 110]]
        # Without exclusion: snaps to poly1
        result_no_excl = GeometryService.apply_snapping(0.5, 0.5, [poly1, poly2], threshold=10.0)
        # With exclusion of poly1: should not snap to it
        result_excl = GeometryService.apply_snapping(
            0.5, 0.5, [poly1, poly2], threshold=10.0, exclude_polygon_index=0
        )
        assert result_no_excl is not None
        assert result_excl is None or result_excl[0] != pytest.approx(0.0, abs=1.0)

    def test_clamp_point_inside_polygon_returns_same(self):
        poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
        point = (50.0, 50.0)
        result = GeometryService.clamp_point_to_polygon(point, poly)
        assert result == point

    def test_clamp_point_outside_polygon_returns_edge_point(self):
        poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
        point = (150.0, 50.0)  # Outside on the right
        result = GeometryService.clamp_point_to_polygon(point, poly)
        # Should be clamped to x=100 edge
        assert result[0] == pytest.approx(100.0, abs=2.0)

    def test_point_to_segment_distance_on_endpoint(self):
        result = GeometryService._point_to_segment_distance(0.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert result is not None
        assert result["distance"] == pytest.approx(0.0)
        assert result["x"] == pytest.approx(0.0)

    def test_point_to_segment_distance_degenerate_segment(self):
        # p1 == p2
        result = GeometryService._point_to_segment_distance(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
        assert result is not None
        assert result["distance"] == pytest.approx(5.0)  # sqrt(9+16)

    def test_point_to_segment_distance_perpendicular_projection(self):
        # Point at (5, 3), segment from (0,0) to (10,0)
        result = GeometryService._point_to_segment_distance(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        assert result is not None
        assert result["distance"] == pytest.approx(3.0)
        assert result["x"] == pytest.approx(5.0)
        assert result["y"] == pytest.approx(0.0)
