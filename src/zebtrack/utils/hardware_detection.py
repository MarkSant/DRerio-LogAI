"""
Hardware detection utilities for automatic backend selection.

Detects available GPU hardware and recommends optimal inference backend
(PyTorch with CUDA or OpenVINO).
"""

from functools import lru_cache

import structlog

log = structlog.get_logger()


@lru_cache(maxsize=1)
def is_cuda_available() -> bool:
    """
    Check if NVIDIA CUDA is available for PyTorch.

    Returns:
        bool: True if PyTorch with CUDA is available and functional.
    """
    try:
        import torch

        available = torch.cuda.is_available()
        if available:
            device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Unknown"
            log.info(
                "hardware.cuda.detected",
                available=True,
                device_count=device_count,
                device_name=device_name,
            )
        else:
            log.info("hardware.cuda.not_available")
        return available
    except (ImportError, RuntimeError) as e:
        log.warning("hardware.cuda.check_failed", error=str(e))
        return False


@lru_cache(maxsize=1)
def is_openvino_available() -> bool:
    """
    Check if OpenVINO runtime is available.

    Returns:
        bool: True if OpenVINO can be imported.
    """
    try:
        import openvino as ov  # noqa: F401

        log.info("hardware.openvino.available")
        return True
    except ImportError:
        log.info("hardware.openvino.not_available")
        return False


@lru_cache(maxsize=1)
def get_openvino_devices() -> tuple[str, ...]:
    """
    Get list of available OpenVINO devices.

    Returns:
        tuple[str, ...]: Tuple of device names (e.g., ('CPU', 'GPU.0', 'GPU.1')).
                         Empty tuple if OpenVINO is not available.
    """
    if not is_openvino_available():
        return ()

    try:
        import openvino as ov

        core = ov.Core()
        devices = tuple(core.available_devices)
        log.info("hardware.openvino.devices", devices=devices)
        return devices
    except Exception as e:
        log.warning("hardware.openvino.device_query_failed", error=str(e))
        return ()


@lru_cache(maxsize=1)
def has_intel_gpu() -> bool:
    """
    Check if Intel GPU (including EVO platform) is available for OpenVINO.

    Returns:
        bool: True if Intel GPU device is detected in OpenVINO.
    """
    devices = get_openvino_devices()
    has_gpu = any("GPU" in device for device in devices)
    if has_gpu:
        log.info("hardware.intel_gpu.detected", devices=devices)
    return has_gpu


@lru_cache(maxsize=1)
def has_npu() -> bool:
    """
    Check if Intel NPU (Neural Processing Unit) is available for OpenVINO.

    Requires Intel Core Ultra (Meteor Lake+) with NPU driver installed.

    Returns:
        bool: True if NPU device is detected in OpenVINO.
    """
    devices = get_openvino_devices()
    has_npu_device = any("NPU" in device for device in devices)
    if has_npu_device:
        log.info("hardware.intel_npu.detected", devices=devices)
    return has_npu_device


@lru_cache(maxsize=1)
def recommend_backend() -> str:
    """
    Recommend optimal inference backend based on available hardware.

    Decision logic:
    1. If NVIDIA CUDA is available -> recommend 'pytorch'
    2. Else if OpenVINO is available with NPU -> recommend 'openvino'
    3. Else if OpenVINO is available with GPU (Intel/EVO) -> recommend 'openvino'
    4. Else if OpenVINO is available (CPU only) -> recommend 'openvino'
    5. Else -> recommend 'pytorch' (fallback, will use CPU)

    Returns:
        str: 'pytorch' or 'openvino'
    """
    # Priority 1: NVIDIA CUDA
    if is_cuda_available():
        log.info(
            "hardware.recommendation",
            backend="pytorch",
            reason="NVIDIA CUDA available",
        )
        return "pytorch"

    # Priority 2: OpenVINO with NPU or GPU acceleration
    if is_openvino_available():
        if has_npu():
            log.info(
                "hardware.recommendation",
                backend="openvino",
                reason="OpenVINO with Intel NPU acceleration",
            )
            return "openvino"
        if has_intel_gpu():
            log.info(
                "hardware.recommendation",
                backend="openvino",
                reason="OpenVINO with Intel GPU acceleration",
            )
            return "openvino"
        # OpenVINO available but CPU only
        log.info(
            "hardware.recommendation",
            backend="openvino",
            reason="OpenVINO available (CPU inference)",
        )
        return "openvino"

    # Fallback: PyTorch CPU
    log.info(
        "hardware.recommendation",
        backend="pytorch",
        reason="Fallback to PyTorch CPU (no GPU acceleration)",
    )
    return "pytorch"


@lru_cache(maxsize=1)
def get_hardware_summary() -> dict:
    """
    Get comprehensive hardware detection summary.

    Returns:
        dict: Summary containing:
            - cuda_available: bool
            - openvino_available: bool
            - openvino_devices: tuple[str, ...]
            - has_intel_gpu: bool
            - recommended_backend: str
    """
    summary = {
        "cuda_available": is_cuda_available(),
        "openvino_available": is_openvino_available(),
        "openvino_devices": list(get_openvino_devices()),  # Convert tuple to list for JSON
        "has_intel_gpu": has_intel_gpu(),
        "has_npu": has_npu(),
        "recommended_backend": recommend_backend(),
    }
    log.info("hardware.summary", **summary)
    return summary
