"""
Extended unit tests for ZoneScaler.
"""

from __future__ import annotations

import numpy as np

from zebtrack.core.detection.detection_types import (
    AquariumData,
    ZoneData,
)
from zebtrack.core.detection.zone_scaler import ZoneScaler


class TestZoneScalerExtended:
    """Test ZoneScaler coordinate scaling and geometry operations."""

    def test_single_zone_scaling_and_cache(self):
        scaler = ZoneScaler(base_width=100, base_height=100)
        zones = ZoneData(
            polygon=[[10, 10], [50, 10], [50, 50], [10, 50]],
            roi_polygons=[[[20, 20], [30, 20], [30, 30], [20, 30]]],
        )

        # Scale to 200x200 (scale factor 2x)
        scaler.update_scaling(zones, actual_width=200, actual_height=200)

        expected_poly = [[20, 20], [100, 20], [100, 100], [20, 100]]
        assert np.array_equal(scaler.scaled_polygon, expected_poly)
        assert len(scaler.scaled_roi_polygons) == 1
        expected_roi = [[40, 40], [60, 40], [60, 60], [40, 60]]
        assert np.array_equal(scaler.scaled_roi_polygons[0], expected_roi)

        # Cache hit
        scaler.update_scaling(zones, actual_width=200, actual_height=200)
        assert np.array_equal(scaler.scaled_polygon, expected_poly)

        # Clear cache
        scaler.clear_cache()
        assert len(scaler._scaling_cache) == 0

    def test_empty_polygon_scaling(self):
        scaler = ZoneScaler(base_width=100, base_height=100)
        zones = ZoneData(polygon=[], roi_polygons=[])

        scaler.update_scaling(zones, actual_width=200, actual_height=200)
        assert scaler.scaled_polygon.size == 0
        assert len(scaler.scaled_roi_polygons) == 0

    def test_multi_aquarium_scaling(self):
        scaler = ZoneScaler(base_width=100, base_height=100)
        aq0 = AquariumData(
            id=0,
            polygon=[[0, 0], [40, 0], [40, 40], [0, 40]],
            roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
        )
        aq1 = AquariumData(
            id=1,
            polygon=[[50, 50], [90, 50], [90, 90], [50, 90]],
            roi_polygons=[],
        )

        scaler.scale_multi_aquarium_zones([aq0, aq1], actual_width=200, actual_height=200)

        poly0 = scaler.get_aquarium_polygon(0)
        assert poly0 is not None
        assert np.array_equal(poly0, [[0, 0], [80, 0], [80, 80], [0, 80]])

        rois0 = scaler.get_aquarium_roi_polygons(0)
        assert len(rois0) == 1
        assert np.array_equal(rois0[0], [[20, 20], [40, 20], [40, 40], [20, 40]])

        poly1 = scaler.get_aquarium_polygon(1)
        assert poly1 is not None
        assert np.array_equal(poly1, [[100, 100], [180, 100], [180, 180], [100, 180]])

        assert scaler.get_aquarium_polygon(99) is None

    def test_point_and_bbox_in_polygon(self):
        scaler = ZoneScaler(base_width=100, base_height=100)
        zones = ZoneData(
            polygon=[[10, 10], [50, 10], [50, 50], [10, 50]],
            roi_polygons=[[[20, 20], [30, 20], [30, 30], [20, 30]]],
        )
        scaler.update_scaling(zones, actual_width=100, actual_height=100)

        # Point inside / outside
        assert scaler.point_in_polygon((30, 30), scaler.scaled_polygon) is True
        assert scaler.point_in_polygon((5, 5), scaler.scaled_polygon) is False

        # is_inside_polygon bbox
        assert scaler.is_inside_polygon(20, 20, 40, 40, scaler.scaled_polygon) is True
        assert scaler.is_inside_polygon(80, 80, 90, 90, scaler.scaled_polygon) is False

        # bbox_hits_roi_polygon
        assert scaler.bbox_hits_roi_polygon(22, 22, 28, 28, scaler.scaled_roi_polygons[0]) is True
        assert scaler.bbox_hits_roi_polygon(80, 80, 90, 90, scaler.scaled_roi_polygons[0]) is False

    def test_get_crop_info_and_crop_aquarium(self):
        scaler = ZoneScaler(base_width=100, base_height=100)
        frame = np.ones((100, 100, 3), dtype=np.uint8) * 50

        # get_crop_info with empty polygon
        empty_res = scaler.get_crop_info(frame, np.array([]))
        assert empty_res is not None
        assert empty_res[0].shape == (100, 100, 3)

        # get_crop_info with valid polygon
        poly = np.array([[10, 10], [40, 10], [40, 40], [10, 40]], dtype=np.int32)
        crop_res = scaler.get_crop_info(frame, poly)
        assert crop_res is not None
        cropped_f, x_off, y_off = crop_res
        assert cropped_f.shape == (31, 31, 3)
        assert (x_off, y_off) == (10, 10)

        # crop_aquarium_region
        aq0 = AquariumData(id=0, polygon=[[10, 10], [40, 10], [40, 40], [10, 40]])
        scaler.scale_multi_aquarium_zones([aq0], actual_width=100, actual_height=100)
        aq_crop, box = scaler.crop_aquarium_region(frame, aquarium_id=0, padding=5)
        assert aq_crop.shape == (41, 41, 3)
        assert box == (5, 5, 41, 41)
