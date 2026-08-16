"""
Extended unit tests for HardwareCapabilityDetector in utils/hardware_capability.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.settings import load_settings
from zebtrack.utils.hardware_capability import (
    HardwareCapabilityDetector,
    HardwareCapabilityReport,
    MultiAquariumCapability,
    assess_hardware_for_live_multi_aquarium,
)


class TestHardwareCapabilityReportExtended:
    """Test HardwareCapabilityReport representation and attributes."""

    def test_str_representation_without_gpu(self):
        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.MODERATE,
            max_aquariums_recommended=2,
            cpu_cores=4,
            available_memory_gb=6.5,
            total_memory_gb=8.0,
            has_gpu=False,
            gpu_name=None,
            cpu_usage_percent=45.0,
            memory_usage_percent=60.0,
            can_process_realtime=True,
            recommendations=["Rec1"],
            warnings=["Warn1"],
        )
        s = str(report)
        assert "Capability: MODERATE" in s
        assert "Max Aquariums: 2"
        assert "GPU: No" in s
        assert "Real-time: Yes" in s

    def test_str_representation_with_gpu(self):
        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.EXCELLENT,
            max_aquariums_recommended=4,
            cpu_cores=16,
            available_memory_gb=24.0,
            total_memory_gb=32.0,
            has_gpu=True,
            gpu_name="NVIDIA RTX 4090",
            cpu_usage_percent=15.0,
            memory_usage_percent=25.0,
            can_process_realtime=True,
            recommendations=[],
            warnings=[],
            gpu_memory_total_gb=24.0,
            gpu_memory_available_gb=20.0,
        )
        s = str(report)
        assert "Capability: EXCELLENT" in s
        assert "NVIDIA RTX 4090" in s
        assert "20.0GB / 24.0GB free" in s


class TestHardwareCapabilityDetectorExtended:
    """Test HardwareCapabilityDetector tier calculation, limits, and recommendations."""

    @pytest.fixture
    def detector(self) -> HardwareCapabilityDetector:
        settings_obj = load_settings()
        return HardwareCapabilityDetector(settings_obj=settings_obj)

    @pytest.mark.parametrize(
        ("cores", "ram", "has_gpu", "expected"),
        [
            (1, 16.0, False, MultiAquariumCapability.INSUFFICIENT),
            (8, 3.5, True, MultiAquariumCapability.INSUFFICIENT),
            (2, 5.0, False, MultiAquariumCapability.LIMITED),
            (3, 8.0, False, MultiAquariumCapability.LIMITED),
            (4, 7.0, False, MultiAquariumCapability.MODERATE),
            (5, 12.0, False, MultiAquariumCapability.MODERATE),
            (6, 12.0, False, MultiAquariumCapability.GOOD),
            (7, 16.0, False, MultiAquariumCapability.GOOD),
            (8, 16.0, False, MultiAquariumCapability.GOOD),
            (8, 16.0, True, MultiAquariumCapability.EXCELLENT),
            (16, 32.0, True, MultiAquariumCapability.EXCELLENT),
        ],
    )
    def test_calculate_capability_tier(
        self,
        detector: HardwareCapabilityDetector,
        cores: int,
        ram: float,
        has_gpu: bool,
        expected: MultiAquariumCapability,
    ):
        tier = detector._calculate_capability_tier(
            cpu_cores=cores,
            total_memory_gb=ram,
            has_gpu=has_gpu,
            cpu_usage=20.0,
            memory_usage=30.0,
        )
        assert tier == expected

    @pytest.mark.parametrize(
        ("tier", "cores", "ram", "expected_max"),
        [
            (MultiAquariumCapability.INSUFFICIENT, 2, 4.0, 0),
            (MultiAquariumCapability.LIMITED, 3, 6.0, 1),
            (MultiAquariumCapability.MODERATE, 4, 8.0, 2),
            (MultiAquariumCapability.GOOD, 6, 12.0, 3),
            (MultiAquariumCapability.EXCELLENT, 16, 32.0, 6),
            (MultiAquariumCapability.EXCELLENT, 8, 16.0, 4),
        ],
    )
    def test_calculate_max_aquariums(
        self,
        detector: HardwareCapabilityDetector,
        tier: MultiAquariumCapability,
        cores: int,
        ram: float,
        expected_max: int,
    ):
        assert detector._calculate_max_aquariums(tier, cores, ram) == expected_max

    def test_generate_warnings_and_recommendations_under_heavy_load(
        self, detector: HardwareCapabilityDetector
    ):
        recs = detector._generate_recommendations(
            capability=MultiAquariumCapability.LIMITED,
            cpu_cores=2,
            available_memory_gb=3.5,
            has_gpu=False,
            cpu_usage=85.0,
            memory_usage=95.0,
        )
        assert any("CPU under heavy load" in r for r in recs)
        assert any("Memory heavily used" in r for r in recs)

        warnings = detector._generate_warnings(
            capability=MultiAquariumCapability.INSUFFICIENT,
            cpu_usage=85.0,
            memory_usage=95.0,
            available_memory_gb=2.0,
        )
        assert any("NOT RECOMMENDED" in w for w in warnings)
        assert any("CPU overloaded" in w for w in warnings)
        assert any("Critical memory" in w for w in warnings)
        assert any("Available memory is very low" in w for w in warnings)

    def test_detect_gpu_cuda(self, detector: HardwareCapabilityDetector):
        with patch.dict("sys.modules", {"torch": MagicMock()}):
            import torch

            torch.cuda.is_available = MagicMock(return_value=True)  # type: ignore[assignment]
            torch.cuda.get_device_name = MagicMock(return_value="Mock NVIDIA GPU")  # type: ignore[assignment]
            props = MagicMock()
            props.total_memory = 16 * (1024**3)
            torch.cuda.get_device_properties = MagicMock(return_value=props)  # type: ignore[assignment]
            torch.cuda.memory_allocated = MagicMock(return_value=4 * (1024**3))  # type: ignore[assignment]

            has_gpu, name, total_gb, free_gb = detector._detect_gpu()
            assert has_gpu is True
            assert name == "Mock NVIDIA GPU"
            assert total_gb == 16.0
            assert free_gb == 12.0

    def test_assess_capability_integration(self, detector: HardwareCapabilityDetector):
        report = detector.assess_capability()
        assert isinstance(report, HardwareCapabilityReport)
        assert report.cpu_cores >= 1
        assert report.total_memory_gb > 0

    def test_assess_hardware_for_live_multi_aquarium_convenience_function(self):
        settings_obj = load_settings()
        report = assess_hardware_for_live_multi_aquarium(settings_obj)
        assert isinstance(report, HardwareCapabilityReport)
