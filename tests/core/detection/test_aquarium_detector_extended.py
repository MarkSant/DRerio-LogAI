"""
Extended unit tests for AquariumDetector helpers in core/detection/aquarium_detector.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.detection.aquarium_detector import (
    AquariumDetector,
    _clamp_confidence,
)


class TestClampConfidenceExtended:
    """Test _clamp_confidence bounds, defaults, and type conversions."""

    def test_clamp_confidence_within_bounds(self):
        assert _clamp_confidence(0.5, default=0.25) == 0.5
        assert _clamp_confidence(0.1, default=0.25) == 0.1

    def test_clamp_confidence_none_uses_default(self):
        assert _clamp_confidence(None, default=0.35) == 0.35

    def test_clamp_confidence_lower_bound(self):
        assert _clamp_confidence(-0.5, default=0.25) == 0.01
        assert _clamp_confidence(0.0001, default=0.25) == 0.01

    def test_clamp_confidence_upper_bound(self):
        assert _clamp_confidence(1.5, default=0.25) == 0.95
        assert _clamp_confidence(0.99, default=0.25) == 0.95


class TestAquariumDetectorExtended:
    """Test AquariumDetector geometric utilities and initialization guards."""

    def test_init_invalid_mode_raises(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            with pytest.raises(ValueError, match="Invalid mode"):
                AquariumDetector(model_path="model.pt", mode="invalid_mode")

    def test_calculate_iou_overlapping_squares(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            detector = AquariumDetector(model_path="model.pt", mode="seg")

            poly1 = [(0, 0), (10, 0), (10, 10), (0, 10)]
            poly2 = [(5, 0), (15, 0), (15, 10), (5, 10)]

            # Intersection = 5x10 = 50, Union = 15x10 = 150 -> IoU = 50/150 = 1/3
            iou = detector._calculate_iou(poly1, poly2)
            assert pytest.approx(iou, rel=0.01) == 1.0 / 3.0

    def test_calculate_iou_disjoint_polygons(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            detector = AquariumDetector(model_path="model.pt", mode="seg")

            poly1 = [(0, 0), (10, 0), (10, 10), (0, 10)]
            poly2 = [(20, 20), (30, 20), (30, 30), (20, 30)]

            iou = detector._calculate_iou(poly1, poly2)
            assert iou == 0.0

    def test_calculate_iou_invalid_polygons_returns_zero(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            detector = AquariumDetector(model_path="model.pt", mode="seg")

            iou = detector._calculate_iou([], [])
            assert iou == 0.0

    def test_extract_polygon_from_detection_empty_results(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            detector = AquariumDetector(model_path="model.pt", mode="det")
            frame = np.zeros((100, 100, 3), dtype=np.uint8)

            assert detector._extract_polygon_from_detection(frame, []) is None

    def test_extract_polygon_from_detection_valid_box(self):
        with patch("zebtrack.core.detection.aquarium_detector.YOLO"):
            detector = AquariumDetector(model_path="model.pt", mode="det")
            frame = np.zeros((100, 100, 3), dtype=np.uint8)

            box_mock = MagicMock()
            box_mock.conf = 0.9
            box_mock.xyxy = [np.array([20, 20, 80, 80])]

            result_mock = MagicMock()
            result_mock.boxes = [box_mock]

            polygon = detector._extract_polygon_from_detection(frame, [result_mock])
            assert polygon is not None
            assert polygon.shape == (4, 2)
            np.testing.assert_array_equal(polygon[0], [20, 20])
            np.testing.assert_array_equal(polygon[2], [80, 80])
