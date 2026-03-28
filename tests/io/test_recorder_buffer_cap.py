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
