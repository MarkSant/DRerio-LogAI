"""Tests for Recorder buffer-cap safety guard (P0 audit fix).

Validates:
- _should_flush returns True when buffer hits MAX_BUFFER_ROWS
- Error re-injection respects the safety cap
- Normal flush behaviour is unchanged
"""

import time

from zebtrack.io.recorder import Recorder


class TestRecorderBufferCap:
    """Verify the _max_buffer_rows safety cap prevents unbounded growth."""

    def _make_recorder(self, max_buffer_rows: int = 50) -> Recorder:
        r = Recorder()
        r._max_buffer_rows = max_buffer_rows
        r._flush_row_threshold = 500  # normal threshold much higher for test
        r._flush_interval_seconds = 9999.0
        r._last_flush_time = time.time()
        return r

    def test_should_flush_false_below_threshold(self):
        r = self._make_recorder(max_buffer_rows=100)
        r.detection_data = [{"frame": i} for i in range(10)]
        assert not r._should_flush()

    def test_should_flush_true_at_cap(self):
        r = self._make_recorder(max_buffer_rows=50)
        r.detection_data = [{"frame": i} for i in range(50)]
        assert r._should_flush()

    def test_should_flush_true_above_cap(self):
        r = self._make_recorder(max_buffer_rows=50)
        r.detection_data = [{"frame": i} for i in range(100)]
        assert r._should_flush()

    def test_normal_threshold_still_works(self):
        r = Recorder()
        r._flush_row_threshold = 10
        r._flush_interval_seconds = 9999.0
        r._last_flush_time = time.time()
        r.detection_data = [{"frame": i} for i in range(10)]
        assert r._should_flush()

    def test_reinjection_capped_on_error(self):
        """Simulate a flush error path where snapshot is re-injected.

        The combined buffer should never exceed _max_buffer_rows.
        """
        r = self._make_recorder(max_buffer_rows=20)
        # Existing buffer has 10 items
        r.detection_data = [{"frame": i, "track_id": i} for i in range(10)]
        # Simulate a snapshot of 25 items that failed to write
        snapshot = [{"frame": i + 100, "track_id": i} for i in range(25)]

        with r._data_lock:
            combined = snapshot + r.detection_data
            if len(combined) > r._max_buffer_rows:
                combined = combined[-r._max_buffer_rows :]
            r.detection_data = combined

        assert len(r.detection_data) == 20  # capped at max_buffer_rows

    def test_reinjection_keeps_all_when_under_cap(self):
        r = self._make_recorder(max_buffer_rows=100)
        r.detection_data = [{"frame": i} for i in range(5)]
        snapshot = [{"frame": i + 100} for i in range(10)]

        with r._data_lock:
            combined = snapshot + r.detection_data
            if len(combined) > r._max_buffer_rows:
                combined = combined[-r._max_buffer_rows :]
            r.detection_data = combined

        assert len(r.detection_data) == 15  # all kept


class TestFailedWriteKeepsTheRows:
    """F2 pragma review: drive the real flush, not a copy of its arithmetic."""

    @staticmethod
    def _recording(tmp_path, monkeypatch):
        import zebtrack.io.recorder as recorder_module
        from zebtrack.core.detection import ZoneData

        output = tmp_path / "session"
        output.mkdir()
        r = Recorder()
        r._flush_row_threshold = 10_000
        r._flush_interval_seconds = 9999.0
        r.start_recording(str(output), 640, 480, zones=ZoneData(), is_video_file=True)
        for frame in (1, 2, 3):
            r.write_detection_data(frame / 30.0, frame, [(0, 0, 10, 10, 0.9, 1)])

        real_writer = recorder_module.pq.ParquetWriter

        def failing_writer(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(recorder_module.pq, "ParquetWriter", failing_writer)
        return (
            r,
            output,
            lambda: monkeypatch.setattr(recorder_module.pq, "ParquetWriter", real_writer),
        )

    def test_rows_return_to_the_buffer_and_reach_disk_on_retry(self, tmp_path, monkeypatch):
        import pandas as pd

        r, output, heal_disk = self._recording(tmp_path, monkeypatch)

        r._flush_detection_data(force=True)
        assert [row["frame"] for row in r.detection_data] == [1, 2, 3]

        heal_disk()
        r.stop_recording()
        written = pd.read_parquet(output / f"3_CoordMovimento_{output.name}.parquet")
        assert written["frame"].tolist() == [1, 2, 3]

    def test_reinjection_keeps_only_the_newest_rows_under_the_cap(self, tmp_path, monkeypatch):
        r, _output, heal_disk = self._recording(tmp_path, monkeypatch)
        r._max_buffer_rows = 2

        r._flush_detection_data(force=True)

        assert [row["frame"] for row in r.detection_data] == [2, 3]
        heal_disk()
        r.stop_recording(force_stop=True)
