"""Tests for hardware_benchmark cache and settings helpers."""

from __future__ import annotations

from zebtrack.utils import hardware_benchmark as hb


def _make_result(*, fingerprint: str = "fp", with_rec: bool = True) -> hb.SystemBenchmarkResult:
    result = hb.SystemBenchmarkResult()
    result.hardware.fingerprint = fingerprint
    if with_rec:
        result.recommendation = hb.BenchmarkRecommendation(
            backend="openvino",
            device_live="CPU",
            device_batch="CPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            decode_backend="FFMPEG",
            recommended_batch_size=4,
            estimated_fps_live=120.0,
            estimated_fps_batch=240.0,
        )
    return result


def test_load_cached_benchmark_returns_none_when_missing(tmp_path, monkeypatch):
    cache_path = tmp_path / "bench.json"
    monkeypatch.setattr(hb, "get_benchmark_cache_path", lambda: cache_path)
    assert hb.load_cached_benchmark() is None


def test_save_and_load_cached_benchmark(tmp_path, monkeypatch):
    cache_path = tmp_path / "bench.json"
    monkeypatch.setattr(hb, "get_benchmark_cache_path", lambda: cache_path)

    expected = _make_result(fingerprint="abc")

    monkeypatch.setattr(hb, "detect_hardware_profile", lambda: expected.hardware)

    hb.save_benchmark_cache(expected)
    loaded = hb.load_cached_benchmark()

    assert loaded is not None
    assert loaded.hardware.fingerprint == "abc"
    assert loaded.recommendation is not None
    assert loaded.recommendation.backend == "openvino"


def test_load_cached_benchmark_invalid_when_fingerprint_changes(tmp_path, monkeypatch):
    cache_path = tmp_path / "bench.json"
    monkeypatch.setattr(hb, "get_benchmark_cache_path", lambda: cache_path)

    cached = _make_result(fingerprint="cached")
    hb.save_benchmark_cache(cached)

    current = hb.HardwareProfile()
    current.fingerprint = "current"
    monkeypatch.setattr(hb, "detect_hardware_profile", lambda: current)

    assert hb.load_cached_benchmark() is None


def test_get_or_run_benchmark_uses_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "bench.json"
    monkeypatch.setattr(hb, "get_benchmark_cache_path", lambda: cache_path)

    cached = _make_result(fingerprint="abc")
    monkeypatch.setattr(hb, "load_cached_benchmark", lambda: cached)

    from unittest.mock import MagicMock

    run_mock = MagicMock()
    monkeypatch.setattr(hb, "run_adaptive_benchmark", run_mock)

    result = hb.get_or_run_benchmark()
    assert result is cached
    run_mock.assert_not_called()


def test_get_or_run_benchmark_force_rerun(tmp_path, monkeypatch):
    cache_path = tmp_path / "bench.json"
    monkeypatch.setattr(hb, "get_benchmark_cache_path", lambda: cache_path)

    expected = _make_result(fingerprint="abc")
    monkeypatch.setattr(hb, "run_adaptive_benchmark", lambda **_: expected)

    save_called = {"value": False}

    def _save(result):
        save_called["value"] = True
        assert result is expected

    monkeypatch.setattr(hb, "save_benchmark_cache", _save)

    result = hb.get_or_run_benchmark(force_rerun=True, quick_mode=True)
    assert result is expected
    assert save_called["value"]


def test_get_optimal_settings_without_recommendation():
    result = _make_result(with_rec=False)
    assert hb.get_optimal_settings(result) == {}


def test_get_optimal_settings_from_recommendation():
    result = _make_result(with_rec=True)
    settings = hb.get_optimal_settings(result)

    assert settings["use_openvino"] is True
    assert settings["openvino"]["device"] == "CPU"
    assert settings["openvino"]["precision"] == "FP16"
    assert settings["batch_size"] == 4


def test_print_benchmark_summary(capsys):
    result = _make_result(with_rec=True)
    result.hardware.cpu_name = "Test CPU"
    result.hardware.gpu_name = "Test GPU"
    result.hardware.gpu_type = hb.GPUType.INTEL_IGPU
    result.hardware.gpu_memory_gb = 1.5
    result.hardware.openvino_devices = ["CPU"]

    hb.print_benchmark_summary(result)
    out = capsys.readouterr().out
    assert "HARDWARE BENCHMARK SUMMARY" in out
    assert "CPU: Test CPU" in out
    assert "GPU: Test GPU" in out
