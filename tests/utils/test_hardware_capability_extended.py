"""Extended unit tests for utils/hardware_capability.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.utils.hardware_capability import (
    HardwareCapabilityDetector,
    HardwareCapabilityReport,
    MultiAquariumCapability,
)


class TestHardwareCapabilityExtended:
    """Test MultiAquariumCapability enum, Report string formatting, and Detector tiers."""

    def test_multi_aquarium_capability_enum(self):
        assert MultiAquariumCapability.EXCELLENT.value == "excellent"
        assert MultiAquariumCapability.GOOD.value == "good"
        assert MultiAquariumCapability.MODERATE.value == "moderate"
        assert MultiAquariumCapability.LIMITED.value == "limited"
        assert MultiAquariumCapability.INSUFFICIENT.value == "insufficient"

    def test_hardware_capability_report_str_with_gpu(self):
        rep = HardwareCapabilityReport(
            capability=MultiAquariumCapability.EXCELLENT,
            max_aquariums_recommended=4,
            cpu_cores=16,
            available_memory_gb=24.5,
            total_memory_gb=32.0,
            has_gpu=True,
            gpu_name="NVIDIA RTX 4080",
            cpu_usage_percent=15.0,
            memory_usage_percent=23.4,
            can_process_realtime=True,
            recommendations=["All optimal"],
            warnings=[],
            gpu_memory_total_gb=16.0,
            gpu_memory_available_gb=14.2,
        )

        s = str(rep)
        assert "EXCELLENT" in s
        assert "Max Aquariums: 4" in s
        assert "NVIDIA RTX 4080" in s
        assert "14.2GB / 16.0GB free" in s
        assert "Real-time: Yes" in s

    def test_hardware_capability_report_str_without_gpu(self):
        rep = HardwareCapabilityReport(
            capability=MultiAquariumCapability.LIMITED,
            max_aquariums_recommended=1,
            cpu_cores=4,
            available_memory_gb=3.5,
            total_memory_gb=8.0,
            has_gpu=False,
            gpu_name=None,
            cpu_usage_percent=45.0,
            memory_usage_percent=56.2,
            can_process_realtime=True,
            recommendations=[],
            warnings=["Low memory"],
        )

        s = str(rep)
        assert "LIMITED" in s
        assert "GPU: No" in s
        assert "Max Aquariums: 1" in s

    def test_calculate_capability_tier_insufficient(self):
        settings = MagicMock()
        det = HardwareCapabilityDetector(settings)

        tier = det._calculate_capability_tier(
            cpu_cores=1,
            total_memory_gb=3.0,
            has_gpu=False,
            cpu_usage=10.0,
            memory_usage=20.0,
        )
        assert tier == MultiAquariumCapability.INSUFFICIENT

    def test_calculate_capability_tier_limited(self):
        settings = MagicMock()
        det = HardwareCapabilityDetector(settings)

        tier = det._calculate_capability_tier(
            cpu_cores=2,
            total_memory_gb=5.0,
            has_gpu=False,
            cpu_usage=10.0,
            memory_usage=20.0,
        )
        assert tier == MultiAquariumCapability.LIMITED

    def test_calculate_capability_tier_excellent(self):
        settings = MagicMock()
        det = HardwareCapabilityDetector(settings)

        tier = det._calculate_capability_tier(
            cpu_cores=16,
            total_memory_gb=32.0,
            has_gpu=True,
            cpu_usage=5.0,
            memory_usage=15.0,
        )
        assert tier == MultiAquariumCapability.EXCELLENT

    def test_calculate_max_aquariums(self):
        settings = MagicMock()
        det = HardwareCapabilityDetector(settings)

        assert det._calculate_max_aquariums(MultiAquariumCapability.EXCELLENT, 16, 32.0) >= 4
        assert det._calculate_max_aquariums(MultiAquariumCapability.GOOD, 8, 16.0) >= 2
        assert det._calculate_max_aquariums(MultiAquariumCapability.MODERATE, 4, 8.0) == 2
        assert det._calculate_max_aquariums(MultiAquariumCapability.LIMITED, 2, 4.0) == 1
        assert det._calculate_max_aquariums(MultiAquariumCapability.INSUFFICIENT, 1, 2.0) == 0

    def test_assess_capability_mocked(self):
        settings = MagicMock()
        det = HardwareCapabilityDetector(settings)

        with (
            patch("psutil.cpu_percent", return_value=12.0),
            patch("psutil.virtual_memory") as mock_vm,
            patch.object(det, "_detect_gpu", return_value=(False, None, None, None)),
        ):
            mock_vm.return_value = MagicMock(
                total=16 * (1024**3),
                available=12 * (1024**3),
                percent=25.0,
            )

            report = det.assess_capability()
            assert isinstance(report, HardwareCapabilityReport)
            assert report.cpu_usage_percent == 12.0
            assert report.total_memory_gb == 16.0
            assert report.can_process_realtime is True
