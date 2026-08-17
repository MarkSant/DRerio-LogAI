"""Extended unit tests for io/recorder.py."""

from __future__ import annotations

import pytest

from zebtrack.io.recorder import Recorder


class TestRecorderExtended4:
    """Test Recorder IoU calculations and calibration guards."""

    def test_calculate_iou_identical_boxes(self):
        box1 = (0.0, 0.0, 10.0, 10.0)
        box2 = (0.0, 0.0, 10.0, 10.0)
        iou = Recorder._calculate_iou(box1, box2)
        assert iou == pytest.approx(1.0)

    def test_calculate_iou_disjoint_boxes(self):
        box1 = (0.0, 0.0, 10.0, 10.0)
        box2 = (20.0, 20.0, 30.0, 30.0)
        iou = Recorder._calculate_iou(box1, box2)
        assert iou == pytest.approx(0.0)

    def test_calculate_iou_partial_overlap(self):
        box1 = (0.0, 0.0, 10.0, 10.0)  # Area 100
        box2 = (5.0, 0.0, 15.0, 10.0)  # Area 100, intersection 5*10=50, union=150
        iou = Recorder._calculate_iou(box1, box2)
        assert iou == pytest.approx(50.0 / 150.0)

    def test_calculate_iou_contained_box(self):
        box1 = (0.0, 0.0, 10.0, 10.0)  # Area 100
        box2 = (2.0, 2.0, 8.0, 8.0)  # Area 36, union 100
        iou = Recorder._calculate_iou(box1, box2)
        assert iou == pytest.approx(36.0 / 100.0)

    def test_calculate_iou_zero_area(self):
        box1 = (0.0, 0.0, 0.0, 0.0)
        box2 = (0.0, 0.0, 0.0, 0.0)
        iou = Recorder._calculate_iou(box1, box2)
        assert iou == 0.0
