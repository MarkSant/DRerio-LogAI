"""Tests for roi_builder (Phase 5.6c)."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI
from zebtrack.analysis.roi_builder import build_roi_from_polygon, build_rois_from_zone_polygons


# ---------------------------------------------------------------------------
# build_roi_from_polygon
# ---------------------------------------------------------------------------
class TestBuildRoiFromPolygon:
    """Tests for build_roi_from_polygon."""

    def test_valid_triangle(self) -> None:
        """Triangle (3 vertices) produces a valid ROI."""
        roi = build_roi_from_polygon("tri", [(0, 0), (10, 0), (5, 10)])
        assert roi is not None
        assert isinstance(roi, ROI)
        assert roi.name == "tri"
        assert isinstance(roi.geometry, Polygon)
        assert roi.coordinate_space == "px"

    def test_valid_rectangle(self) -> None:
        """Rectangle (4 vertices) produces a valid ROI."""
        roi = build_roi_from_polygon("rect", [(0, 0), (10, 0), (10, 10), (0, 10)])
        assert roi is not None
        assert roi.name == "rect"
        assert roi.geometry.area == pytest.approx(100.0)

    def test_custom_coordinate_space(self) -> None:
        """Custom coordinate_space is preserved."""
        roi = build_roi_from_polygon("r", [(0, 0), (1, 0), (1, 1), (0, 1)], coordinate_space="cm")
        assert roi is not None
        assert roi.coordinate_space == "cm"

    def test_degenerate_polygon_two_points(self) -> None:
        """Polygon with < 3 vertices returns None."""
        assert build_roi_from_polygon("bad", [(0, 0), (1, 1)]) is None

    def test_degenerate_polygon_empty(self) -> None:
        """Empty vertex list returns None."""
        assert build_roi_from_polygon("empty", []) is None


# ---------------------------------------------------------------------------
# build_rois_from_zone_polygons
# ---------------------------------------------------------------------------
class TestBuildRoisFromZonePolygons:
    """Tests for build_rois_from_zone_polygons."""

    def test_multiple_polygons(self) -> None:
        """Builds ROIs from multiple polygons."""
        polys = [
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            [(20, 20), (30, 20), (30, 30), (20, 30)],
        ]
        names = ["Zone A", "Zone B"]
        rois = build_rois_from_zone_polygons(polys, names)
        assert len(rois) == 2
        assert rois[0].name == "Zone A"
        assert rois[1].name == "Zone B"

    def test_with_offset(self) -> None:
        """Offset is subtracted from all vertex coordinates."""
        poly = [[(100, 200), (110, 200), (110, 210), (100, 210)]]
        names = ["Shifted"]
        rois = build_rois_from_zone_polygons(poly, names, offset=(100.0, 200.0))
        assert len(rois) == 1
        # After offset: (0,0), (10,0), (10,10), (0,10)
        assert rois[0].geometry.area == pytest.approx(100.0)

    def test_fallback_names(self) -> None:
        """When names list is shorter, ROI_<i> fallback is used."""
        polys = [
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            [(2, 2), (3, 2), (3, 3), (2, 3)],
        ]
        rois = build_rois_from_zone_polygons(polys, names=["First"])
        assert len(rois) == 2
        assert rois[0].name == "First"
        assert rois[1].name == "ROI_1"

    def test_skips_degenerate(self) -> None:
        """Degenerate polygons (< 3 vertices) are silently skipped."""
        polys = [
            [(0, 0), (10, 0), (10, 10)],
            [(5, 5)],  # degenerate
        ]
        rois = build_rois_from_zone_polygons(polys, names=["Good", "Bad"])
        assert len(rois) == 1
        assert rois[0].name == "Good"
