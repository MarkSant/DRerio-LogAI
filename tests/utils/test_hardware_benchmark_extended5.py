"""Extended unit tests for utils/hardware_benchmark.py (Part 5)."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import GPUType, HardwareProfile


class TestHardwareBenchmarkExtended5:
    """Test HardwareProfile dataclass attributes and GPUType enum values."""

    def test_hardware_profile_defaults(self):
        profile = HardwareProfile()
        assert profile.cpu_name == ""
        assert profile.cpu_cores == 0
        assert profile.gpu_type == GPUType.NONE
        assert profile.gpu_name == ""
        assert profile.gpu_memory_gb == 0.0
        assert profile.gpu_capabilities == []
        assert profile.openvino_available is False
        assert profile.openvino_devices == []

    def test_hardware_profile_with_intel_gpu(self):
        profile = HardwareProfile(
            cpu_name="Intel Core i7-1185G7",
            cpu_cores=8,
            gpu_type=GPUType.INTEL_IGPU,
            gpu_name="Intel Iris Xe Graphics",
            gpu_memory_gb=4.0,
            gpu_capabilities=["fp16", "int8"],
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
        )
        assert profile.gpu_type == GPUType.INTEL_IGPU
        assert profile.openvino_available is True
        assert len(profile.openvino_devices) == 2

    def test_hardware_profile_nvidia(self):
        profile = HardwareProfile(
            cpu_name="AMD Ryzen 9 5900X",
            cpu_cores=12,
            gpu_type=GPUType.NVIDIA,
            gpu_name="NVIDIA GeForce RTX 3080",
            gpu_memory_gb=10.0,
            gpu_capabilities=["cuda", "tensorrt"],
        )
        assert profile.gpu_type == GPUType.NVIDIA
        assert profile.gpu_memory_gb == 10.0
