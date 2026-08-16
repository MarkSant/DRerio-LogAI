"""Extended unit tests for Recorder in io/recorder.py."""

from __future__ import annotations

import pytest

from zebtrack.io.recorder import Recorder
from zebtrack.settings import load_settings


class TestRecorderExtended:
    """Test Recorder calibration guards, pause/resume, and context manager."""

    @pytest.fixture
    def recorder(self) -> Recorder:
        settings = load_settings()
        return Recorder(settings_obj=settings)

    def test_initial_state(self, recorder: Recorder):
        assert recorder.is_recording is False
        assert recorder._is_paused is False
        assert recorder.pixel_per_cm_ratio is None
        assert recorder.calibration is None

    def test_calibration_change_during_recording_raises(self, recorder: Recorder):
        recorder.is_recording = True
        recorder._initial_schema_columns = frozenset(["frame", "x_px", "y_px"])

        # Attempting to add calibration ratio while initial schema had no x_cm
        with pytest.raises(ValueError, match="Cannot change calibration during active recording"):
            recorder.pixel_per_cm_ratio = 10.5

    def test_calibration_object_change_during_recording_raises(self, recorder: Recorder):
        recorder.is_recording = True
        recorder._initial_schema_columns = frozenset(["frame", "x_px", "y_px"])

        # Attempting to attach calibration object during active recording
        with pytest.raises(ValueError, match="Cannot add/remove calibration"):
            recorder.calibration = {"homography_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}

    def test_pause_and_resume_recording(self, recorder: Recorder):
        recorder.is_recording = True
        assert recorder._is_paused is False

        recorder.pause_recording()
        assert recorder._is_paused is True
        assert recorder._pause_start_time is not None

        # Double pause is idempotent
        recorder.pause_recording()
        assert recorder._is_paused is True

        recorder.resume_recording()
        assert recorder._is_paused is False
        assert recorder._total_paused_duration >= 0.0

        # Resume when not paused is no-op
        recorder.resume_recording()
        assert recorder._is_paused is False

    def test_context_manager_protocol(self, recorder: Recorder):
        with recorder as rec:
            assert rec is recorder
            rec.is_recording = False
        assert recorder.is_recording is False

    def test_calculate_iou(self, recorder: Recorder):
        box1 = (0.0, 0.0, 10.0, 10.0)
        box2 = (5.0, 0.0, 15.0, 10.0)
        # Intersection: width 5, height 10 -> area 50
        # Union: area 100 + 100 - 50 = 150
        # IoU = 50 / 150 = 1/3
        iou = recorder._calculate_iou(box1, box2)
        assert iou == pytest.approx(1.0 / 3.0)

    def test_calculate_iou_no_overlap(self, recorder: Recorder):
        box1 = (0.0, 0.0, 5.0, 5.0)
        box2 = (10.0, 10.0, 15.0, 15.0)
        assert recorder._calculate_iou(box1, box2) == 0.0
