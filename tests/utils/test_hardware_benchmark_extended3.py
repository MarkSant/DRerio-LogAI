"""Extended unit tests for utils/hardware_benchmark.py (Part 3)."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    GPUType,
    HardwareProfile,
    SystemBenchmarkResult,
    _detect_system_memory_gb,
)


class TestHardwareBenchmarkExtended3:
    """Test SystemBenchmarkResult dataclass serialization and memory detection."""

    def test_system_benchmark_result_to_dict_and_from_dict(self):
        prof = HardwareProfile(
            cpu_name="AMD Ryzen 9",
            cpu_cores=16,
            gpu_type=GPUType.NVIDIA,
            gpu_name="RTX 4090",
            total_memory_gb=64.0,
        )
        rec = BenchmarkRecommendation(
            backend="pytorch",
            device_live="cuda",
            device_batch="cuda",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=False,
            decode_backend="MSMF",
            recommended_batch_size=8,
            estimated_fps_live=150.0,
            estimated_fps_batch=300.0,
        )
        sys_res = SystemBenchmarkResult(
            benchmark_version="1.2.0",
            benchmark_date="2026-08-17",
            benchmark_duration_s=45.2,
            hardware=prof,
            recommendation=rec,
        )

        d = sys_res.to_dict()
        assert d["benchmark_version"] == "1.2.0"
        assert d["hardware"]["cpu_name"] == "AMD Ryzen 9"
        assert d["recommendation"]["backend"] == "pytorch"

        restored = SystemBenchmarkResult.from_dict(d)
        assert restored.benchmark_version == "1.2.0"
        assert restored.hardware.gpu_type == GPUType.NVIDIA
        assert restored.recommendation is not None
        assert restored.recommendation.backend == "pytorch"

    def test_detect_system_memory_gb(self):
        ram_gb = _detect_system_memory_gb()
        assert isinstance(ram_gb, float)
        assert ram_gb > 0.0
