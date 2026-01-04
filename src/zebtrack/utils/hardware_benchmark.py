"""
Adaptive Hardware Benchmark for ZebTrack-AI.

This module provides comprehensive hardware benchmarking that automatically
adapts to the detected hardware (Intel iGPU, Intel Arc, NVIDIA, AMD, CPU-only).

Features:
- Auto-detection of GPU type and capabilities
- Runs only relevant tests per hardware profile
- Generates optimal configuration recommendations
- Caches results to avoid re-running on every startup
- Supports manual re-benchmark via settings or CLI

Integration:
    Called from __main__.py during startup if no cached results exist
    or if hardware has changed since last benchmark.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import structlog

log = structlog.get_logger()


class GPUType(Enum):
    """Type of GPU detected in the system."""

    NONE = "none"
    INTEL_IGPU = "intel_igpu"  # Intel Iris Xe, UHD (integrated)
    INTEL_ARC = "intel_arc"  # Intel Arc (discrete)
    NVIDIA = "nvidia"  # NVIDIA with CUDA
    AMD = "amd"  # AMD with ROCm
    UNKNOWN = "unknown"


@dataclass
class HardwareProfile:
    """Detected hardware profile."""

    cpu_name: str = ""
    cpu_cores: int = 0

    gpu_type: GPUType = GPUType.NONE
    gpu_name: str = ""
    gpu_memory_gb: float = 0.0
    gpu_capabilities: list[str] = field(default_factory=list)

    # OpenVINO specific
    openvino_available: bool = False
    openvino_devices: list[str] = field(default_factory=list)

    # PyTorch/CUDA specific
    cuda_available: bool = False
    cuda_device_count: int = 0

    # System fingerprint (for cache invalidation)
    fingerprint: str = ""

    def to_dict(self) -> dict:
        result = asdict(self)
        result["gpu_type"] = self.gpu_type.value
        return result

    @classmethod
    def from_dict(cls, data: dict) -> HardwareProfile:
        data = data.copy()
        data["gpu_type"] = GPUType(data.get("gpu_type", "none"))
        return cls(**data)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    name: str
    device: str
    scenario: str  # "isolated", "live", "batch"
    avg_ms: float
    min_ms: float
    max_ms: float
    fps: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BenchmarkRecommendation:
    """Recommended configuration based on benchmark results."""

    # Backend selection
    backend: str  # "openvino" or "pytorch"

    # Device selection
    device_live: str  # Device for live camera analysis
    device_batch: str  # Device for pre-recorded video

    # OpenVINO specific
    openvino_hint_live: str  # "LATENCY" or "THROUGHPUT"
    openvino_hint_batch: str
    openvino_precision: str  # "FP32", "FP16", "INT8"
    enable_model_cache: bool

    # Video decode
    decode_backend: str  # "AUTO", "FFMPEG", "MSMF"

    # Batch size for throughput mode
    recommended_batch_size: int

    # Performance estimates
    estimated_fps_live: float
    estimated_fps_batch: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkRecommendation:
        return cls(**data)


@dataclass
class SystemBenchmarkResult:
    """Complete benchmark results for the system."""

    # Metadata
    benchmark_version: str = "1.0.0"
    benchmark_date: str = ""
    benchmark_duration_s: float = 0.0

    # Hardware profile
    hardware: HardwareProfile = field(default_factory=HardwareProfile)

    # Individual benchmark results
    decode_results: dict[str, dict] = field(default_factory=dict)
    compute_results: dict[str, dict] = field(default_factory=dict)
    pipeline_live_results: dict[str, dict] = field(default_factory=dict)
    pipeline_batch_results: dict[str, dict] = field(default_factory=dict)

    # Recommendations
    recommendation: Optional[BenchmarkRecommendation] = None

    def to_dict(self) -> dict:
        result = {
            "benchmark_version": self.benchmark_version,
            "benchmark_date": self.benchmark_date,
            "benchmark_duration_s": self.benchmark_duration_s,
            "hardware": self.hardware.to_dict(),
            "decode_results": self.decode_results,
            "compute_results": self.compute_results,
            "pipeline_live_results": self.pipeline_live_results,
            "pipeline_batch_results": self.pipeline_batch_results,
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> SystemBenchmarkResult:
        result = cls()
        result.benchmark_version = data.get("benchmark_version", "1.0.0")
        result.benchmark_date = data.get("benchmark_date", "")
        result.benchmark_duration_s = data.get("benchmark_duration_s", 0.0)
        result.hardware = HardwareProfile.from_dict(data.get("hardware", {}))
        result.decode_results = data.get("decode_results", {})
        result.compute_results = data.get("compute_results", {})
        result.pipeline_live_results = data.get("pipeline_live_results", {})
        result.pipeline_batch_results = data.get("pipeline_batch_results", {})
        if data.get("recommendation"):
            result.recommendation = BenchmarkRecommendation.from_dict(data["recommendation"])
        return result


def detect_hardware_profile() -> HardwareProfile:
    """
    Detect complete hardware profile of the system.

    Returns:
        HardwareProfile with all detected hardware information.
    """
    profile = HardwareProfile()

    # CPU info
    try:
        import platform

        profile.cpu_name = platform.processor() or "Unknown CPU"
        import os

        profile.cpu_cores = os.cpu_count() or 1
    except Exception:
        pass

    # Check CUDA/PyTorch
    try:
        import torch

        profile.cuda_available = torch.cuda.is_available()
        if profile.cuda_available:
            profile.cuda_device_count = torch.cuda.device_count()
            if profile.cuda_device_count > 0:
                profile.gpu_name = torch.cuda.get_device_name(0)
                profile.gpu_type = GPUType.NVIDIA
                # Get GPU memory
                try:
                    props = torch.cuda.get_device_properties(0)
                    profile.gpu_memory_gb = props.total_memory / (1024**3)
                except Exception:
                    pass
    except ImportError:
        pass

    # Check OpenVINO
    try:
        import openvino as ov

        profile.openvino_available = True
        core = ov.Core()
        profile.openvino_devices = list(core.available_devices)

        # Get CPU name from OpenVINO (more accurate)
        try:
            profile.cpu_name = core.get_property("CPU", "FULL_DEVICE_NAME")
        except Exception:
            pass

        # Check for GPU devices
        for device in profile.openvino_devices:
            if "GPU" in device:
                try:
                    gpu_name = core.get_property(device, "FULL_DEVICE_NAME")
                    profile.gpu_name = gpu_name

                    # Determine GPU type from name
                    gpu_name_lower = gpu_name.lower()
                    if "arc" in gpu_name_lower:
                        profile.gpu_type = GPUType.INTEL_ARC
                    elif "iris" in gpu_name_lower or "uhd" in gpu_name_lower:
                        profile.gpu_type = GPUType.INTEL_IGPU
                    elif "nvidia" in gpu_name_lower or "geforce" in gpu_name_lower:
                        profile.gpu_type = GPUType.NVIDIA
                    elif "amd" in gpu_name_lower or "radeon" in gpu_name_lower:
                        profile.gpu_type = GPUType.AMD
                    else:
                        profile.gpu_type = GPUType.UNKNOWN

                    # Get GPU memory
                    try:
                        mem = core.get_property(device, "GPU_DEVICE_TOTAL_MEM_SIZE")
                        profile.gpu_memory_gb = mem / (1024**3)
                    except Exception:
                        pass

                    # Get capabilities
                    try:
                        caps = core.get_property(device, "OPTIMIZATION_CAPABILITIES")
                        profile.gpu_capabilities = list(caps) if caps else []
                    except Exception:
                        pass

                    break  # Use first GPU found

                except Exception as e:
                    log.warning("hardware.gpu_info_failed", device=device, error=str(e))

    except ImportError:
        pass

    # Generate fingerprint for cache invalidation
    fingerprint_data = f"{profile.cpu_name}|{profile.gpu_name}|{profile.gpu_memory_gb}"
    profile.fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()[:12]

    log.info(
        "hardware.profile_detected",
        cpu=profile.cpu_name,
        gpu_type=profile.gpu_type.value,
        gpu_name=profile.gpu_name,
        gpu_memory_gb=round(profile.gpu_memory_gb, 2),
        openvino_devices=profile.openvino_devices,
        cuda_available=profile.cuda_available,
        fingerprint=profile.fingerprint,
    )

    return profile


def _find_test_video() -> Optional[Path]:
    """Find a test video for benchmarking."""
    search_paths = [
        Path("live_analysis_sessions"),
        Path("tests/fixtures"),
        Path("test_data"),
        Path("resources"),
    ]

    for base in search_paths:
        if base.exists():
            for ext in ["*.mp4", "*.avi", "*.mkv"]:
                videos = list(base.rglob(ext))
                if videos:
                    videos.sort(key=lambda p: p.stat().st_size, reverse=True)
                    return videos[0]
    return None


def _find_openvino_model() -> Optional[Path]:
    """Find an OpenVINO model for benchmarking."""
    cache_dir = Path("openvino_model_cache")
    if not cache_dir.exists():
        return None

    for model_dir in cache_dir.iterdir():
        if model_dir.is_dir():
            xml_files = list(model_dir.glob("*.xml"))
            if xml_files:
                return xml_files[0]
    return None


def _benchmark_video_decode(video_path: Path, num_frames: int = 50) -> dict[str, BenchmarkResult]:
    """Benchmark video decoding with different backends."""
    results = {}

    backends = [
        ("FFMPEG", cv2.CAP_FFMPEG, "Software decode (FFmpeg)"),
        ("MSMF", cv2.CAP_MSMF, "Hardware decode (Media Foundation)"),
        ("AUTO", cv2.CAP_ANY, "Automatic"),
    ]

    for backend_key, backend_id, desc in backends:
        try:
            cap = cv2.VideoCapture(str(video_path), backend_id)
            if not cap.isOpened():
                continue

            times = []
            for _ in range(num_frames):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                start = time.perf_counter()
                ret, frame = cap.read()
                elapsed = (time.perf_counter() - start) * 1000
                if ret:
                    times.append(elapsed)

            cap.release()

            if times:
                avg = sum(times) / len(times)
                results[backend_key] = BenchmarkResult(
                    name=f"Video Decode ({desc})",
                    device="GPU" if "MSMF" in backend_key else "CPU",
                    scenario="isolated",
                    avg_ms=avg,
                    min_ms=min(times),
                    max_ms=max(times),
                    fps=1000 / avg,
                )
        except Exception as e:
            log.warning("benchmark.decode_failed", backend=backend_key, error=str(e))

    return results


def _benchmark_openvino_inference(
    model_path: Path,
    sample_frame: np.ndarray,
    profile: HardwareProfile,
    num_iterations: int = 30,
) -> dict[str, BenchmarkResult]:
    """Benchmark OpenVINO inference on available devices."""
    results = {}

    try:
        import openvino as ov

        core = ov.Core()
        model = core.read_model(str(model_path))
    except Exception as e:
        log.error("benchmark.openvino_load_failed", error=str(e))
        return results

    # Prepare input
    input_size = 640
    resized = cv2.resize(sample_frame, (input_size, input_size))
    blob = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
    blob = np.expand_dims(blob, 0)

    # Determine which devices and hints to test based on GPU type
    test_configs = []

    # Always test CPU
    test_configs.append(("CPU", "LATENCY", "CPU_LATENCY"))

    # GPU tests depend on GPU type
    if "GPU" in profile.openvino_devices:
        test_configs.append(("GPU", "LATENCY", "GPU_LATENCY"))

        # Only test THROUGHPUT on discrete GPUs (Arc, NVIDIA)
        if profile.gpu_type in [GPUType.INTEL_ARC, GPUType.NVIDIA]:
            test_configs.append(("GPU", "THROUGHPUT", "GPU_THROUGHPUT"))

        # Test FP16 if supported
        if "FP16" in profile.gpu_capabilities:
            test_configs.append(("GPU", "LATENCY", "GPU_LATENCY_FP16"))

    for device, hint, key in test_configs:
        try:
            config = {"PERFORMANCE_HINT": hint}
            if device == "GPU":
                config["CACHE_DIR"] = "openvino_model_cache/compiled_cache"
                if "FP16" in key:
                    config["INFERENCE_PRECISION_HINT"] = "f16"

            compiled = core.compile_model(model, device, config)
            infer_request = compiled.create_infer_request()

            # Warmup
            for _ in range(5):
                infer_request.infer({0: blob})

            # Benchmark
            times = []
            for _ in range(num_iterations):
                start = time.perf_counter()
                infer_request.infer({0: blob})
                times.append((time.perf_counter() - start) * 1000)

            avg = sum(times) / len(times)
            results[key] = BenchmarkResult(
                name=f"Inference ({device} {hint})",
                device=device,
                scenario="isolated",
                avg_ms=avg,
                min_ms=min(times),
                max_ms=max(times),
                fps=1000 / avg,
            )

        except Exception as e:
            log.warning("benchmark.inference_failed", config=key, error=str(e))

    return results


def _benchmark_pytorch_cuda(
    sample_frame: np.ndarray,
    num_iterations: int = 30,
) -> dict[str, BenchmarkResult]:
    """Benchmark PyTorch CUDA inference (for NVIDIA GPUs)."""
    results = {}

    try:
        import torch

        if not torch.cuda.is_available():
            return results

        # Simple convolution benchmark as proxy for YOLO inference
        device = torch.device("cuda")

        # Create a simple model
        model = torch.nn.Sequential(
            torch.nn.Conv2d(3, 64, 3, padding=1),
            torch.nn.ReLU(),
            torch.nn.Conv2d(64, 64, 3, padding=1),
            torch.nn.ReLU(),
            torch.nn.AdaptiveAvgPool2d(1),
        ).to(device)
        model.eval()

        # Prepare input
        input_size = 640
        resized = cv2.resize(sample_frame, (input_size, input_size))
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float().unsqueeze(0).to(device) / 255.0

        # Warmup
        with torch.no_grad():
            for _ in range(10):
                _ = model(tensor)
        torch.cuda.synchronize()

        # Benchmark
        times = []
        with torch.no_grad():
            for _ in range(num_iterations):
                torch.cuda.synchronize()
                start = time.perf_counter()
                _ = model(tensor)
                torch.cuda.synchronize()
                times.append((time.perf_counter() - start) * 1000)

        avg = sum(times) / len(times)
        results["CUDA"] = BenchmarkResult(
            name="PyTorch CUDA",
            device="CUDA",
            scenario="isolated",
            avg_ms=avg,
            min_ms=min(times),
            max_ms=max(times),
            fps=1000 / avg,
        )

    except Exception as e:
        log.warning("benchmark.pytorch_cuda_failed", error=str(e))

    return results


def _benchmark_pipeline_complete(
    video_path: Path,
    model_path: Path,
    device: str,
    hint: str,
    num_frames: int = 30,
) -> Optional[BenchmarkResult]:
    """Benchmark complete pipeline: decode → preprocess → inference → postprocess."""
    try:
        import openvino as ov

        core = ov.Core()
        model = core.read_model(str(model_path))

        config = {"PERFORMANCE_HINT": hint}
        if device == "GPU":
            config["CACHE_DIR"] = "openvino_model_cache/compiled_cache"

        compiled = core.compile_model(model, device, config)
        infer_request = compiled.create_infer_request()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        input_size = 640

        # Warmup
        for _ in range(3):
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            resized = cv2.resize(frame, (input_size, input_size))
            blob = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
            blob = np.expand_dims(blob, 0)
            infer_request.infer({0: blob})

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        # Benchmark
        times = []
        for _ in range(num_frames):
            start = time.perf_counter()

            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()

            resized = cv2.resize(frame, (input_size, input_size))
            blob = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
            blob = np.expand_dims(blob, 0)

            infer_request.infer({0: blob})
            output = infer_request.get_output_tensor(0).data.copy()

            times.append((time.perf_counter() - start) * 1000)

        cap.release()

        avg = sum(times) / len(times)
        return BenchmarkResult(
            name=f"Pipeline ({device} {hint})",
            device=device,
            scenario="pipeline",
            avg_ms=avg,
            min_ms=min(times),
            max_ms=max(times),
            fps=1000 / avg,
        )

    except Exception as e:
        log.warning("benchmark.pipeline_failed", device=device, hint=hint, error=str(e))
        return None


def _generate_recommendation(
    profile: HardwareProfile,
    compute_results: dict[str, BenchmarkResult],
    pipeline_live_results: dict[str, BenchmarkResult],
    pipeline_batch_results: dict[str, BenchmarkResult],
    decode_results: dict[str, BenchmarkResult],
) -> BenchmarkRecommendation:
    """Generate optimal configuration recommendation based on benchmark results."""

    # Defaults
    recommendation = BenchmarkRecommendation(
        backend="openvino" if profile.openvino_available else "pytorch",
        device_live="CPU",
        device_batch="CPU",
        openvino_hint_live="LATENCY",
        openvino_hint_batch="LATENCY",
        openvino_precision="FP32",
        enable_model_cache=True,
        decode_backend="AUTO",
        recommended_batch_size=1,
        estimated_fps_live=0.0,
        estimated_fps_batch=0.0,
    )

    # For NVIDIA, prefer PyTorch CUDA
    if profile.gpu_type == GPUType.NVIDIA and profile.cuda_available:
        recommendation.backend = "pytorch"
        recommendation.device_live = "cuda"
        recommendation.device_batch = "cuda"
        if "CUDA" in compute_results:
            recommendation.estimated_fps_live = compute_results["CUDA"].fps
            recommendation.estimated_fps_batch = compute_results["CUDA"].fps
        return recommendation

    # For OpenVINO-based systems
    if profile.openvino_available:
        # Find best device for live (prioritize latency)
        best_live_fps = 0.0
        for key, result in pipeline_live_results.items():
            if result.fps > best_live_fps:
                best_live_fps = result.fps
                recommendation.device_live = result.device
                recommendation.estimated_fps_live = result.fps

        # Find best config for batch
        best_batch_fps = 0.0
        best_batch_hint = "LATENCY"
        for key, result in pipeline_batch_results.items():
            if result.fps > best_batch_fps:
                best_batch_fps = result.fps
                recommendation.device_batch = result.device
                recommendation.estimated_fps_batch = result.fps
                # Extract hint from key
                if "THROUGHPUT" in key:
                    best_batch_hint = "THROUGHPUT"
                else:
                    best_batch_hint = "LATENCY"

        recommendation.openvino_hint_batch = best_batch_hint

        # Check if FP16 is better
        if "GPU_LATENCY_FP16" in compute_results and "GPU_LATENCY" in compute_results:
            if compute_results["GPU_LATENCY_FP16"].fps > compute_results["GPU_LATENCY"].fps:
                recommendation.openvino_precision = "FP16"

        # Determine batch size based on GPU type and memory
        if profile.gpu_type == GPUType.INTEL_ARC:
            recommendation.recommended_batch_size = min(8, int(profile.gpu_memory_gb * 2))
        elif profile.gpu_type == GPUType.INTEL_IGPU:
            recommendation.recommended_batch_size = 1  # Shared memory, avoid batching
        else:
            recommendation.recommended_batch_size = min(4, int(profile.gpu_memory_gb))

    # Find best decode backend
    best_decode_fps = 0.0
    for key, result in decode_results.items():
        if result.fps > best_decode_fps:
            best_decode_fps = result.fps
            recommendation.decode_backend = key

    return recommendation


def run_adaptive_benchmark(
    quick_mode: bool = False,
    progress_callback: Optional[callable] = None,
) -> SystemBenchmarkResult:
    """
    Run adaptive benchmark based on detected hardware.

    Args:
        quick_mode: If True, run fewer iterations for faster results.
        progress_callback: Optional callback(step: int, total: int, message: str)

    Returns:
        SystemBenchmarkResult with all benchmark data and recommendations.
    """
    from datetime import datetime

    start_time = time.perf_counter()

    result = SystemBenchmarkResult()
    result.benchmark_date = datetime.now().isoformat()

    num_iterations = 15 if quick_mode else 30
    num_frames = 25 if quick_mode else 50

    def report_progress(step: int, total: int, message: str):
        log.info("benchmark.progress", step=step, total=total, message=message)
        if progress_callback:
            progress_callback(step, total, message)

    # Step 1: Detect hardware
    report_progress(1, 6, "Detecting hardware...")
    profile = detect_hardware_profile()
    result.hardware = profile

    # Find test resources
    video_path = _find_test_video()
    model_path = _find_openvino_model()

    sample_frame = None
    if video_path:
        cap = cv2.VideoCapture(str(video_path))
        ret, sample_frame = cap.read()
        cap.release()

    if sample_frame is None:
        sample_frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

    # Step 2: Video decode benchmark
    report_progress(2, 6, "Testing video decode...")
    decode_results = {}
    if video_path:
        decode_results = _benchmark_video_decode(video_path, num_frames=num_frames)
        result.decode_results = {k: v.to_dict() for k, v in decode_results.items()}

    # Step 3: Compute/Inference benchmark
    report_progress(3, 6, "Testing inference performance...")
    compute_results = {}

    if model_path and profile.openvino_available:
        compute_results = _benchmark_openvino_inference(
            model_path, sample_frame, profile, num_iterations
        )

    if profile.cuda_available:
        cuda_results = _benchmark_pytorch_cuda(sample_frame, num_iterations)
        compute_results.update(cuda_results)

    result.compute_results = {k: v.to_dict() for k, v in compute_results.items()}

    # Step 4: Pipeline Live benchmark
    report_progress(4, 6, "Testing live camera pipeline...")
    pipeline_live_results = {}
    if video_path and model_path and profile.openvino_available:
        for device in ["CPU", "GPU"]:
            if device == "GPU" and "GPU" not in profile.openvino_devices:
                continue
            result_bench = _benchmark_pipeline_complete(
                video_path, model_path, device, "LATENCY", num_frames
            )
            if result_bench:
                pipeline_live_results[f"{device}_LATENCY"] = result_bench

    result.pipeline_live_results = {k: v.to_dict() for k, v in pipeline_live_results.items()}

    # Step 5: Pipeline Batch benchmark
    report_progress(5, 6, "Testing batch processing pipeline...")
    pipeline_batch_results = {}
    if video_path and model_path and profile.openvino_available:
        for device in ["CPU", "GPU"]:
            if device == "GPU" and "GPU" not in profile.openvino_devices:
                continue

            hints_to_test = ["LATENCY"]
            # Only test THROUGHPUT on discrete GPUs
            if device == "GPU" and profile.gpu_type in [GPUType.INTEL_ARC, GPUType.NVIDIA]:
                hints_to_test.append("THROUGHPUT")

            for hint in hints_to_test:
                result_bench = _benchmark_pipeline_complete(
                    video_path, model_path, device, hint, num_frames
                )
                if result_bench:
                    pipeline_batch_results[f"{device}_{hint}"] = result_bench

    result.pipeline_batch_results = {k: v.to_dict() for k, v in pipeline_batch_results.items()}

    # Step 6: Generate recommendations
    report_progress(6, 6, "Generating recommendations...")
    result.recommendation = _generate_recommendation(
        profile,
        compute_results,
        pipeline_live_results,
        pipeline_batch_results,
        decode_results,
    )

    result.benchmark_duration_s = time.perf_counter() - start_time

    log.info(
        "benchmark.completed",
        duration_s=round(result.benchmark_duration_s, 1),
        recommended_backend=result.recommendation.backend,
        recommended_device_live=result.recommendation.device_live,
        estimated_fps_live=round(result.recommendation.estimated_fps_live, 1),
    )

    return result


def get_benchmark_cache_path() -> Path:
    """Get path to cached benchmark results."""
    return Path("openvino_model_cache") / "system_benchmark.json"


def load_cached_benchmark() -> Optional[SystemBenchmarkResult]:
    """Load benchmark results from cache if valid."""
    cache_path = get_benchmark_cache_path()

    if not cache_path.exists():
        log.info("benchmark.cache_not_found")
        return None

    try:
        with open(cache_path) as f:
            data = json.load(f)

        result = SystemBenchmarkResult.from_dict(data)

        # Verify hardware fingerprint
        current_profile = detect_hardware_profile()
        if result.hardware.fingerprint != current_profile.fingerprint:
            log.info(
                "benchmark.cache_invalid",
                reason="hardware_changed",
                cached_fingerprint=result.hardware.fingerprint,
                current_fingerprint=current_profile.fingerprint,
            )
            return None

        log.info("benchmark.cache_loaded", date=result.benchmark_date)
        return result

    except Exception as e:
        log.warning("benchmark.cache_load_failed", error=str(e))
        return None


def save_benchmark_cache(result: SystemBenchmarkResult) -> None:
    """Save benchmark results to cache."""
    cache_path = get_benchmark_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(cache_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        log.info("benchmark.cache_saved", path=str(cache_path))
    except Exception as e:
        log.error("benchmark.cache_save_failed", error=str(e))


def get_or_run_benchmark(
    force_rerun: bool = False,
    quick_mode: bool = False,
    progress_callback: Optional[callable] = None,
) -> SystemBenchmarkResult:
    """
    Get benchmark results from cache or run new benchmark if needed.

    Args:
        force_rerun: If True, ignore cache and run new benchmark.
        quick_mode: If True, run faster benchmark with fewer iterations.
        progress_callback: Optional callback for progress updates.

    Returns:
        SystemBenchmarkResult with recommendations.
    """
    if not force_rerun:
        cached = load_cached_benchmark()
        if cached:
            return cached

    result = run_adaptive_benchmark(quick_mode=quick_mode, progress_callback=progress_callback)
    save_benchmark_cache(result)

    return result


def get_optimal_settings(
    benchmark_result: Optional[SystemBenchmarkResult] = None,
) -> dict[str, Any]:
    """
    Get optimal settings dictionary based on benchmark results.

    This returns settings that can be used to configure the application.

    Args:
        benchmark_result: Optional pre-loaded benchmark result.

    Returns:
        Dictionary with optimal settings.
    """
    if benchmark_result is None:
        benchmark_result = get_or_run_benchmark()

    rec = benchmark_result.recommendation
    if rec is None:
        return {}

    return {
        "use_openvino": rec.backend == "openvino",
        "openvino_device": rec.device_live,
        "openvino_device_batch": rec.device_batch,
        "openvino_hint_live": rec.openvino_hint_live,
        "openvino_hint_batch": rec.openvino_hint_batch,
        "openvino_precision": rec.openvino_precision,
        "enable_model_cache": rec.enable_model_cache,
        "decode_backend": rec.decode_backend,
        "batch_size": rec.recommended_batch_size,
        "estimated_fps_live": rec.estimated_fps_live,
        "estimated_fps_batch": rec.estimated_fps_batch,
    }


def print_benchmark_summary(result: SystemBenchmarkResult) -> None:
    """Print human-readable benchmark summary."""
    print("\n" + "=" * 70)
    print("HARDWARE BENCHMARK SUMMARY")
    print("=" * 70)

    hw = result.hardware
    print(f"\nCPU: {hw.cpu_name}")
    print(f"GPU: {hw.gpu_name} ({hw.gpu_type.value})")
    print(f"GPU Memory: {hw.gpu_memory_gb:.2f} GB")
    print(f"OpenVINO Devices: {hw.openvino_devices}")

    if result.compute_results:
        print("\n--- Inference Performance ---")
        for key, data in result.compute_results.items():
            print(f"  {key}: {data['avg_ms']:.1f}ms = {data['fps']:.1f} FPS")

    if result.pipeline_live_results:
        print("\n--- Live Camera Pipeline ---")
        for key, data in result.pipeline_live_results.items():
            print(f"  {key}: {data['avg_ms']:.1f}ms = {data['fps']:.1f} FPS")

    rec = result.recommendation
    if rec:
        print("\n" + "=" * 70)
        print("RECOMMENDED CONFIGURATION")
        print("=" * 70)
        print(f"  Backend: {rec.backend}")
        print(f"  Device (Live): {rec.device_live} with {rec.openvino_hint_live}")
        print(f"  Device (Batch): {rec.device_batch} with {rec.openvino_hint_batch}")
        print(f"  Precision: {rec.openvino_precision}")
        print(f"  Model Cache: {'Enabled' if rec.enable_model_cache else 'Disabled'}")
        print(f"  Estimated FPS (Live): {rec.estimated_fps_live:.1f}")
        print(f"  Estimated FPS (Batch): {rec.estimated_fps_batch:.1f}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # CLI mode for testing
    import argparse

    parser = argparse.ArgumentParser(description="ZebTrack-AI Hardware Benchmark")
    parser.add_argument("--force", action="store_true", help="Force re-run benchmark")
    parser.add_argument("--quick", action="store_true", help="Quick mode with fewer iterations")
    args = parser.parse_args()

    result = get_or_run_benchmark(force_rerun=args.force, quick_mode=args.quick)
    print_benchmark_summary(result)
