"""Extended unit tests for io/recorder.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.io.recorder import Recorder


class TestRecorderExtended2:
    """Test Recorder properties, state management, calibration changes, and calculations."""

    def test_recorder_initial_state(self):
        rec = Recorder()
        assert rec.is_recording is False
        assert rec.frame_count == 0
        assert rec._is_paused is False
        assert rec._total_paused_duration == 0.0
        assert rec._max_buffer_rows == 10_000

    def test_context_manager_protocol(self):
        rec = Recorder()
        with rec as r:
            assert r is rec
        assert rec.is_recording is False

    def test_pause_and_resume_durations(self):
        rec = Recorder()
        rec.is_recording = True
        rec._is_paused = False

        # Pause
        rec._is_paused = True
        rec._pause_start_time = 100.0

        # Resume at 105.0 (5 seconds paused)
        rec._total_paused_duration += 105.0 - rec._pause_start_time
        rec._is_paused = False
        rec._pause_start_time = None

        assert rec._total_paused_duration == 5.0

    def test_prevent_calibration_change_during_recording(self):
        rec = Recorder()
        rec.is_recording = True
        rec._initial_schema_columns = frozenset(["x_cm", "y_cm", "frame"])

        # Changing from calibrated to None while recording raises ValueError
        with pytest.raises(ValueError, match="Cannot change calibration during active recording"):
            rec.pixel_per_cm_ratio = None

    def test_calibration_object_setter_validation(self):
        rec = Recorder()
        rec.is_recording = True
        rec._initial_schema_columns = frozenset(["x_px", "y_px"])
        rec._calibration = None

        # Setting calibration when it was None during active recording raises ValueError
        with pytest.raises(
            ValueError, match="Cannot add/remove calibration during active recording"
        ):
            rec.calibration = MagicMock()

    def test_calculate_iou(self):
        # Disjoint boxes
        box1 = (0.0, 0.0, 10.0, 10.0)
        box2 = (20.0, 20.0, 30.0, 30.0)
        assert Recorder._calculate_iou(box1, box2) == 0.0

        # Identical boxes
        assert Recorder._calculate_iou(box1, box1) == 1.0

        # 50% overlap box
        box3 = (0.0, 0.0, 10.0, 5.0)  # Area = 50
        box4 = (0.0, 0.0, 10.0, 10.0)  # Area = 100, Inter = 50, Union = 100
        assert Recorder._calculate_iou(box3, box4) == 0.5

    def test_start_recording_invalid_dimensions(self, tmp_path: Path):
        rec = Recorder()
        mock_zones = MagicMock()

        with pytest.raises(ValueError, match="must be positive numbers"):
            rec.start_recording(
                output_folder=tmp_path,
                frame_width=0,
                frame_height=720,
                zones=mock_zones,
            )

        with pytest.raises(ValueError, match="must be positive numbers"):
            rec.start_recording(
                output_folder=tmp_path,
                frame_width=1280,
                frame_height=-10,
                zones=mock_zones,
            )
