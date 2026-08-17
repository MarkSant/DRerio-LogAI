"""Extended unit tests for utils/geometry_service.py."""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry_service import GeometryService


class TestGeometryServiceExtended2:
    """Test GeometryService polygon snapping and clamping operations."""

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
