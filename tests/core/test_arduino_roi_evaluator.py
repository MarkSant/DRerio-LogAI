"""Tests for ArduinoRoiEvaluator (per-frame ROI occupancy geometry)."""

from __future__ import annotations

import numpy as np

from zebtrack.core.services.arduino_roi_evaluator import ArduinoRoiEvaluator

# Two disjoint 10x10 squares.
SQUARE_A = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)
SQUARE_B = np.array([[100, 100], [110, 100], [110, 110], [100, 110]], dtype=np.int32)


def test_centroid_inside_single_roi():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(5, 5)]) == {"A"}


def test_centroid_outside_all_rois():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(50, 50)]) == set()


def test_multiple_animals_occupy_multiple_rois():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(5, 5), (105, 105)]) == {"A", "B"}


def test_any_track_scope_one_roi_two_animals():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    # Two animals both in A -> still just {"A"} (set semantics)
    assert ev.occupied_rois([(3, 3), (7, 7)]) == {"A"}


def test_empty_and_degenerate_polygons_ignored():
    ev = ArduinoRoiEvaluator(
        ["A", "Empty", "Line"],
        [SQUARE_A, np.array([], dtype=np.int32), np.array([[0, 0], [1, 1]], dtype=np.int32)],
    )
    assert ev.roi_names == ["A"]
    assert ev.has_rois() is True


def test_no_rois():
    ev = ArduinoRoiEvaluator([], [])
    assert ev.has_rois() is False
    assert ev.occupied_rois([(5, 5)]) == set()


def test_centroid_of_bbox():
    assert ArduinoRoiEvaluator.centroid_of_bbox(0, 0, 10, 20) == (5.0, 10.0)


def test_accepts_list_polygons():
    ev = ArduinoRoiEvaluator(["A"], [[[0, 0], [10, 0], [10, 10], [0, 10]]])
    assert ev.occupied_rois([(5, 5)]) == {"A"}
