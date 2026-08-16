"""
Extended unit tests for DetectionPostProcessor stateless utilities.
"""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor


class TestDetectionPostProcessorExtended:
    """Test DetectionPostProcessor validation, normalization, math, and fallbacks."""

    def test_validate_frame_success_and_errors(self):
        valid = np.zeros((100, 100, 3), dtype=np.uint8)
        DetectionPostProcessor.validate_frame(valid)  # Should not raise

        with pytest.raises(ValueError, match="valid numpy array"):
            DetectionPostProcessor.validate_frame(None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="cannot be empty"):
            DetectionPostProcessor.validate_frame(np.array([]))

        with pytest.raises(ValueError, match="HxWx3"):
            DetectionPostProcessor.validate_frame(np.zeros((100, 100), dtype=np.uint8))

    def test_ensure_track_tuple(self):
        # 5-element
        t5 = (10, 20, 30, 40, 0.85)
        res5 = DetectionPostProcessor.ensure_track_tuple(t5)
        assert res5 == (10.0, 20.0, 30.0, 40.0, 0.85, None, 0)

        # 6-element
        t6 = (10, 20, 30, 40, 0.85, 3)
        res6 = DetectionPostProcessor.ensure_track_tuple(t6)
        assert res6 == (10.0, 20.0, 30.0, 40.0, 0.85, 3, 0)

        # 7-element
        t7 = (10, 20, 30, 40, 0.85, 3, 1)
        res7 = DetectionPostProcessor.ensure_track_tuple(t7)
        assert res7 == (10.0, 20.0, 30.0, 40.0, 0.85, 3, 1)

    def test_offset_detections(self):
        raw = [(10, 10, 20, 20, 0.9, 1, 0)]
        offset = DetectionPostProcessor.offset_detections(raw, dx=50, dy=100)
        assert offset == [(60.0, 110.0, 70.0, 120.0, 0.9, 1, 0)]

    def test_calculate_iou(self):
        # Disjoint boxes
        assert DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 20, 20, 30, 30) == 0.0

        # Exact match 10x10
        iou_exact = DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 0, 0, 10, 10)
        assert iou_exact == pytest.approx(1.0)

        # 50% overlap: box A 0..10, box B 5..15 -> inter = 50, union = 150 -> 1/3
        iou = DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 5, 0, 15, 10)
        assert iou == pytest.approx(50.0 / 150.0)

    def test_apply_class_mismatch_fallback(self):
        poly = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)  # Area 10,000

        # Small bbox (10x10 = 100 area, 1% of arena) misclassified as aquarium (class 1)
        # Should be reclassified to animal (class 0)
        dets = [(10, 10, 20, 20, 0.8, 1, 1)]
        corrected = DetectionPostProcessor.apply_class_mismatch_fallback(
            detections=dets,
            scaled_polygon=poly,
            aquarium_class_id=1,
            animal_class_id=0,
        )
        assert corrected[0][6] == 0  # Reclassified to class 0

        # Huge bbox (90x90 = 8100 area, 81% of arena) stays aquarium (class 1)
        dets_huge = [(5, 5, 95, 95, 0.8, 1, 1)]
        not_corrected = DetectionPostProcessor.apply_class_mismatch_fallback(
            detections=dets_huge,
            scaled_polygon=poly,
            aquarium_class_id=1,
            animal_class_id=0,
        )
        assert not_corrected[0][6] == 1
