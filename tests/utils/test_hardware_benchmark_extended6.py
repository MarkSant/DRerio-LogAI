"""Extended unit tests for utils/hardware_benchmark.py (Part 6)."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import BenchmarkResult, GPUType, HardwareProfile


class TestHardwareBenchmarkExtended6:
    """Test BenchmarkResult dataclass fields and HardwareProfile dict conversions."""

    def test_benchmark_result_fields(self):
        res = BenchmarkResult(
            name="yolov8n",
            device="CPU",
            scenario="isolated",
            avg_ms=22.5,
            min_ms=18.0,
            max_ms=30.0,
            fps=44.4,
        )

        assert res.name == "yolov8n"
        assert res.device == "CPU"
        assert res.scenario == "isolated"
        assert res.avg_ms == 22.5
        assert res.min_ms == 18.0
        assert res.max_ms == 30.0
        assert res.fps == 44.4

    def test_hardware_profile_to_dict_and_from_dict(self):
        profile = HardwareProfile(
            cpu_name="AMD Ryzen 7",
            cpu_cores=8,
            gpu_type=GPUType.NVIDIA,
            gpu_name="RTX 4070",
            gpu_memory_gb=12.0,
        )
        data = profile.to_dict()
        assert data["gpu_type"] == "nvidia"
        assert data["cpu_name"] == "AMD Ryzen 7"

        restored = HardwareProfile.from_dict(data)
        assert restored.gpu_type == GPUType.NVIDIA
        assert restored.cpu_name == "AMD Ryzen 7"
        assert restored.gpu_memory_gb == 12.0
