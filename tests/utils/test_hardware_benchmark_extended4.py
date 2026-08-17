"""Extended unit tests for utils/hardware_benchmark.py (Part 4)."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    BenchmarkResult,
    SystemBenchmarkResult,
)


class TestHardwareBenchmarkExtended4:
    """Test BenchmarkResult and BenchmarkRecommendation serialization and lifecycle."""

    def test_benchmark_result_to_dict(self):
        res = BenchmarkResult(
            name="OpenVINO_Inference",
            device="CPU",
            scenario="live",
            avg_ms=12.5,
            min_ms=10.0,
            max_ms=15.0,
            fps=80.0,
        )

        d = res.to_dict()
        assert d["name"] == "OpenVINO_Inference"
        assert d["device"] == "CPU"
        assert d["scenario"] == "live"
        assert d["avg_ms"] == 12.5
        assert d["fps"] == 80.0

    def test_benchmark_recommendation_serialization(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="CPU",
            device_batch="GPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            decode_backend="FFMPEG",
            recommended_batch_size=4,
            estimated_fps_live=60.0,
            estimated_fps_batch=120.0,
        )

        d = rec.to_dict()
        assert d["backend"] == "openvino"
        assert d["device_live"] == "CPU"
        assert d["device_batch"] == "GPU"
        assert d["recommended_batch_size"] == 4

        recreated = BenchmarkRecommendation.from_dict(d)
        assert recreated.backend == "openvino"
        assert recreated.estimated_fps_live == 60.0

    def test_system_benchmark_result_default_metadata(self):
        sys_res = SystemBenchmarkResult()
        assert sys_res.benchmark_version == "1.0.0"
        assert sys_res.decode_results == {}
        assert sys_res.compute_results == {}
