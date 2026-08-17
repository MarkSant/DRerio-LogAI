"""Extended unit tests for io/recorder.py (Part 8)."""

from __future__ import annotations

import pytest

from zebtrack.io.recorder import Recorder


class TestRecorderExtended8:
    """Test Recorder buffer initial states and flush timing defaults."""

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
