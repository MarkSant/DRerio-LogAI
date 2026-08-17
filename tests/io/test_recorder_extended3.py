"""Extended unit tests for io/recorder.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.io.recorder import Recorder


class TestRecorderExtended3:
    """Test Recorder buffer safety cap, locking mechanisms, and context manager."""

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
