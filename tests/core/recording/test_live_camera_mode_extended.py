"""
Extended unit tests for LiveCameraMode and LiveCameraModeSelector.
"""

from __future__ import annotations

from types import SimpleNamespace

from zebtrack.core.recording.live_camera_mode import (
    LiveCameraMode,
    LiveCameraModeRecommendation,
    LiveCameraModeSelector,
)
from zebtrack.utils.hardware_capability import (
    HardwareCapabilityReport,
    MultiAquariumCapability,
)


class TestLiveCameraModeExtended:
    """Test LiveCameraMode enum, recommendation DTO, and decision tree."""

    def test_live_camera_mode_enum_values(self):
        assert LiveCameraMode.MULTI_AQUARIUM_REALTIME.value == "multi_aquarium_realtime"
        assert LiveCameraMode.SINGLE_AQUARIUM_REALTIME.value == "single_aquarium_realtime"
        assert LiveCameraMode.RECORD_ONLY.value == "record_only"
        assert LiveCameraMode.SEQUENTIAL_AQUARIUM.value == "sequential_aquarium"

    def test_live_camera_mode_recommendation_str(self):
        rec = LiveCameraModeRecommendation(
            recommended_mode=LiveCameraMode.MULTI_AQUARIUM_REALTIME,
            requested_aquariums=3,
            max_aquariums_supported=4,
            can_process_realtime=True,
            reason="All supported",
            alternative_options=[(LiveCameraMode.RECORD_ONLY, "Record without detection")],
            warnings=[],
        )
        s = str(rec)
        assert "Recommended mode: multi_aquarium_realtime" in s
        assert "Aquariums requested: 3" in s
        assert "Aquariums supported: 4" in s
        assert "Reason: All supported" in s
        assert "Alternatives: 1" in s

    def test_recommend_mode_case1_multi_aquarium(self):
        settings = SimpleNamespace()
        selector = LiveCameraModeSelector(settings_obj=settings)  # type: ignore[arg-type]

        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.EXCELLENT,
            max_aquariums_recommended=4,
            cpu_cores=8,
            available_memory_gb=16.0,
            total_memory_gb=32.0,
            has_gpu=True,
            gpu_name="NVIDIA",
            cpu_usage_percent=25.0,
            memory_usage_percent=40.0,
            can_process_realtime=True,
            recommendations=["Real-time supported"],
            warnings=[],
        )

        rec = selector.recommend_mode(requested_aquariums=3, hardware_report=report)
        assert rec.recommended_mode == LiveCameraMode.MULTI_AQUARIUM_REALTIME
        assert rec.can_process_realtime is True
        assert len(rec.alternative_options) == 1
        assert rec.alternative_options[0][0] == LiveCameraMode.RECORD_ONLY

    def test_recommend_mode_case1_single_aquarium(self):
        settings = SimpleNamespace()
        selector = LiveCameraModeSelector(settings_obj=settings)  # type: ignore[arg-type]

        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.GOOD,
            max_aquariums_recommended=2,
            cpu_cores=6,
            available_memory_gb=8.0,
            total_memory_gb=16.0,
            has_gpu=False,
            gpu_name=None,
            cpu_usage_percent=30.0,
            memory_usage_percent=50.0,
            can_process_realtime=True,
            recommendations=["Real-time supported"],
            warnings=[],
        )

        rec = selector.recommend_mode(requested_aquariums=1, hardware_report=report)
        assert rec.recommended_mode == LiveCameraMode.SINGLE_AQUARIUM_REALTIME
        assert rec.can_process_realtime is True

    def test_recommend_mode_case2_partial_support(self):
        settings = SimpleNamespace()
        selector = LiveCameraModeSelector(settings_obj=settings)  # type: ignore[arg-type]

        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.LIMITED,
            max_aquariums_recommended=1,
            cpu_cores=4,
            available_memory_gb=4.0,
            total_memory_gb=8.0,
            has_gpu=False,
            gpu_name=None,
            cpu_usage_percent=70.0,
            memory_usage_percent=75.0,
            can_process_realtime=True,
            recommendations=["Limited support"],
            warnings=[],
        )

        # Allow sequential -> SEQUENTIAL_AQUARIUM
        rec_seq = selector.recommend_mode(
            requested_aquariums=3, hardware_report=report, allow_sequential=True
        )
        assert rec_seq.recommended_mode == LiveCameraMode.SEQUENTIAL_AQUARIUM

        # Disallow sequential -> SINGLE_AQUARIUM_REALTIME
        rec_single = selector.recommend_mode(
            requested_aquariums=3, hardware_report=report, allow_sequential=False
        )
        assert rec_single.recommended_mode == LiveCameraMode.SINGLE_AQUARIUM_REALTIME

    def test_recommend_mode_case3_no_realtime(self):
        settings = SimpleNamespace()
        selector = LiveCameraModeSelector(settings_obj=settings)  # type: ignore[arg-type]

        report = HardwareCapabilityReport(
            capability=MultiAquariumCapability.INSUFFICIENT,
            max_aquariums_recommended=0,
            cpu_cores=2,
            available_memory_gb=2.0,
            total_memory_gb=4.0,
            has_gpu=False,
            gpu_name=None,
            cpu_usage_percent=95.0,
            memory_usage_percent=90.0,
            can_process_realtime=False,
            recommendations=["Insufficient"],
            warnings=[],
        )

        rec = selector.recommend_mode(requested_aquariums=2, hardware_report=report)
        assert rec.recommended_mode == LiveCameraMode.RECORD_ONLY
        assert rec.can_process_realtime is False
        assert len(rec.warnings) > 0
