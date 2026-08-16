"""Extended unit tests for utils/hardware_benchmark.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

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
    get_optimal_settings,
    load_cached_benchmark,
    print_benchmark_summary,
    save_benchmark_cache,
)


class TestHardwareBenchmarkDataStructures:
    """Test GPUType, HardwareProfile, BenchmarkResult, and SystemBenchmarkResult."""

    def test_gpu_type_enum_values(self):
        assert GPUType.NONE.value == "none"
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.INTEL_NPU.value == "intel_npu"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"
        assert GPUType.UNKNOWN.value == "unknown"

    def test_hardware_profile_roundtrip(self):
        profile = HardwareProfile(
            cpu_name="Intel Core i7",
            cpu_cores=8,
            gpu_type=GPUType.INTEL_ARC,
            gpu_name="Intel Arc A770",
            gpu_memory_gb=16.0,
            gpu_capabilities=["FP16", "INT8"],
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
            cuda_available=False,
            cuda_device_count=0,
            fingerprint="abc123456789",
            total_memory_gb=32.0,
        )
        d = profile.to_dict()
        assert d["gpu_type"] == "intel_arc"
        restored = HardwareProfile.from_dict(d)
        assert restored.cpu_name == "Intel Core i7"
        assert restored.gpu_type == GPUType.INTEL_ARC
        assert restored.gpu_memory_gb == 16.0
        assert restored.fingerprint == "abc123456789"

    def test_benchmark_result_to_dict(self):
        res = BenchmarkResult(
            name="Inference Test",
            device="GPU",
            scenario="isolated",
            avg_ms=10.5,
            min_ms=9.0,
            max_ms=14.0,
            fps=95.2,
        )
        d = res.to_dict()
        assert d["name"] == "Inference Test"
        assert d["avg_ms"] == 10.5
        assert d["fps"] == 95.2

    def test_benchmark_recommendation_roundtrip(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="GPU",
            device_batch="GPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            decode_backend="MSMF",
            recommended_batch_size=4,
            estimated_fps_live=60.0,
            estimated_fps_batch=120.0,
            recommended_inference_size=640,
            recommended_memory_mode="normal",
        )
        d = rec.to_dict()
        restored = BenchmarkRecommendation.from_dict(d)
        assert restored.backend == "openvino"
        assert restored.device_live == "GPU"
        assert restored.recommended_batch_size == 4

    def test_system_benchmark_result_roundtrip(self):
        sys_res = SystemBenchmarkResult(
            benchmark_version="1.0.0",
            benchmark_date="2026-08-16T12:00:00",
            benchmark_duration_s=12.5,
            hardware=HardwareProfile(cpu_name="Test CPU"),
            decode_results={"AUTO": {"fps": 200.0}},
            compute_results={"CPU": {"fps": 50.0}},
            recommendation=BenchmarkRecommendation(
                backend="openvino",
                device_live="CPU",
                device_batch="CPU",
                openvino_hint_live="LATENCY",
                openvino_hint_batch="LATENCY",
                openvino_precision="FP32",
                enable_model_cache=True,
                decode_backend="AUTO",
                recommended_batch_size=1,
                estimated_fps_live=50.0,
                estimated_fps_batch=50.0,
            ),
        )
        d = sys_res.to_dict()
        restored = SystemBenchmarkResult.from_dict(d)
        assert restored.benchmark_version == "1.0.0"
        assert restored.hardware.cpu_name == "Test CPU"
        assert restored.recommendation is not None
        assert restored.recommendation.backend == "openvino"


class TestHardwareBenchmarkLogic:
    """Test memory detection, hardware sizing, and recommendation generators."""

    def test_detect_system_memory_gb_returns_positive_float(self):
        mem = _detect_system_memory_gb()
        assert isinstance(mem, float)
        assert mem >= 0.0

    def test_apply_hardware_sizing_cpu_low_ram(self):
        profile = HardwareProfile(
            gpu_type=GPUType.NONE,
            cuda_available=False,
            total_memory_gb=4.0,
        )
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
            estimated_fps_live=30.0,
            estimated_fps_batch=30.0,
        )
        _apply_hardware_sizing(rec, profile)
        assert rec.recommended_inference_size == 320
        assert rec.recommended_memory_mode == "low"

    def test_apply_hardware_sizing_cpu_medium_ram(self):
        profile = HardwareProfile(
            gpu_type=GPUType.NONE,
            cuda_available=False,
            total_memory_gb=8.0,
        )
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
            estimated_fps_live=30.0,
            estimated_fps_batch=30.0,
        )
        _apply_hardware_sizing(rec, profile)
        assert rec.recommended_inference_size == 416
        assert rec.recommended_memory_mode == "normal"

    def test_get_benchmark_devices(self):
        p_cpu = HardwareProfile(openvino_devices=["CPU"])
        assert _get_benchmark_devices(p_cpu) == ["CPU"]

        p_all = HardwareProfile(openvino_devices=["CPU", "GPU", "NPU"])
        assert _get_benchmark_devices(p_all) == ["CPU", "GPU", "NPU"]

    def test_generate_recommendation_nvidia_cuda(self):
        profile = HardwareProfile(
            gpu_type=GPUType.NVIDIA,
            cuda_available=True,
            openvino_available=False,
        )
        compute = {
            "CUDA": BenchmarkResult("PyTorch CUDA", "CUDA", "isolated", 5.0, 4.0, 6.0, 200.0)
        }
        rec = _generate_recommendation(
            profile=profile,
            compute_results=compute,
            pipeline_live_results={},
            pipeline_batch_results={},
            decode_results={},
        )
        assert rec.backend == "pytorch"
        assert rec.device_live == "cuda"
        assert rec.device_batch == "cuda"
        assert rec.estimated_fps_live == 200.0

    def test_generate_recommendation_openvino_arc(self):
        profile = HardwareProfile(
            gpu_type=GPUType.INTEL_ARC,
            gpu_memory_gb=8.0,
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
            gpu_capabilities=["FP16"],
        )
        live_res = {
            "GPU_LATENCY": BenchmarkResult("Pipe Live", "GPU", "pipeline", 10.0, 8.0, 12.0, 100.0)
        }
        batch_res = {
            "GPU_THROUGHPUT": BenchmarkResult("Pipe Batch", "GPU", "pipeline", 5.0, 4.0, 6.0, 200.0)
        }
        compute_res = {
            "GPU_LATENCY": BenchmarkResult("Inf FP32", "GPU", "isolated", 12.0, 10.0, 15.0, 83.3),
            "GPU_LATENCY_FP16": BenchmarkResult(
                "Inf FP16", "GPU", "isolated", 8.0, 7.0, 10.0, 125.0
            ),
        }
        decode_res = {"MSMF": BenchmarkResult("Decode", "GPU", "isolated", 2.0, 1.5, 3.0, 500.0)}

        rec = _generate_recommendation(
            profile=profile,
            compute_results=compute_res,
            pipeline_live_results=live_res,
            pipeline_batch_results=batch_res,
            decode_results=decode_res,
        )
        assert rec.backend == "openvino"
        assert rec.device_live == "GPU"
        assert rec.device_batch == "GPU"
        assert rec.openvino_hint_batch == "THROUGHPUT"
        assert rec.openvino_precision == "FP16"
        assert rec.decode_backend == "MSMF"
        assert rec.recommended_batch_size == 8

    def test_get_benchmark_cache_path(self):
        p = get_benchmark_cache_path()
        assert isinstance(p, Path)
        assert p.name == "system_benchmark.json"

    def test_save_and_load_cached_benchmark(self, tmp_path: Path):
        cache_file = tmp_path / "system_benchmark.json"
        patch_target = "zebtrack.utils.hardware_benchmark.get_benchmark_cache_path"
        with patch(patch_target, return_value=cache_file):
            # Initially not found
            assert load_cached_benchmark() is None

            # Save
            profile = HardwareProfile(cpu_name="Test CPU", fingerprint="test_fp_123")
            sys_res = SystemBenchmarkResult(
                benchmark_version="1.0.0",
                hardware=profile,
                recommendation=BenchmarkRecommendation(
                    backend="openvino",
                    device_live="CPU",
                    device_batch="CPU",
                    openvino_hint_live="LATENCY",
                    openvino_hint_batch="LATENCY",
                    openvino_precision="FP32",
                    enable_model_cache=True,
                    decode_backend="AUTO",
                    recommended_batch_size=1,
                    estimated_fps_live=30.0,
                    estimated_fps_batch=30.0,
                ),
            )
            save_benchmark_cache(sys_res)
            assert cache_file.exists()

            # Load with matching fingerprint
            patch_detect = "zebtrack.utils.hardware_benchmark.detect_hardware_profile"
            with patch(patch_detect, return_value=profile):
                loaded = load_cached_benchmark()
                assert loaded is not None
                assert loaded.hardware.cpu_name == "Test CPU"

            # Load with mismatched fingerprint
            other_profile = HardwareProfile(cpu_name="Other CPU", fingerprint="different_fp")
            with patch(patch_detect, return_value=other_profile):
                assert load_cached_benchmark() is None

    def test_get_optimal_settings_from_benchmark(self):
        rec = BenchmarkRecommendation(
            backend="openvino",
            device_live="GPU",
            device_batch="GPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            decode_backend="MSMF",
            recommended_batch_size=4,
            estimated_fps_live=80.0,
            estimated_fps_batch=150.0,
            recommended_inference_size=640,
            recommended_memory_mode="normal",
        )
        res = SystemBenchmarkResult(recommendation=rec)
        settings = get_optimal_settings(res)
        assert settings["use_openvino"] is True
        assert settings["openvino"]["device"] == "GPU"
        assert settings["openvino"]["precision"] == "FP16"
        assert settings["decode_backend"] == "MSMF"
        assert settings["batch_size"] == 4

    def test_print_benchmark_summary(self, capsys: pytest.CaptureFixture[str]):
        profile = HardwareProfile(
            cpu_name="Ryzen 7",
            gpu_name="RTX 4070",
            gpu_type=GPUType.NVIDIA,
            gpu_memory_gb=12.0,
            total_memory_gb=32.0,
            openvino_devices=["CPU"],
        )
        rec = BenchmarkRecommendation(
            backend="pytorch",
            device_live="cuda",
            device_batch="cuda",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="LATENCY",
            openvino_precision="FP32",
            enable_model_cache=False,
            decode_backend="AUTO",
            recommended_batch_size=1,
            estimated_fps_live=250.0,
            estimated_fps_batch=250.0,
        )
        res = SystemBenchmarkResult(
            hardware=profile,
            recommendation=rec,
            compute_results={"CUDA": {"avg_ms": 4.0, "fps": 250.0}},
            pipeline_live_results={"CUDA_LATENCY": {"avg_ms": 5.0, "fps": 200.0}},
        )
        print_benchmark_summary(res)
        captured = capsys.readouterr().out
        assert "HARDWARE BENCHMARK SUMMARY" in captured
        assert "Ryzen 7" in captured
        assert "RTX 4070" in captured
        assert "RECOMMENDED CONFIGURATION" in captured
