"""Extended unit tests for io/recorder.py (Part 7)."""

from __future__ import annotations

from zebtrack.io.recorder import Recorder


class TestRecorderExtended7:
    """Test Recorder pause states, multi aquarium mode, and mask data initialization."""

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
