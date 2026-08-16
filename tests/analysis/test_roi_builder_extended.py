"""
Extended unit tests for roi_builder in analysis/roi_builder.py.
"""

from __future__ import annotations

from zebtrack.analysis.roi import ROI
from zebtrack.analysis.roi_builder import (
    build_roi_from_polygon,
    build_rois_from_zone_polygons,
)


class TestRoiBuilderExtended:
    """Test ROI builder helpers for polygon validation, coordinate spaces, and zone translation."""

    def test_build_roi_from_polygon_degenerate_cases(self):
        assert build_roi_from_polygon("None_0", []) is None
        assert build_roi_from_polygon("None_1", [(1.0, 1.0)]) is None
        assert build_roi_from_polygon("None_2", [(1.0, 1.0), (2.0, 2.0)]) is None

    def test_build_roi_from_polygon_valid_triangle_and_spaces(self):
        triangle_px = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
        roi_px = build_roi_from_polygon("Triangle_PX", triangle_px, coordinate_space="px")
        assert roi_px is not None
        assert isinstance(roi_px, ROI)
        assert roi_px.name == "Triangle_PX"
        assert roi_px.coordinate_space == "px"
        assert roi_px.geometry.area == 50.0

        roi_cm = build_roi_from_polygon("Triangle_CM", triangle_px, coordinate_space="cm")
        assert roi_cm is not None
        assert roi_cm.coordinate_space == "cm"

    def test_build_rois_from_zone_polygons_translation_and_fallbacks(self):
        # 3 polygons: 2 valid rectangles, 1 invalid line
        poly1 = [(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)]
        poly2 = [(300.0, 300.0), (400.0, 300.0), (400.0, 400.0), (300.0, 400.0)]
        poly_invalid = [(500.0, 500.0), (600.0, 600.0)]

        # Provide only 1 name, second should fallback to ROI_1
        names = ["Zone_First"]
        offset = (50.0, 50.0)

        rois = build_rois_from_zone_polygons([poly1, poly2, poly_invalid], names, offset=offset)

        assert len(rois) == 2
        assert rois[0].name == "Zone_First"
        # Translated by -50: (50, 50) to (150, 150)
        assert rois[0].geometry.bounds == (50.0, 50.0, 150.0, 150.0)

        assert rois[1].name == "ROI_1"
        # Translated by -50: (250, 250) to (350, 350)
        assert rois[1].geometry.bounds == (250.0, 250.0, 350.0, 350.0)

    def test_build_rois_from_zone_polygons_negative_offset(self):
        poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        rois = build_rois_from_zone_polygons([poly], ["Origin"], offset=(-10.0, -20.0))
        assert len(rois) == 1
        # Translated by -(-10, -20) -> +(10, 20) -> bounds (10, 20, 20, 30)
        assert rois[0].geometry.bounds == (10.0, 20.0, 20.0, 30.0)
