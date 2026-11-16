"""
Extended unit tests for LiveCameraMode and LiveCameraModeSelector.
"""

from __future__ import annotations

from types import SimpleNamespace

from zebtrack.core.recording.live_camera_mode import (
    LiveCameraMode,
    LiveCameraModeRecommendation,
    LiveCameraModeSelector,
    get_mode_description,
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


def _report(*, max_aquariums: int, realtime: bool, cores: int = 4, ram: float = 4.0):
    return HardwareCapabilityReport(
        capability=MultiAquariumCapability.LIMITED,
        max_aquariums_recommended=max_aquariums,
        cpu_cores=cores,
        available_memory_gb=ram,
        total_memory_gb=ram * 2,
        has_gpu=False,
        gpu_name=None,
        cpu_usage_percent=50.0,
        memory_usage_percent=50.0,
        can_process_realtime=realtime,
        recommendations=[],
        warnings=[],
    )


def _selector() -> LiveCameraModeSelector:
    return LiveCameraModeSelector(settings_obj=SimpleNamespace())  # type: ignore[arg-type]


class TestRecommendationDetails:
    def test_request_equal_to_capacity_is_still_realtime(self):
        rec = _selector().recommend_mode(2, _report(max_aquariums=2, realtime=True))

        assert rec.recommended_mode is LiveCameraMode.MULTI_AQUARIUM_REALTIME
        assert rec.warnings == []
        assert "supports 2 aquariums simultaneously" in rec.reason

    def test_partial_support_with_sequential_offers_single_then_record(self):
        rec = _selector().recommend_mode(3, _report(max_aquariums=2, realtime=True))

        assert rec.reason.endswith("Recommended: record 3 separate sessions.")
        assert "only 2 of the 3 aquariums" in rec.reason
        assert [mode for mode, _ in rec.alternative_options] == [
            LiveCameraMode.SINGLE_AQUARIUM_REALTIME,
            LiveCameraMode.RECORD_ONLY,
        ]
        assert rec.warnings == [
            "⚠️ The system does not support 3 aquariums simultaneously.",
            "Maximum supported: 2 aquariums.",
        ]
        assert rec.max_aquariums_supported == 2

    def test_partial_support_without_sequential_offers_split_then_record(self):
        rec = _selector().recommend_mode(
            4, _report(max_aquariums=1, realtime=True), allow_sequential=False
        )

        assert rec.reason.endswith("Recommended: process only 1 aquarium in this session.")
        (split_mode, split_text), (record_mode, _) = rec.alternative_options
        assert split_mode is LiveCameraMode.SEQUENTIAL_AQUARIUM
        assert split_text == "Split into 4 separate sessions"
        assert record_mode is LiveCameraMode.RECORD_ONLY
        # One aquarium reads as a singular sentence, not "aquarium(s)".
        assert rec.warnings[1] == "Maximum supported: 1 aquarium."

    def test_no_realtime_reports_the_hardware_it_saw(self):
        rec = _selector().recommend_mode(
            2, _report(max_aquariums=3, realtime=False, cores=2, ram=3.26)
        )

        assert rec.recommended_mode is LiveCameraMode.RECORD_ONLY
        assert rec.max_aquariums_supported == 0
        assert rec.warnings[1:] == [
            "CPU: 2 cores (minimum 2)",
            "RAM: 3.3GB available (minimum 4GB)",
        ]

    def test_realtime_with_zero_capacity_falls_back_to_record_only(self):
        rec = _selector().recommend_mode(2, _report(max_aquariums=0, realtime=True))

        assert rec.recommended_mode is LiveCameraMode.RECORD_ONLY
        assert rec.can_process_realtime is True
        assert rec.alternative_options == []
        assert rec.reason == "Default mode selected."


class TestSequentialPlan:
    def test_one_single_aquarium_session_per_aquarium(self):
        plan = _selector().create_sequential_session_plan(3, "Dia_1_G1")

        assert [s["experiment_id"] for s in plan] == [
            "Dia_1_G1_aquarium_0",
            "Dia_1_G1_aquarium_1",
            "Dia_1_G1_aquarium_2",
        ]
        assert [s["aquarium_index"] for s in plan] == [0, 1, 2]
        assert {s["aquarium_count_total"] for s in plan} == {3}
        assert {s["mode"] for s in plan} == {LiveCameraMode.SINGLE_AQUARIUM_REALTIME}
        assert plan[0]["notes"] == "Session 1 of 3 (individual aquarium)"
        assert plan[2]["notes"] == "Session 3 of 3 (individual aquarium)"

    def test_zero_aquariums_is_an_empty_plan(self):
        assert _selector().create_sequential_session_plan(0, "x") == []


class TestModeDescription:
    def test_every_mode_has_its_own_description(self):
        descriptions = {mode: get_mode_description(mode) for mode in LiveCameraMode}

        assert descriptions[LiveCameraMode.RECORD_ONLY] == (
            "Record video without detection (process offline later)"
        )
        assert len(set(descriptions.values())) == len(LiveCameraMode)
        assert "Unknown mode" not in descriptions.values()

    def test_unknown_value_has_a_fallback(self):
        assert get_mode_description("nope") == "Unknown mode"  # type: ignore[arg-type]
