"""
Extended unit tests for GeometryService.
"""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry_service import GeometryService


class TestGeometryServiceExtended:
    """Test GeometryService snapping and clamping routines."""

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
