"""
Extended unit tests for MetricsCache and JSON serialization in analysis/metrics_cache.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from zebtrack.analysis.metrics_cache import (
    MetricsCache,
    _NumpyJSONEncoder,
    _sanitize_for_json,
)


class TestNumpyJSONEncoderAndSanitize:
    """Test numpy JSON serialization helpers."""

    def test_numpy_json_encoder_types(self):
        encoder = _NumpyJSONEncoder()

        assert encoder.default(np.int64(42)) == 42
        assert encoder.default(np.float64(3.14)) == 3.14
        assert encoder.default(np.bool_(True)) is True
        assert encoder.default(np.array([1, 2, 3])) == [1, 2, 3]
        assert encoder.default(np.float64(np.nan)) is None
        assert encoder.default(np.float64(np.inf)) is None

    def test_sanitize_for_json_nested(self):
        data = {
            "int_val": np.int32(10),
            "float_val": np.float64(2.5),
            "nan_val": float("nan"),
            "inf_val": np.inf,
            "arr": np.array([1.0, 2.0]),
            "nested_dict": {"sub_bool": np.bool_(False)},
            "nested_list": [np.int64(100), float("inf")],
        }
        sanitized = _sanitize_for_json(data)
        assert sanitized["int_val"] == 10
        assert sanitized["float_val"] == 2.5
        assert sanitized["nan_val"] is None
        assert sanitized["inf_val"] is None
        assert sanitized["arr"] == [1.0, 2.0]
        assert sanitized["nested_dict"]["sub_bool"] is False
        assert sanitized["nested_list"] == [100, None]


class TestMetricsCacheExtended:
    """Test MetricsCache saving, retrieval, cache key derivation, and invalidation."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> MetricsCache:
        return MetricsCache(tmp_path / "cache_dir")

    def test_cache_miss_when_no_entry(self, cache: MetricsCache, tmp_path: Path):
        parquet_file = tmp_path / "traj.parquet"
        parquet_file.write_bytes(b"dummy parquet bytes for testing")

        metrics = cache.get_base_metrics(
            parquet_file,
            calibration={"px_cm": 10.0},
            smoothing_window=5,
            smoothing_polyorder=2,
        )
        assert metrics is None

    def test_cache_save_and_hit(self, cache: MetricsCache, tmp_path: Path):
        parquet_file = tmp_path / "traj.parquet"
        parquet_file.write_bytes(b"content for hashing" * 10)

        calib = {"px_cm": 10.0, "fps": 30.0}
        data = {"total_distance_cm": 125.4, "mean_speed_cm_s": 4.2}

        cache.save_base_metrics(
            parquet_file,
            calibration=calib,
            smoothing_window=7,
            smoothing_polyorder=2,
            metrics=data,
        )

        # Cache hit
        loaded = cache.get_base_metrics(
            parquet_file,
            calibration=calib,
            smoothing_window=7,
            smoothing_polyorder=2,
        )
        assert loaded is not None
        assert loaded["total_distance_cm"] == 125.4
        assert loaded["mean_speed_cm_s"] == 4.2

    def test_cache_different_parameters_miss(self, cache: MetricsCache, tmp_path: Path):
        parquet_file = tmp_path / "traj.parquet"
        parquet_file.write_bytes(b"content" * 10)

        calib = {"px_cm": 10.0}
        cache.save_base_metrics(
            parquet_file,
            calibration=calib,
            smoothing_window=5,
            smoothing_polyorder=2,
            metrics={"dist": 10.0},
        )

        # Different smoothing window
        assert (
            cache.get_base_metrics(
                parquet_file,
                calibration=calib,
                smoothing_window=9,
                smoothing_polyorder=2,
            )
            is None
        )

        # Different calibration
        assert (
            cache.get_base_metrics(
                parquet_file,
                calibration={"px_cm": 20.0},
                smoothing_window=5,
                smoothing_polyorder=2,
            )
            is None
        )

    def test_clear_cache_all_and_specific(self, cache: MetricsCache, tmp_path: Path):
        file1 = tmp_path / "file1.parquet"
        file1.write_bytes(b"file 1 bytes")
        file2 = tmp_path / "file2.parquet"
        file2.write_bytes(b"file 2 bytes")

        cache.save_base_metrics(file1, {"c": 1}, 5, 2, {"m": 1})
        cache.save_base_metrics(file2, {"c": 1}, 5, 2, {"m": 2})

        # Clear only file1
        cleared_file1 = cache.clear_cache(file1)
        assert cleared_file1 == 1
        assert cache.get_base_metrics(file1, {"c": 1}, 5, 2) is None
        assert cache.get_base_metrics(file2, {"c": 1}, 5, 2) is not None

        # Clear all
        cleared_all = cache.clear_cache()
        assert cleared_all == 1
        assert cache.get_base_metrics(file2, {"c": 1}, 5, 2) is None
