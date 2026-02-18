from pathlib import Path

import numpy as np

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.metrics_cache import MetricsCache


def _dummy_parquet(path: Path, name: str) -> Path:
    target = path / name
    target.write_bytes(b"dummy-parquet-data" * 8)
    return target


def test_metrics_cache_miss_save_hit(tmp_path):
    parquet_path = _dummy_parquet(tmp_path, "traj.parquet")
    cache = MetricsCache(tmp_path / "cache")

    calibration = {"pixelcm_x": 10.0, "pixelcm_y": 10.0}
    smoothing_window = 5
    smoothing_polyorder = 2

    assert (
        cache.get_base_metrics(parquet_path, calibration, smoothing_window, smoothing_polyorder)
        is None
    )

    metrics = {"distance_cm": 12.3, "frames": 5}
    cache.save_base_metrics(
        parquet_path, calibration, smoothing_window, smoothing_polyorder, metrics
    )

    cached = cache.get_base_metrics(
        parquet_path, calibration, smoothing_window, smoothing_polyorder
    )
    assert cached == metrics


def test_metrics_cache_corrupted_file_is_removed(tmp_path):
    parquet_path = _dummy_parquet(tmp_path, "traj.parquet")
    cache = MetricsCache(tmp_path / "cache")
    calibration = {"pixelcm_x": 10.0, "pixelcm_y": 10.0}

    cache_file = cache.cache_dir / cache._cache_key(parquet_path, calibration, 3, 1)
    cache.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"not-valid-json{{{")

    result = cache.get_base_metrics(parquet_path, calibration, 3, 1)

    assert result is None
    assert not cache_file.exists()


def test_metrics_cache_clear_specific_and_all(tmp_path):
    parquet_a = _dummy_parquet(tmp_path, "a.parquet")
    parquet_b = _dummy_parquet(tmp_path, "b.parquet")
    cache = MetricsCache(tmp_path / "cache")
    calibration = {"pixelcm_x": 10.0, "pixelcm_y": 10.0}

    cache.save_base_metrics(parquet_a, calibration, 3, 1, {"a": 1})
    cache.save_base_metrics(parquet_b, calibration, 3, 1, {"b": 2})

    cleared_specific = cache.clear_cache(parquet_a)
    assert cleared_specific == 1
    assert len(list(cache.cache_dir.glob("*.json"))) == 1

    cleared_all = cache.clear_cache()
    assert cleared_all == 1
    assert len(list(cache.cache_dir.glob("*.json"))) == 0


def test_analysis_service_initializes_metrics_cache(tmp_path):
    tmp_path / "cache"
    from tests.helpers import create_mock_settings

    settings = create_mock_settings()

    service = AnalysisService(settings_obj=settings, enable_metrics_cache=True)

    assert service.metrics_cache is not None


def test_metrics_cache_numpy_types_round_trip(tmp_path):
    """Verify NumpyJSONEncoder handles numpy types correctly during cache."""
    parquet_path = _dummy_parquet(tmp_path, "numpy_test.parquet")
    cache = MetricsCache(tmp_path / "cache")
    calibration = {"pixelcm_x": 5.0}

    metrics = {
        "np_float64": np.float64(3.14159),
        "np_int64": np.int64(42),
        "np_bool": np.bool_(True),
        "np_array": np.array([1.0, 2.0, 3.0]),
        "plain_float": 2.718,
        "plain_int": 7,
        "nested": {"np_val": np.float32(1.5)},
    }

    cache.save_base_metrics(parquet_path, calibration, 5, 2, metrics)

    cached = cache.get_base_metrics(parquet_path, calibration, 5, 2)
    assert cached is not None
    assert abs(cached["np_float64"] - 3.14159) < 1e-4
    assert cached["np_int64"] == 42
    assert cached["np_bool"] is True
    assert cached["np_array"] == [1.0, 2.0, 3.0]
    assert abs(cached["plain_float"] - 2.718) < 1e-4
    assert cached["plain_int"] == 7
    assert abs(cached["nested"]["np_val"] - 1.5) < 1e-4


def test_metrics_cache_nan_handling(tmp_path):
    """Verify NaN values are serialized as null (None) in JSON."""
    parquet_path = _dummy_parquet(tmp_path, "nan_test.parquet")
    cache = MetricsCache(tmp_path / "cache")
    calibration = {"pixelcm_x": 1.0}

    metrics = {"nan_value": np.float64("nan"), "inf_value": np.float64("inf")}

    cache.save_base_metrics(parquet_path, calibration, 3, 1, metrics)

    cached = cache.get_base_metrics(parquet_path, calibration, 3, 1)
    assert cached is not None
    assert cached["nan_value"] is None
    assert cached["inf_value"] is None


def test_metrics_cache_clears_legacy_pkl_files(tmp_path):
    """Verify clear_cache removes both .json and legacy .pkl files."""
    cache = MetricsCache(tmp_path / "cache")

    # Create a legacy .pkl file and a new .json file
    (cache.cache_dir / "old_cache.pkl").write_bytes(b"legacy")
    (cache.cache_dir / "new_cache.json").write_text("{}", encoding="utf-8")

    cleared = cache.clear_cache()
    assert cleared == 2
    assert len(list(cache.cache_dir.iterdir())) == 0
