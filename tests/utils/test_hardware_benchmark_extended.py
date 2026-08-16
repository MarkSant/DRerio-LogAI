"""
Extended unit tests for Adaptive Hardware Benchmark in utils/hardware_benchmark.py.
"""

from __future__ import annotations

from unittest.mock import patch

from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    BenchmarkResult,
    GPUType,
    HardwareProfile,
    SystemBenchmarkResult,
    _detect_system_memory_gb,
    detect_hardware_profile,
    load_cached_benchmark,
    save_benchmark_cache,
)


class TestHardwareBenchmarkExtended:
    """Test GPUType enum, hardware profiles, benchmark DTOs, and caching logic."""

    def test_gpu_type_enum(self):
        assert GPUType.NONE.value == "none"
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.INTEL_NPU.value == "intel_npu"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"
        assert GPUType.UNKNOWN.value == "unknown"

    def test_hardware_profile_serialization(self):
        profile = HardwareProfile(
            cpu_name="Intel i7",
            cpu_cores=8,
            gpu_type=GPUType.INTEL_IGPU,
            gpu_name="Intel Iris Xe",
            gpu_memory_gb=2.0,
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
            cuda_available=False,
            fingerprint="abc123def456",
            total_memory_gb=16.0,
        )
        d = profile.to_dict()
        assert d["gpu_type"] == "intel_igpu"
        assert d["fingerprint"] == "abc123def456"

        restored = HardwareProfile.from_dict(d)
        assert restored.gpu_type == GPUType.INTEL_IGPU
        assert restored.cpu_name == "Intel i7"
        assert restored.openvino_devices == ["CPU", "GPU"]

    def test_benchmark_result_serialization(self):
        res = BenchmarkResult(
            name="Inference_GPU",
            device="GPU",
            scenario="live",
            avg_ms=12.5,
            min_ms=10.0,
            max_ms=15.0,
            fps=80.0,
        )
        d = res.to_dict()
        assert d["name"] == "Inference_GPU"
        assert d["fps"] == 80.0

    def test_benchmark_recommendation_serialization(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="GPU",
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
        assert d["estimated_fps_batch"] == 120.0

        restored = BenchmarkRecommendation.from_dict(d)
        assert restored.backend == "openvino"
        assert restored.decode_backend == "FFMPEG"

    def test_system_benchmark_result_serialization(self):
        sys_res = SystemBenchmarkResult(
            benchmark_version="1.0.0",
            benchmark_date="2026-08-16",
            benchmark_duration_s=5.2,
            hardware=HardwareProfile(cpu_name="Test CPU"),
            decode_results={"FFMPEG": {"fps": 200.0}},
            compute_results={"GPU": {"fps": 85.0}},
        )
        d = sys_res.to_dict()
        assert d["benchmark_version"] == "1.0.0"
        assert d["decode_results"]["FFMPEG"]["fps"] == 200.0

        restored = SystemBenchmarkResult.from_dict(d)
        assert restored.benchmark_version == "1.0.0"
        assert restored.hardware.cpu_name == "Test CPU"

    def test_detect_system_memory_gb(self):
        gb = _detect_system_memory_gb()
        assert isinstance(gb, float)
        assert gb >= 0.0

    def test_detect_hardware_profile(self):
        profile = detect_hardware_profile()
        assert isinstance(profile, HardwareProfile)
        assert profile.cpu_cores >= 1
        assert len(profile.fingerprint) > 0

    def test_cache_save_and_load(self, tmp_path):
        cache_file = tmp_path / "system_benchmark.json"
        target = "zebtrack.utils.hardware_benchmark.get_benchmark_cache_path"
        mock_profile = HardwareProfile(
            cpu_name="Test CPU",
            cpu_cores=4,
            fingerprint="fixed1234567",
        )
        with (
            patch(target, return_value=cache_file),
            patch(
                "zebtrack.utils.hardware_benchmark.detect_hardware_profile",
                return_value=mock_profile,
            ),
        ):
            sys_res = SystemBenchmarkResult(
                benchmark_version="1.0.0",
                benchmark_date="2026-08-16",
                hardware=mock_profile,
            )
            save_benchmark_cache(sys_res)
            assert cache_file.exists()

            loaded = load_cached_benchmark()
            assert loaded is not None
            assert loaded.hardware.fingerprint == "fixed1234567"

            # Invalidate cache when hardware fingerprint differs
            mismatched_profile = HardwareProfile(
                cpu_name="New CPU",
                cpu_cores=8,
                fingerprint="different999",
            )
            with patch(
                "zebtrack.utils.hardware_benchmark.detect_hardware_profile",
                return_value=mismatched_profile,
            ):
                assert load_cached_benchmark() is None

    def test_load_cached_benchmark_missing_or_corrupt(self, tmp_path):
        missing_file = tmp_path / "missing.json"
        target = "zebtrack.utils.hardware_benchmark.get_benchmark_cache_path"
        with patch(target, return_value=missing_file):
            assert load_cached_benchmark() is None

        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("invalid json")
        with patch(target, return_value=corrupt_file):
            assert load_cached_benchmark() is None
