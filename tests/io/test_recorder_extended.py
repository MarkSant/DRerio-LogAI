"""Extended unit tests for Recorder in io/recorder.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.io.recorder import Recorder
from zebtrack.settings import load_settings


class TestRecorderExtended:
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


class TestRecorderExtended2:
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


class TestRecorderExtended3:
    def test_initialization_defaults_and_safety_caps(self):
        recorder = Recorder(settings_obj=None)
        assert recorder.is_recording is False
        assert recorder.video_writer is None
        assert recorder.frame_count == 0
        assert recorder.detection_data == []
        assert recorder._max_buffer_rows == 10_000
        assert recorder._data_lock is not None
        assert recorder._writer_lock is not None
        assert recorder._fps == 30.0
        assert recorder._parquet_compression == "snappy"

    def test_context_manager_protocol(self):
        recorder = Recorder(settings_obj=None)
        recorder.is_recording = True
        recorder.stop_recording = MagicMock()  # type: ignore[method-assign]

        with recorder as r:
            assert r is recorder

        recorder.stop_recording.assert_called_once()

    def test_pixel_per_cm_ratio_setter_guard(self):
        recorder = Recorder(settings_obj=None)
        recorder.is_recording = True
        recorder._initial_schema_columns = frozenset(["frame", "track_id"])

        with pytest.raises(ValueError, match="Cannot change calibration during active recording"):
            recorder.pixel_per_cm_ratio = 15.0

    def test_pixel_per_cm_ratio_setter_allowed_when_idle(self):
        recorder = Recorder(settings_obj=None)
        recorder.is_recording = False
        recorder.pixel_per_cm_ratio = 12.5

        assert recorder.pixel_per_cm_ratio == 12.5


class TestRecorderExtended4:
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


class TestRecorderExtended6:
    def test_recorder_uncertainty_tracking_initial(self):
        rec = Recorder()
        assert rec._last_detections_by_track == {}
        assert rec._total_paused_duration == 0.0
        assert rec._pause_start_time is None
        assert rec._flush_signal.is_set() is False
        assert rec._flush_stop.is_set() is False

    def test_recorder_buffer_safety_cap(self):
        rec = Recorder()
        assert rec._max_buffer_rows == 10_000
        assert rec.is_recording is False

    def test_recorder_pixel_per_cm_initial(self):
        rec = Recorder()
        assert rec._pixel_per_cm_ratio is None
        assert rec._calibration is None
        assert rec._parquet_writer is None
        assert rec._parquet_schema is None


class TestRecorderExtended7:
    def test_recorder_pause_and_mask_defaults(self):
        rec = Recorder()
        assert rec._is_paused is False
        assert rec._mask_data == []
        assert rec._persist_masks is False
        assert rec._multi_aquarium_mode is False
        assert rec._aquarium_id is None

    def test_recorder_parquet_filenames_initial(self):
        rec = Recorder()
        assert rec._parquet_filename == ""
        assert rec._mask_parquet_filename == ""
        assert rec._last_flush_time == 0.0

    def test_recorder_settings_obj_attribute(self):
        rec = Recorder(settings_obj=None)
        assert rec._settings_obj is None


class TestRecorderExtended8:
    def test_recorder_buffer_initialization(self):
        rec = Recorder()
        assert rec._pixel_per_cm_ratio is None
        assert rec._calibration is None
        assert rec._parquet_writer is None
        assert rec.is_recording is False
        assert rec._total_paused_duration == 0.0

    def test_recorder_flush_thread_defaults(self):
        rec = Recorder()
        assert rec._flush_thread is None
        assert rec._flush_drain_on_stop is True

    def test_recorder_mask_data_append(self):
        rec = Recorder()
        rec._mask_data.append({"frame": 1, "mask": "data"})
        assert len(rec._mask_data) == 1
        assert rec._mask_data[0]["frame"] == 1

    def test_recorder_pause_duration_accumulation(self):
        rec = Recorder()
        rec._total_paused_duration += 1.5
        assert rec._total_paused_duration == pytest.approx(1.5)


class TestRecorderExtended9:
    def test_recorder_init_with_none_settings(self):
        rec = Recorder(settings_obj=None)
        assert rec._settings_obj is None
        assert rec.video_writer is None
