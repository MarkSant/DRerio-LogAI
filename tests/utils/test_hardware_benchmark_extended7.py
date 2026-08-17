"""Extended unit tests for utils/hardware_benchmark.py (Part 7)."""

from __future__ import annotations

from zebtrack.utils.hardware_benchmark import GPUType, HardwareProfile


class TestHardwareBenchmarkExtended7:
    """Test HardwareProfile GPU types and default capability lists."""

    def test_hardware_profile_openvino_and_cuda_defaults(self):
        hp = HardwareProfile()
        assert hp.gpu_type == GPUType.NONE
        assert hp.openvino_available is False
        assert hp.openvino_devices == []
        assert hp.cuda_available is False
        assert hp.cuda_device_count == 0

    def test_gpu_type_enum_values(self):
        assert GPUType.INTEL_IGPU.value == "intel_igpu"
        assert GPUType.INTEL_ARC.value == "intel_arc"
        assert GPUType.INTEL_NPU.value == "intel_npu"
        assert GPUType.NVIDIA.value == "nvidia"
        assert GPUType.AMD.value == "amd"
        assert GPUType.UNKNOWN.value == "unknown"
        assert GPUType.NONE.value == "none"
