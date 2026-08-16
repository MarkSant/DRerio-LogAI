"""
Extended unit tests for Calibration perspective transformation.
"""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.detection.calibration import Calibration


class TestCalibrationExtended:
    """Test Calibration homography calculation, point warping, and bboxes."""

    def test_calibration_without_polygon(self):
        calib = Calibration(polygon=None, real_width_cm=30.0, real_height_cm=20.0)
        assert calib.homography_matrix is None
        assert calib.pixel_per_cm_ratio == (0.0, 0.0)

        # Fallbacks when matrix is None
        dummy_frame = np.zeros((50, 50, 3), dtype=np.uint8)
        assert calib.warp_frame(dummy_frame) is dummy_frame
        assert calib.transform_points([[10, 10]]) == [[10, 10]]
        assert calib.transform_bbox(10, 10, 20, 20) == (10, 10, 20, 20)

    def test_calibration_with_degenerate_polygon(self):
        # < 3 points
        poly = np.array([[0, 0], [10, 10]])
        calib = Calibration(
            polygon=poly,
            real_width_cm=30.0,
            real_height_cm=20.0,
        )
        assert calib.homography_matrix is None

    def test_calibration_with_valid_rectangle(self):
        # 100x100 square in pixels, 20x20 cm in real world
        poly = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float32)
        calib = Calibration(
            polygon=poly,
            real_width_cm=20.0,
            real_height_cm=20.0,
        )

        assert calib.homography_matrix is not None
        assert calib.target_dims_px == (600, 600)
        assert calib.pixel_per_cm_ratio == (30.0, 30.0)

        # Warp frame
        frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
        warped = calib.warp_frame(frame)
        assert warped.shape == (600, 600, 3)

        # Transform points: center (50, 50) -> should be close to center (300, 300)
        pts_transformed = calib.transform_points([[50.0, 50.0]])
        assert len(pts_transformed) == 1
        assert pts_transformed[0][0] == pytest.approx(300.0, abs=5.0)
        assert pts_transformed[0][1] == pytest.approx(300.0, abs=5.0)

        # Transform bbox: (25, 25, 75, 75)
        bbox_warped = calib.transform_bbox(25.0, 25.0, 75.0, 75.0)
        assert len(bbox_warped) == 4
        assert bbox_warped[0] == pytest.approx(150.0, abs=5.0)
        assert bbox_warped[2] == pytest.approx(450.0, abs=5.0)
