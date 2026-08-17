"""Extended unit tests for utils/hardware_benchmark.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    BenchmarkResult,
    GPUType,
    HardwareProfile,
    SystemBenchmarkResult,
    _apply_hardware_sizing,
    _detect_system_memory_gb,
    _generate_recommendation,
    _get_benchmark_devices,
    get_benchmark_cache_path,
    load_cached_benchmark,
    save_benchmark_cache,
)


class TestHardwareBenchmarkDataClasses:
    """Test data structures and serialization for hardware benchmark."""

    def test_gpu_type_enum(self):
        assert GPUType.NONE.value == "none"
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"

    def test_hardware_profile_roundtrip(self):
        profile = HardwareProfile(
            cpu_name="Intel Core i7",
            cpu_cores=8,
            gpu_type=GPUType.NVIDIA,
            gpu_name="RTX 4060",
            gpu_memory_gb=8.0,
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
            cuda_available=True,
            total_memory_gb=16.0,
        )
        d = profile.to_dict()
        assert d["gpu_type"] == "nvidia"
        assert d["cpu_cores"] == 8

        restored = HardwareProfile.from_dict(d)
        assert restored.gpu_type == GPUType.NVIDIA
        assert restored.gpu_name == "RTX 4060"
        assert restored.total_memory_gb == 16.0

    def test_benchmark_result_to_dict(self):
        res = BenchmarkResult(
            name="test_det",
            device="CPU",
            scenario="live",
            avg_ms=12.5,
            min_ms=10.0,
            max_ms=15.0,
            fps=80.0,
        )
        d = res.to_dict()
        assert d["name"] == "test_det"
        assert d["fps"] == 80.0

    def test_benchmark_recommendation_roundtrip(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="GPU",
            device_batch="AUTO",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            decode_backend="FFMPEG",
            recommended_batch_size=4,
            estimated_fps_live=60.0,
            estimated_fps_batch=120.0,
            recommended_inference_size=640,
            recommended_memory_mode="normal",
        )
        d = rec.to_dict()
        assert d["backend"] == "openvino"
        assert d["recommended_batch_size"] == 4

        restored = BenchmarkRecommendation.from_dict(d)
        assert restored.backend == "openvino"
        assert restored.estimated_fps_live == 60.0

    def test_system_benchmark_result_roundtrip(self):
        sys_res = SystemBenchmarkResult(
            benchmark_version="1.0.0",
            benchmark_date="2026-08-16",
            benchmark_duration_s=5.2,
            hardware=HardwareProfile(cpu_name="Ryzen 7", gpu_type=GPUType.AMD),
            recommendation=BenchmarkRecommendation(
                backend="pytorch",
                device_live="cuda",
                device_batch="cuda",
                openvino_hint_live="LATENCY",
                openvino_hint_batch="THROUGHPUT",
                openvino_precision="FP32",
                enable_model_cache=False,
                decode_backend="AUTO",
                recommended_batch_size=2,
                estimated_fps_live=45.0,
                estimated_fps_batch=90.0,
            ),
        )
        d = sys_res.to_dict()
        assert d["hardware"]["cpu_name"] == "Ryzen 7"
        assert d["recommendation"]["backend"] == "pytorch"

        restored = SystemBenchmarkResult.from_dict(d)
        assert restored.hardware.cpu_name == "Ryzen 7"
        assert restored.recommendation is not None
        assert restored.recommendation.backend == "pytorch"

    def test_detect_system_memory(self):
        mem = _detect_system_memory_gb()
        assert isinstance(mem, float)
        assert mem >= 0.0

    def test_get_benchmark_cache_path(self):
        p = get_benchmark_cache_path()
        assert "openvino_model_cache" in str(p)
        assert p.name == "system_benchmark.json"

    def test_get_benchmark_devices(self):
        profile = HardwareProfile(openvino_devices=["CPU", "GPU", "NPU"])
        devs = _get_benchmark_devices(profile)
        assert "CPU" in devs
        assert "GPU" in devs
        assert "NPU" in devs

    def test_apply_hardware_sizing_low_ram(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="CPU",
            device_batch="CPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="LATENCY",
            openvino_precision="FP32",
            enable_model_cache=True,
            decode_backend="AUTO",
            recommended_batch_size=1,
            estimated_fps_live=10.0,
            estimated_fps_batch=10.0,
        )
        profile = HardwareProfile(
            gpu_type=GPUType.NONE,
            cuda_available=False,
            total_memory_gb=4.0,
        )
        _apply_hardware_sizing(rec, profile)
        assert rec.recommended_inference_size == 320
        assert rec.recommended_memory_mode == "low"

    def test_generate_recommendation_nvidia_cuda(self):
        profile = HardwareProfile(
            gpu_type=GPUType.NVIDIA,
            cuda_available=True,
            total_memory_gb=16.0,
        )
        compute_results = {
            "CUDA": BenchmarkResult(
                name="CUDA",
                device="cuda",
                scenario="isolated",
                avg_ms=10.0,
                min_ms=9.0,
                max_ms=12.0,
                fps=100.0,
            )
        }
        rec = _generate_recommendation(
            profile=profile,
            compute_results=compute_results,
            pipeline_live_results={},
            pipeline_batch_results={},
            decode_results={},
        )
        assert rec.backend == "pytorch"
        assert rec.device_live == "cuda"
        assert rec.estimated_fps_live == 100.0

    def test_save_and_load_benchmark_cache(self, tmp_path: Path):
        fake_cache_path = tmp_path / "system_benchmark.json"
        profile = HardwareProfile(cpu_name="Test CPU", gpu_type=GPUType.NONE)
        sys_res = SystemBenchmarkResult(
            benchmark_version="1.0",
            benchmark_date="2026-08-16",
            hardware=profile,
        )

        with (
            patch(
                "zebtrack.utils.hardware_benchmark.get_benchmark_cache_path",
                return_value=fake_cache_path,
            ),
            patch(
                "zebtrack.utils.hardware_benchmark.detect_hardware_profile",
                return_value=profile,
            ),
        ):
            save_benchmark_cache(sys_res)
            assert fake_cache_path.exists()

            loaded = load_cached_benchmark()
            assert loaded is not None
            assert loaded.hardware.cpu_name == "Test CPU"

    def test_load_cached_benchmark_missing_file(self, tmp_path: Path):
        missing_path = tmp_path / "nonexistent.json"
        with patch(
            "zebtrack.utils.hardware_benchmark.get_benchmark_cache_path",
            return_value=missing_path,
        ):
            loaded = load_cached_benchmark()
            assert loaded is None
