from pathlib import Path
from types import SimpleNamespace

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
    cache_file.write_bytes(b"not-a-pickle")

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
    assert len(list(cache.cache_dir.glob("*.pkl"))) == 1

    cleared_all = cache.clear_cache()
    assert cleared_all == 1
    assert len(list(cache.cache_dir.glob("*.pkl"))) == 0


def test_analysis_service_initializes_metrics_cache(tmp_path):
    cache_root = tmp_path / "cache"
    settings = SimpleNamespace()

    service = AnalysisService(settings_obj=settings, enable_metrics_cache=True)

    assert service.metrics_cache is not None
    assert service.metrics_cache.cache_dir.exists()

    # Ensure cache directory is under .cache/metrics by default
    assert "metrics" in str(service.metrics_cache.cache_dir)
