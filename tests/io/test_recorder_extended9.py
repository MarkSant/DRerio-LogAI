"""Extended unit tests for io/recorder.py (Part 9)."""

from __future__ import annotations

from zebtrack.io.recorder import Recorder


class TestRecorderExtended9:
    """Test Recorder pause timestamp, uncertainty tracking, and multi-aquarium mechanics."""

    def test_recorder_init_with_none_settings(self):
        rec = Recorder(settings_obj=None)
        assert rec._settings_obj is None
        assert rec.video_writer is None
