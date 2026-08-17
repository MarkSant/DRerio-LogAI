"""Extended unit tests for utils/hardware_benchmark.py."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    BenchmarkResult,
    GPUType,
    HardwareProfile,
)


class TestHardwareBenchmarkExtended2:
    """Test GPUType enums, HardwareProfile serialization, and Benchmark dataclasses."""

    def test_gpu_type_enums(self):
        assert GPUType.NONE.value == "none"
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.INTEL_NPU.value == "intel_npu"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"
        assert GPUType.UNKNOWN.value == "unknown"

    def test_hardware_profile_to_dict_and_from_dict(self):
        prof = HardwareProfile(
            cpu_name="Intel Core i7",
            cpu_cores=8,
            gpu_type=GPUType.INTEL_ARC,
            gpu_name="Intel Arc A770",
            gpu_memory_gb=16.0,
            openvino_available=True,
            total_memory_gb=32.0,
        )

        d = prof.to_dict()
        assert d["cpu_name"] == "Intel Core i7"
        assert d["cpu_cores"] == 8
        assert d["gpu_type"] == "intel_arc"

        restored = HardwareProfile.from_dict(d)
        assert restored.cpu_name == "Intel Core i7"
        assert restored.gpu_type == GPUType.INTEL_ARC
        assert restored.openvino_available is True

    def test_benchmark_result_dataclass(self):
        res = BenchmarkResult(
            name="YOLOv8s",
            device="GPU",
            scenario="live",
            avg_ms=12.5,
            min_ms=10.0,
            max_ms=15.0,
            fps=80.0,
        )

        d = res.to_dict()
        assert d["name"] == "YOLOv8s"
        assert d["device"] == "GPU"
        assert d["fps"] == 80.0

    def test_benchmark_recommendation_dataclass(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="GPU",
            device_batch="CPU",
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
        assert d["openvino_precision"] == "FP16"

        restored = BenchmarkRecommendation.from_dict(d)
        assert restored.backend == "openvino"
        assert restored.enable_model_cache is True
