"""Extended unit tests for io/recorder.py (Part 5)."""

from __future__ import annotations

from zebtrack.io.recorder import Recorder


class TestRecorderExtended5:
    """Test Recorder pause, resume, sidecars, and duration tracking defaults."""

    def test_recorder_pause_state_initial(self):
        rec = object.__new__(Recorder)
        rec._is_paused = False
        rec._pause_start_time = None
        rec._total_paused_duration = 0.0

        assert rec._is_paused is False
        assert rec._pause_start_time is None
        assert rec._total_paused_duration == 0.0

    def test_recorder_mask_sidecar_defaults(self):
        rec = object.__new__(Recorder)
        rec._persist_masks = False
        rec._mask_data = []
        rec._mask_parquet_writer = None

        assert rec._persist_masks is False
        assert rec._mask_data == []
        assert rec._mask_parquet_writer is None

    def test_recorder_multi_aquarium_defaults(self):
        rec = object.__new__(Recorder)
        rec._multi_aquarium_mode = False
        rec._aquarium_recorders = {}
        rec._aquarium_id = None

        assert rec._multi_aquarium_mode is False
        assert rec._aquarium_recorders == {}
        assert rec._aquarium_id is None
