"""
Unit tests for zebtrack.analysis.roi_builder.
"""

from __future__ import annotations

from zebtrack.analysis.roi import ROI
from zebtrack.analysis.roi_builder import build_roi_from_polygon, build_rois_from_zone_polygons


def test_build_roi_from_polygon_invalid_coordinates():
    # Empty
    assert build_roi_from_polygon("ROI_1", []) is None
    # Less than 3 vertices
    assert build_roi_from_polygon("ROI_1", [(0.0, 0.0), (10.0, 10.0)]) is None


def test_build_roi_from_polygon_valid():
    coords = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    roi = build_roi_from_polygon("Zone_A", coords, coordinate_space="cm")
    assert roi is not None
    assert isinstance(roi, ROI)
    assert roi.name == "Zone_A"
    assert roi.coordinate_space == "cm"
    assert roi.geometry.area == 100.0


def test_build_rois_from_zone_polygons_empty():
    assert build_rois_from_zone_polygons([], []) == []


def test_build_rois_from_zone_polygons_with_offset_and_fallback_names():
    poly1 = [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)]
    poly2 = [(30.0, 30.0), (40.0, 30.0), (40.0, 40.0), (30.0, 40.0)]
    poly_degenerate = [(50.0, 50.0), (51.0, 51.0)]

    polygons = [poly1, poly2, poly_degenerate]
    names = ["Custom_1"]  # Only 1 name provided; second should fallback to ROI_1

    offset = (10.0, 10.0)
    rois = build_rois_from_zone_polygons(polygons, names, offset=offset)

    assert len(rois) == 2
    assert rois[0].name == "Custom_1"
    # Translated by (-10, -10): vertices become (0,0), (10,0), (10,10), (0,10)
    bounds = rois[0].geometry.bounds
    assert bounds == (0.0, 0.0, 10.0, 10.0)

    assert rois[1].name == "ROI_1"
    bounds2 = rois[1].geometry.bounds
    assert bounds2 == (20.0, 20.0, 30.0, 30.0)
