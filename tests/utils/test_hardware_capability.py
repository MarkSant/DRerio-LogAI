"""Tests for ``zebtrack.utils.hardware_capability``.

The detector tells the live wizard how many aquariums a machine can track in
real time, so the tier boundaries are checked on both sides of every threshold
and the assessment is driven end to end on described hardware (fake ``torch``
and ``openvino`` modules, patched ``psutil`` readings).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from zebtrack.utils import hardware_capability as hc
from zebtrack.utils.hardware_capability import (
    HardwareCapabilityDetector,
    HardwareCapabilityReport,
    MultiAquariumCapability,
)

pytestmark = pytest.mark.unit

GIB = 1024**3
Tier = MultiAquariumCapability


@pytest.fixture
def detector() -> HardwareCapabilityDetector:
    return HardwareCapabilityDetector(SimpleNamespace())  # type: ignore[arg-type]


def _no_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)


def _no_openvino(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openvino", None)


def _cuda(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = True,
    name: str = "RTX 3060",
    total_gb: float = 12.0,
    allocated_gb: float = 2.0,
    error: Exception | None = None,
) -> None:
    def _name(index: int) -> str:
        if error is not None:
            raise error
        return name

    cuda = SimpleNamespace(
        is_available=lambda: available,
        get_device_name=_name,
        get_device_properties=lambda index: SimpleNamespace(total_memory=int(total_gb * GIB)),
        memory_allocated=lambda index: int(allocated_gb * GIB),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))


def _openvino(
    monkeypatch: pytest.MonkeyPatch,
    *,
    devices: tuple[str, ...] = ("CPU", "GPU"),
    names: dict[str, str] | None = None,
    core_error: Exception | None = None,
) -> None:
    device_names: dict[str, str] = names or {}

    class _Core:
        def __init__(self) -> None:
            if core_error is not None:
                raise core_error
            self.available_devices = list(devices)

        def get_property(self, device: str, prop: str) -> str:
            assert prop == "FULL_DEVICE_NAME"
            return device_names[device]

    monkeypatch.setitem(sys.modules, "openvino", SimpleNamespace(Core=_Core))


def _machine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cores: int,
    total_gb: float,
    available_gb: float,
    memory_percent: float,
    cpu_percent: float,
) -> list[float]:
    """Patch the psutil/multiprocessing readings; returns the sampling intervals used."""
    intervals: list[float] = []
    memory = SimpleNamespace(
        total=int(total_gb * GIB), available=int(available_gb * GIB), percent=memory_percent
    )

    def _cpu_percent(interval: float) -> float:
        intervals.append(interval)
        return cpu_percent

    monkeypatch.setattr(hc.multiprocessing, "cpu_count", lambda: cores)
    monkeypatch.setattr(hc.psutil, "virtual_memory", lambda: memory)
    monkeypatch.setattr(hc.psutil, "cpu_percent", _cpu_percent)
    return intervals


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------


class TestCapabilityTier:
    @pytest.mark.parametrize(
        ("cores", "memory_gb", "has_gpu", "expected"),
        [
            # The memory thresholds are NOMINAL sizes: the OS reports up to 1 GB
            # less than installed (A4-12), so a reported 15.0 GiB is a 16 GB machine.
            # Under 2 cores or under 4 GB: record-only.
            (1, 64.0, True, Tier.INSUFFICIENT),
            (16, 2.9, True, Tier.INSUFFICIENT),
            # 2-3 cores or under 6 GB: one aquarium.
            (2, 3.0, False, Tier.LIMITED),
            (3, 64.0, True, Tier.LIMITED),
            (16, 4.9, True, Tier.LIMITED),
            # 4-5 cores or under 8 GB: two aquariums.
            (4, 5.0, False, Tier.MODERATE),
            (5, 64.0, True, Tier.MODERATE),
            (16, 6.9, True, Tier.MODERATE),
            # 6-7 cores or under 16 GB: two to three.
            (6, 7.0, False, Tier.GOOD),
            (7, 64.0, True, Tier.GOOD),
            (16, 14.9, True, Tier.GOOD),
            # A nominal 16 GB laptop reports about 15.8 GiB: it is a 16 GB machine.
            (8, 15.8, True, Tier.EXCELLENT),
            # 8+ cores and 16+ GB only become EXCELLENT with a GPU.
            (8, 16.0, True, Tier.EXCELLENT),
            (8, 16.0, False, Tier.GOOD),
            (32, 128.0, False, Tier.GOOD),
        ],
    )
    def test_each_threshold_from_both_sides(
        self,
        detector: HardwareCapabilityDetector,
        cores: int,
        memory_gb: float,
        has_gpu: bool,
        expected: Tier,
    ) -> None:
        tier = detector._calculate_capability_tier(
            cpu_cores=cores,
            total_memory_gb=memory_gb,
            has_gpu=has_gpu,
            cpu_usage=10.0,
            memory_usage=10.0,
        )
        assert tier is expected

    def test_current_load_does_not_change_the_tier(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        # The tier describes the machine, not the moment: load only adds warnings.
        tier = detector._calculate_capability_tier(
            cpu_cores=8, total_memory_gb=16.0, has_gpu=True, cpu_usage=99.0, memory_usage=99.0
        )
        assert tier is Tier.EXCELLENT


class TestMaxAquariums:
    @pytest.mark.parametrize(
        ("tier", "cores", "memory_gb", "expected"),
        [
            (Tier.INSUFFICIENT, 16, 64.0, 0),
            (Tier.LIMITED, 16, 64.0, 1),
            (Tier.MODERATE, 16, 64.0, 2),
            # GOOD: one per three cores plus one, at most three.
            (Tier.GOOD, 5, 64.0, 2),
            (Tier.GOOD, 6, 64.0, 3),
            (Tier.GOOD, 32, 64.0, 3),
            # EXCELLENT: two cores and 4 GB per aquarium, at most six.
            (Tier.EXCELLENT, 8, 16.0, 4),
            (Tier.EXCELLENT, 8, 64.0, 4),
            (Tier.EXCELLENT, 16, 19.9, 4),
            (Tier.EXCELLENT, 16, 20.0, 5),
            (Tier.EXCELLENT, 32, 128.0, 6),
        ],
    )
    def test_the_count_scales_within_each_tier(
        self,
        detector: HardwareCapabilityDetector,
        tier: Tier,
        cores: int,
        memory_gb: float,
        expected: int,
    ) -> None:
        assert detector._calculate_max_aquariums(tier, cores, memory_gb) == expected

    def test_an_unknown_tier_is_treated_as_a_single_aquarium(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        assert detector._calculate_max_aquariums("mystery", 8, 16.0) == 1  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Recommendations and warnings
# ---------------------------------------------------------------------------


def _recommend(detector: HardwareCapabilityDetector, tier: Tier, **overrides: Any) -> list[str]:
    values: dict[str, Any] = {
        "capability": tier,
        "cpu_cores": 8,
        "available_memory_gb": 12.0,
        "has_gpu": True,
        "cpu_usage": 10.0,
        "memory_usage": 10.0,
    }
    values.update(overrides)
    return detector._generate_recommendations(**values)


class TestRecommendations:
    def test_an_insufficient_machine_is_sent_to_record_only_with_its_numbers(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        lines = _recommend(detector, Tier.INSUFFICIENT, cpu_cores=1, available_memory_gb=2.5)
        assert len(lines) == 2
        assert "record video only" in lines[0]
        assert "current: 1 cores, 2.5GB" in lines[1]

    def test_a_limited_machine_names_only_the_resource_that_limits_it(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        cpu_bound = _recommend(detector, Tier.LIMITED, cpu_cores=3, available_memory_gb=12.0)
        assert len(cpu_bound) == 2
        assert "Limited CPU (3 cores)" in cpu_bound[1]

        memory_bound = _recommend(detector, Tier.LIMITED, cpu_cores=8, available_memory_gb=5.9)
        assert len(memory_bound) == 2
        assert "Limited memory (5.9GB available)" in memory_bound[1]

        both = _recommend(detector, Tier.LIMITED, cpu_cores=3, available_memory_gb=5.9)
        assert len(both) == 3

        neither = _recommend(detector, Tier.LIMITED, cpu_cores=4, available_memory_gb=6.0)
        assert len(neither) == 1
        assert "limited to 1 aquarium" in neither[0]

    def test_a_moderate_machine_is_told_about_the_missing_gpu(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        with_gpu = _recommend(detector, Tier.MODERATE, has_gpu=True)
        without_gpu = _recommend(detector, Tier.MODERATE, has_gpu=False)
        assert with_gpu == ["System supports up to 2 aquariums simultaneously."]
        assert without_gpu[0] == with_gpu[0]
        assert "No GPU detected" in without_gpu[1]

    @pytest.mark.parametrize(
        ("tier", "fragment"), [(Tier.GOOD, "2-3 aquariums"), (Tier.EXCELLENT, "4+ aquariums")]
    )
    def test_capable_machines_get_one_line(
        self, detector: HardwareCapabilityDetector, tier: Tier, fragment: str
    ) -> None:
        (line,) = _recommend(detector, tier, has_gpu=False)
        assert fragment in line

    @pytest.mark.parametrize(
        ("cpu_usage", "memory_usage", "extra"),
        [(70.0, 80.0, 0), (70.1, 80.0, 1), (70.0, 80.1, 1), (95.0, 95.0, 2)],
    )
    def test_load_advice_starts_strictly_above_the_limits(
        self,
        detector: HardwareCapabilityDetector,
        cpu_usage: float,
        memory_usage: float,
        extra: int,
    ) -> None:
        lines = _recommend(detector, Tier.GOOD, cpu_usage=cpu_usage, memory_usage=memory_usage)
        assert len(lines) == 1 + extra

    def test_load_advice_quotes_the_measured_usage(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        lines = _recommend(detector, Tier.GOOD, cpu_usage=91.25, memory_usage=88.0)
        assert "CPU under heavy load (91.2%)" in lines[1]
        assert "Memory heavily used (88.0%)" in lines[2]


class TestWarnings:
    def _warn(
        self, detector: HardwareCapabilityDetector, tier: Tier, **overrides: Any
    ) -> list[str]:
        values: dict[str, Any] = {
            "capability": tier,
            "cpu_usage": 10.0,
            "memory_usage": 10.0,
            "available_memory_gb": 12.0,
        }
        values.update(overrides)
        return detector._generate_warnings(**values)

    def test_a_healthy_machine_has_no_warnings(self, detector: HardwareCapabilityDetector) -> None:
        assert self._warn(detector, Tier.GOOD) == []

    def test_boundary_values_do_not_warn(self, detector: HardwareCapabilityDetector) -> None:
        warnings = self._warn(
            detector, Tier.GOOD, cpu_usage=80.0, memory_usage=90.0, available_memory_gb=4.0
        )
        assert warnings == []

    def test_each_condition_adds_its_own_warning(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        assert "NOT RECOMMENDED" in self._warn(detector, Tier.INSUFFICIENT)[0]
        assert "CPU overloaded (80.1%)" in self._warn(detector, Tier.GOOD, cpu_usage=80.1)[0]
        assert "Critical memory (90.1%)" in self._warn(detector, Tier.GOOD, memory_usage=90.1)[0]
        assert "very low" in self._warn(detector, Tier.GOOD, available_memory_gb=3.9)[0]

    def test_everything_wrong_at_once_reports_all_four(
        self, detector: HardwareCapabilityDetector
    ) -> None:
        warnings = self._warn(
            detector, Tier.INSUFFICIENT, cpu_usage=99.0, memory_usage=99.0, available_memory_gb=0.5
        )
        assert len(warnings) == 4


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------


class TestDetectGpu:
    def test_a_cuda_gpu_reports_total_and_free_memory(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _cuda(monkeypatch, name="RTX 3060", total_gb=12.0, allocated_gb=2.5)
        _no_openvino(monkeypatch)

        assert detector._detect_gpu() == (True, "RTX 3060", 12.0, 9.5)

    def test_cuda_takes_precedence_over_openvino(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _cuda(monkeypatch, name="RTX 3060")
        _openvino(monkeypatch, names={"GPU": "Intel Iris Xe"})
        assert detector._detect_gpu()[1] == "RTX 3060"

    def test_an_intel_gpu_is_found_through_openvino_without_memory_figures(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _cuda(monkeypatch, available=False)
        _openvino(monkeypatch, devices=("CPU", "GPU.0", "GPU.1"), names={"GPU.0": "Intel Iris Xe"})

        assert detector._detect_gpu() == (True, "Intel Iris Xe (OpenVINO)", None, None)

    def test_a_cuda_query_that_raises_falls_through_to_openvino(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _cuda(monkeypatch, error=RuntimeError("driver crashed"))
        _openvino(monkeypatch, names={"GPU": "Intel Arc A770"})
        assert detector._detect_gpu() == (True, "Intel Arc A770 (OpenVINO)", None, None)

    def test_an_unnamed_openvino_gpu_is_described_by_the_processor(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _no_torch(monkeypatch)
        _openvino(monkeypatch, names={})  # get_property raises KeyError
        monkeypatch.setattr(hc.platform, "processor", lambda: "Intel64 Family 6")

        assert detector._detect_gpu() == (True, "Intel Graphics (Intel64 Family 6)", None, None)

    @pytest.mark.parametrize("devices", [("CPU",), ("CPU", "NPU"), ()])
    def test_openvino_without_a_gpu_device_is_no_gpu(
        self,
        detector: HardwareCapabilityDetector,
        monkeypatch: pytest.MonkeyPatch,
        devices: tuple[str, ...],
    ) -> None:
        _no_torch(monkeypatch)
        _openvino(monkeypatch, devices=devices)
        assert detector._detect_gpu() == (False, None, None, None)

    def test_no_backend_installed_is_no_gpu(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _no_torch(monkeypatch)
        _no_openvino(monkeypatch)
        assert detector._detect_gpu() == (False, None, None, None)

    def test_a_broken_openvino_runtime_is_no_gpu(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _no_torch(monkeypatch)
        _openvino(monkeypatch, core_error=RuntimeError("plugins.xml missing"))
        assert detector._detect_gpu() == (False, None, None, None)


# ---------------------------------------------------------------------------
# Full assessment
# ---------------------------------------------------------------------------


class TestAssessCapability:
    def test_a_workstation_with_a_cuda_gpu(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        intervals = _machine(
            monkeypatch,
            cores=12,
            total_gb=32.0,
            available_gb=20.0,
            memory_percent=37.5,
            cpu_percent=15.0,
        )
        _cuda(monkeypatch, name="RTX 3060", total_gb=12.0, allocated_gb=2.0)

        report = detector.assess_capability()

        assert report == HardwareCapabilityReport(
            capability=Tier.EXCELLENT,
            max_aquariums_recommended=6,
            cpu_cores=12,
            available_memory_gb=20.0,
            total_memory_gb=32.0,
            has_gpu=True,
            gpu_name="RTX 3060",
            cpu_usage_percent=15.0,
            memory_usage_percent=37.5,
            can_process_realtime=True,
            recommendations=[
                "Excellent system! Supports 4+ aquariums simultaneously at high performance."
            ],
            warnings=[],
            gpu_memory_total_gb=12.0,
            gpu_memory_available_gb=10.0,
        )
        assert intervals == [0.5]

    def test_the_tier_uses_total_memory_while_the_advice_uses_what_is_free(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 16 GB installed but only 3 GB free: still a GOOD machine, with a warning.
        _machine(
            monkeypatch,
            cores=8,
            total_gb=16.0,
            available_gb=3.0,
            memory_percent=81.0,
            cpu_percent=20.0,
        )
        _no_torch(monkeypatch)
        _no_openvino(monkeypatch)

        report = detector.assess_capability()

        assert report.capability is Tier.GOOD
        assert report.max_aquariums_recommended == 3
        assert report.has_gpu is False
        assert len(report.recommendations) == 2  # tier line + memory load
        assert len(report.warnings) == 1
        assert "very low" in report.warnings[0]

    def test_an_underpowered_machine_cannot_process_in_real_time(
        self, detector: HardwareCapabilityDetector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _machine(
            monkeypatch,
            cores=1,
            total_gb=2.0,
            available_gb=1.0,
            memory_percent=50.0,
            cpu_percent=30.0,
        )
        _no_torch(monkeypatch)
        _no_openvino(monkeypatch)

        report = detector.assess_capability()

        assert report.capability is Tier.INSUFFICIENT
        assert report.max_aquariums_recommended == 0
        assert report.can_process_realtime is False
        assert any("NOT RECOMMENDED" in warning for warning in report.warnings)


# ---------------------------------------------------------------------------
# Report text
# ---------------------------------------------------------------------------


def _report(**overrides: Any) -> HardwareCapabilityReport:
    values: dict[str, Any] = {
        "capability": Tier.GOOD,
        "max_aquariums_recommended": 3,
        "cpu_cores": 8,
        "available_memory_gb": 9.26,
        "total_memory_gb": 16.0,
        "has_gpu": False,
        "gpu_name": None,
        "cpu_usage_percent": 12.34,
        "memory_usage_percent": 42.0,
        "can_process_realtime": True,
        "recommendations": [],
        "warnings": [],
    }
    values.update(overrides)
    return HardwareCapabilityReport(**values)


class TestReportText:
    def test_a_machine_without_gpu(self) -> None:
        assert str(_report()) == (
            "Capability: GOOD\n"
            "Max Aquariums: 3\n"
            "CPU: 8 cores (12.3% used)\n"
            "Memory: 9.3GB available / 16.0GB total\n"
            "GPU: No\n"
            "Real-time: Yes"
        )

    def test_a_gpu_with_memory_figures(self) -> None:
        text = str(
            _report(
                has_gpu=True,
                gpu_name="RTX 3060",
                gpu_memory_total_gb=12.0,
                gpu_memory_available_gb=9.5,
            )
        )
        assert "GPU: Yes - RTX 3060 (9.5GB / 12.0GB free)" in text

    def test_a_gpu_without_memory_figures_or_name(self) -> None:
        assert "GPU: Yes - Intel Iris Xe (OpenVINO)\n" in str(
            _report(has_gpu=True, gpu_name="Intel Iris Xe (OpenVINO)")
        )
        assert "GPU: Yes - Unknown\n" in str(_report(has_gpu=True))

    def test_a_record_only_machine(self) -> None:
        text = str(
            _report(
                capability=Tier.INSUFFICIENT,
                max_aquariums_recommended=0,
                can_process_realtime=False,
            )
        )
        assert text.startswith("Capability: INSUFFICIENT\nMax Aquariums: 0\n")
        assert text.endswith("Real-time: No (record-only)")
