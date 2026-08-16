"""Retry + box-selection behaviour of the live aquarium auto-detection.

Two reported symptoms are covered here:

1. "Adjusting the threshold and retrying does not seem to try again -- it just
   re-shows the previous screen." The dialog deliberately leaves the canvas
   untouched on failure, so a bare ``None`` from four different failure paths
   rendered identically. Every failure now carries a machine tag the dialog can
   turn into a specific sentence.

2. "Auto-detection behaves worse here than in the live-project flow." Part of
   that was selection: the live path took the LARGEST box regardless of
   confidence, so moving the slider changed nothing until every box vanished at
   once. It now selects like the pre-recorded path -- highest confidence among
   boxes that pass the area gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.core.detection.aquarium_retry import (
    RETRY_REASON_CAPTURE_ERROR,
    RETRY_REASON_NO_CAMERA,
    RETRY_REASON_NO_FRAMES,
    RETRY_REASON_NO_POLYGON,
    AquariumRetryOutcome,
    normalize_retry_outcome,
)


def _coordinator() -> LiveCalibrationCoordinator:
    return LiveCalibrationCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=MagicMock(),
        root=None,
        view=None,
    )


def _result(boxes: np.ndarray, confs: list[float] | None):
    """Minimal stand-in for an Ultralytics result with boxes (+ optional conf)."""
    boxes_obj = MagicMock()
    boxes_obj.xyxy = MagicMock()
    boxes_obj.xyxy.cpu.return_value.numpy.return_value = boxes
    if confs is None:
        boxes_obj.conf = None
    else:
        conf_obj = MagicMock()
        conf_obj.cpu.return_value.numpy.return_value = np.array(confs, dtype=np.float32)
        boxes_obj.conf = conf_obj
    boxes_obj.__len__ = lambda self: len(boxes)
    boxes_obj.__bool__ = lambda self: len(boxes) > 0
    return SimpleNamespace(boxes=boxes_obj, masks=None)


class TestRetryOutcomeTagging:
    def test_no_camera_is_distinguishable(self):
        coord = _coordinator()
        coord.camera = None
        coord._calibration_detector = None

        outcome = coord._retry_aquarium_detection(0.5)

        assert outcome.succeeded is False
        assert outcome.reason == RETRY_REASON_NO_CAMERA

    def test_capture_error_is_distinguishable(self):
        coord = _coordinator()
        coord.camera = MagicMock()
        coord.camera.get_frame.side_effect = OSError("device gone")
        coord._calibration_detector = MagicMock()

        outcome = coord._retry_aquarium_detection(0.5)

        assert outcome.reason == RETRY_REASON_CAPTURE_ERROR

    def test_no_frames_is_distinguishable(self):
        coord = _coordinator()
        coord.camera = MagicMock()
        coord.camera.get_frame.return_value = (False, None)
        coord._calibration_detector = MagicMock()

        outcome = coord._retry_aquarium_detection(0.5)

        assert outcome.reason == RETRY_REASON_NO_FRAMES

    def test_threshold_found_nothing_is_distinguishable(self):
        """The common case -- and the one whose message must name the threshold."""
        coord = _coordinator()
        coord.camera = MagicMock()
        coord.camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        detector = MagicMock()
        detector.model.task = "detect"
        detector.model.predict.return_value = [_result(np.empty((0, 4)), [])]
        coord._calibration_detector = detector

        outcome = coord._retry_aquarium_detection(0.9)

        assert outcome.reason == RETRY_REASON_NO_POLYGON

    def test_success_carries_polygon_and_frame(self):
        coord = _coordinator()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        coord.camera = MagicMock()
        coord.camera.get_frame.return_value = (True, frame)
        detector = MagicMock()
        detector.model.task = "detect"
        # 400x300 box in a 640x480 frame -> area ratio 0.39, inside the gate.
        detector.model.predict.return_value = [
            _result(np.array([[100.0, 100.0, 500.0, 400.0]]), [0.8])
        ]
        coord._calibration_detector = detector

        outcome = coord._retry_aquarium_detection(0.5)

        assert outcome.succeeded is True
        assert outcome.reason == "ok"
        assert len(outcome.polygon or []) == 4
        assert outcome.frame is frame


class TestBoxSelection:
    def test_highest_confidence_wins_over_largest_area(self):
        """Regression: selecting by area made the confidence slider inert."""
        coord = _coordinator()
        boxes = np.array(
            [
                [0.0, 0.0, 600.0, 450.0],  # bigger, but low confidence
                [100.0, 100.0, 500.0, 400.0],  # smaller, high confidence
            ]
        )
        result = _result(boxes, [0.10, 0.90])

        idx = coord._select_box_index(result, boxes, 640, 480)

        assert idx == 1

    def test_falls_through_to_next_box_when_top_one_fails_the_area_gate(self):
        """A frame is no longer discarded whole because its best box is oversized."""
        coord = _coordinator()
        boxes = np.array(
            [
                [0.0, 0.0, 640.0, 480.0],  # full frame -> above max area ratio
                [100.0, 100.0, 500.0, 400.0],  # valid
            ]
        )
        result = _result(boxes, [0.95, 0.60])

        idx = coord._select_box_index(result, boxes, 640, 480)

        assert idx == 1

    def test_rejects_boxes_below_the_area_floor(self):
        coord = _coordinator()
        boxes = np.array([[0.0, 0.0, 20.0, 20.0]])  # a fish, not a tank
        result = _result(boxes, [0.99])

        assert coord._select_box_index(result, boxes, 640, 480) is None

    def test_degrades_to_area_order_without_confidences(self):
        """A model/stub exposing no ``conf`` must still detect something."""
        coord = _coordinator()
        boxes = np.array(
            [
                [100.0, 100.0, 300.0, 250.0],
                [50.0, 50.0, 550.0, 430.0],
            ]
        )
        result = _result(boxes, None)

        assert coord._select_box_index(result, boxes, 640, 480) == 1

    def test_zero_area_frame_is_rejected(self):
        coord = _coordinator()
        boxes = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert coord._select_box_index(_result(boxes, [0.9]), boxes, 0, 0) is None


class TestNormalizeRetryOutcome:
    def test_legacy_tuple_is_still_accepted(self):
        """``(frame, polygon) | None`` is the module's published contract."""
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        outcome = normalize_retry_outcome((frame, [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]))

        assert outcome.succeeded is True
        assert outcome.frame is frame

    def test_legacy_none_degrades_to_no_polygon(self):
        assert normalize_retry_outcome(None).reason == RETRY_REASON_NO_POLYGON

    def test_structured_outcome_passes_through(self):
        original = AquariumRetryOutcome(reason=RETRY_REASON_NO_CAMERA)
        assert normalize_retry_outcome(original) is original
