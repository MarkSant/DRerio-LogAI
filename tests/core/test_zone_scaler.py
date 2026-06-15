"""Unit tests for the geometry helpers of ``zebtrack.core.detection.ZoneScaler``.

``test_property_zone_scaler.py`` already exercises polygon scaling, mask building
and ``point_in_polygon``. This file covers the remaining gaps with concrete
boundary cases: the uncached ``cv2.pointPolygonTest`` fallback in
``is_inside_polygon`` / ``bbox_hits_roi_polygon``, the ``_check_mask`` fast path,
crop helpers, and the per-aquarium getters in their empty default state.

``cv2`` is real, deterministic pure compute — never mocked.
"""

import numpy as np
import pytest

from zebtrack.core.detection.zone_scaler import ZoneScaler


@pytest.fixture
def scaler():
    return ZoneScaler(base_width=1280, base_height=720)


def _square(x1, y1, x2, y2):
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.int32)


class TestIsInsidePolygon:
    def test_bbox_fully_inside(self, scaler):
        poly = _square(0, 0, 100, 100)
        assert scaler.is_inside_polygon(10, 10, 20, 20, poly) is True

    def test_bbox_fully_outside(self, scaler):
        poly = _square(0, 0, 100, 100)
        assert scaler.is_inside_polygon(200, 200, 210, 210, poly) is False

    def test_corner_on_boundary_is_inside(self, scaler):
        # cv2.pointPolygonTest returns 0 on the edge, and the code accepts >= 0,
        # so a bbox whose corner sits exactly on a polygon vertex counts as inside.
        # (Contrast: shapely's strict ``contains`` in analysis/roi.py excludes it.)
        poly = _square(0, 0, 100, 100)
        assert scaler.is_inside_polygon(100, 100, 110, 110, poly) is True

    def test_empty_polygon_returns_false(self, scaler):
        assert scaler.is_inside_polygon(10, 10, 20, 20, np.array([])) is False

    def test_center_inside_corners_outside(self, scaler):
        # bbox larger than the polygon: corners outside but center inside → True.
        poly = _square(40, 40, 60, 60)
        assert scaler.is_inside_polygon(0, 0, 100, 100, poly) is True


class TestBboxHitsRoiPolygon:
    def test_hit_and_miss(self, scaler):
        poly = _square(0, 0, 100, 100)
        assert scaler.bbox_hits_roi_polygon(10, 10, 20, 20, poly) is True
        assert scaler.bbox_hits_roi_polygon(500, 500, 510, 510, poly) is False

    def test_empty_polygon_returns_false(self, scaler):
        assert scaler.bbox_hits_roi_polygon(10, 10, 20, 20, np.array([])) is False


class TestCheckMask:
    def test_any_point_inside(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[0:50, 0:50] = 255
        # Top-left corner falls in the filled region.
        assert ZoneScaler._check_mask(mask, 10, 10, 20, 20) is True

    def test_no_point_inside(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        assert ZoneScaler._check_mask(mask, 10, 10, 20, 20) is False


class TestGetCropInfo:
    def test_empty_polygon_returns_full_frame(self, scaler):
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        cropped, dx, dy = scaler.get_crop_info(frame, np.array([]))
        assert cropped is frame and dx == 0 and dy == 0

    def test_valid_crop_returns_offsets(self, scaler):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        cropped, dx, dy = scaler.get_crop_info(frame, _square(10, 10, 40, 40))
        assert (dx, dy) == (10, 10)
        # cv2.boundingRect is inclusive of both vertices → 31x31 region.
        assert cropped.shape[:2] == (31, 31)

    def test_degenerate_crop_returns_none(self, scaler):
        # Polygon entirely to the right of a small frame → empty intersection → None.
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        assert scaler.get_crop_info(frame, _square(100, 100, 110, 110)) is None


class TestCropAquariumRegion:
    def test_unknown_aquarium_returns_full_frame(self, scaler):
        frame = np.zeros((80, 120, 3), dtype=np.uint8)
        cropped, offsets = scaler.crop_aquarium_region(frame, aquarium_id=99)
        assert cropped is frame
        assert offsets == (0, 0, 120, 80)


class TestAquariumGetters:
    def test_polygon_getter_defaults_to_none(self, scaler):
        assert scaler.get_aquarium_polygon(0) is None

    def test_roi_getter_defaults_to_empty_list(self, scaler):
        assert scaler.get_aquarium_roi_polygons(0) == []

    def test_clear_cache_is_safe(self, scaler):
        scaler.clear_cache()  # must not raise on an empty scaler
        assert scaler.get_aquarium_polygon(0) is None


class TestPointInPolygon:
    def test_inside_and_outside(self):
        poly = _square(0, 0, 100, 100)
        assert ZoneScaler.point_in_polygon((50, 50), poly) is True
        assert ZoneScaler.point_in_polygon((150, 150), poly) is False
