"""
Extended unit tests for ClosedLoopLatencyLog and latency calculation helpers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from zebtrack.core.services.closed_loop_latency import (
    ClosedLoopLatencyLog,
    _ms,
    _sampling_interval_ms,
)


class TestClosedLoopLatencyExtended:
    """Test closed-loop latency helpers and log persistence."""

    def test_ms_helper(self):
        assert _ms(1.0, 1.05) == pytest.approx(50.0)
        assert _ms(None, 1.0) is None
        assert _ms(1.0, None) is None

    def test_sampling_interval_ms_helper(self):
        # 10 frames / 30 fps * 1000 = 333.33 ms
        assert _sampling_interval_ms(10, 30.0) == pytest.approx(333.333, rel=1e-3)
        assert _sampling_interval_ms(None, 30.0) is None
        assert _sampling_interval_ms(10, 0) is None
        assert _sampling_interval_ms(10, "invalid") is None

    def test_latency_log_on_sample_and_stream(self, tmp_path: Path):
        log_sink = ClosedLoopLatencyLog(tmp_path, "session_test")

        context = {
            "event_id": 1,
            "frame_t0": 100.0,
            "dequeue_perf": 100.01,
            "decision_perf": 100.03,
            "analysis_interval_frames": 10,
            "fps": 30.0,
            "fps_configured": 30.0,
            "roi": "ZoneA",
            "edge": "enter",
            "token": "A",
            "frame": 50,
            "session_ts_s": 1.5,
            "trigger_wall_s": 1700000000.0,
        }

        log_sink.on_sample(context, t_send=100.04, t_ack=100.06, ack_text="Red LED 1 ON")

        assert log_sink.row_count == 1
        assert log_sink._csv_path.exists()

        df_csv = pd.read_csv(log_sink._csv_path)
        assert len(df_csv) == 1
        assert df_csv["roi"].iloc[0] == "ZoneA"
        assert df_csv["token"].iloc[0] == "A"
        assert df_csv["serial_act_ms"].iloc[0] == pytest.approx(20.0, rel=1e-2)

        # Finalize writes parquet
        parquet_path = log_sink.finalize()
        assert parquet_path is not None
        assert parquet_path.exists()
        df_parquet = pd.read_parquet(parquet_path)
        assert len(df_parquet) == 1

    def test_finalize_without_rows_returns_none(self, tmp_path: Path):
        log_sink = ClosedLoopLatencyLog(tmp_path, "empty_session")
        assert log_sink.finalize() is None

    def test_csv_stream_exception_is_caught_gracefully(self, tmp_path: Path):
        log_sink = ClosedLoopLatencyLog(tmp_path, "err_session")
        with patch.object(Path, "open", side_effect=OSError("Disk full")):
            # Should not raise
            log_sink.on_sample({}, t_send=None, t_ack=None, ack_text=None)
            assert log_sink.row_count == 1
