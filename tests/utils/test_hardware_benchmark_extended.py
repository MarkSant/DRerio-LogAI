"""
Extended unit tests for Adaptive Hardware Benchmark.
"""

from __future__ import annotations

from dataclasses import asdict

from zebtrack.utils.hardware_benchmark import (
    GPUType,
    HardwareProfile,
)


class TestHardwareBenchmarkExtended:
    """Test GPUType enum and HardwareProfile dataclass."""

    def test_gpu_type_enum(self):
        assert GPUType.NONE.value == "none"
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.INTEL_NPU.value == "intel_npu"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"
        assert GPUType.UNKNOWN.value == "unknown"

    def test_hardware_profile_defaults_and_asdict(self):
        profile = HardwareProfile(
            cpu_name="Intel i7",
            cpu_cores=8,
            gpu_type=GPUType.INTEL_IGPU,
            gpu_name="Intel Iris Xe",
            gpu_memory_gb=2.0,
        )
        assert profile.cpu_name == "Intel i7"
        assert profile.gpu_type == GPUType.INTEL_IGPU
        d = asdict(profile)
        assert d["cpu_cores"] == 8
        assert d["gpu_name"] == "Intel Iris Xe"
