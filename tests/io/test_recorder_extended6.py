"""Extended unit tests for io/recorder.py (Part 6)."""

from __future__ import annotations

from zebtrack.io.recorder import Recorder


class TestRecorderExtended6:
    """Test Recorder uncertainty tracking dictionary, buffer rows, and flush event states."""

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
