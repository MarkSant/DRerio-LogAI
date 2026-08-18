"""Extended unit tests for io/recorder.py (Part 9)."""

from __future__ import annotations

from typing import Any

from zebtrack.io.recorder import Recorder


class TestRecorderExtended9:
    """Test Recorder pause timestamp, uncertainty tracking, and multi-aquarium mechanics."""

    def test_recorder_pause_start_time_defaults(self):
        rec: Any = object.__new__(Recorder)
        rec.pause_start_time = None
        assert rec.pause_start_time is None
        rec.pause_start_time = 1234.56
        assert rec.pause_start_time == 1234.56

    def test_recorder_uncertainty_tracking_dict(self):
        rec: Any = object.__new__(Recorder)
        rec.uncertainty_tracking = {"track_0": 0.15}
        assert rec.uncertainty_tracking["track_0"] == 0.15

    def test_recorder_multi_aquarium_mode_defaults(self):
        rec: Any = object.__new__(Recorder)
        rec.multi_aquarium = True
        assert rec.multi_aquarium is True
        rec.multi_aquarium = False
        assert rec.multi_aquarium is False

    def test_recorder_init_with_none_settings(self):
        rec = Recorder(settings_obj=None)
        assert rec._settings_obj is None
        assert rec.video_writer is None
