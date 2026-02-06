"""Tests for hardware_capability logic helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.utils.hardware_capability import (
    HardwareCapabilityDetector,
    HardwareCapabilityReport,
    MultiAquariumCapability,
)


def _make_detector():
    return HardwareCapabilityDetector(settings_obj=MagicMock())


def test_calculate_capability_tier_thresholds():
    detector = _make_detector()

    assert (
        detector._calculate_capability_tier(
            cpu_cores=1,
            total_memory_gb=8,
            has_gpu=False,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.INSUFFICIENT
    )

    assert (
        detector._calculate_capability_tier(
            cpu_cores=3,
            total_memory_gb=8,
            has_gpu=False,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.LIMITED
    )

    assert (
        detector._calculate_capability_tier(
            cpu_cores=4,
            total_memory_gb=6,
            has_gpu=False,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.MODERATE
    )

    assert (
        detector._calculate_capability_tier(
            cpu_cores=6,
            total_memory_gb=8,
            has_gpu=False,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.GOOD
    )

    assert (
        detector._calculate_capability_tier(
            cpu_cores=8,
            total_memory_gb=16,
            has_gpu=True,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.EXCELLENT
    )

    assert (
        detector._calculate_capability_tier(
            cpu_cores=8,
            total_memory_gb=16,
            has_gpu=False,
            cpu_usage=10,
            memory_usage=10,
        )
        == MultiAquariumCapability.GOOD
    )


def test_calculate_max_aquariums():
    detector = _make_detector()

    assert (
        detector._calculate_max_aquariums(
            MultiAquariumCapability.INSUFFICIENT, cpu_cores=4, total_memory_gb=8
        )
        == 0
    )

    assert (
        detector._calculate_max_aquariums(
            MultiAquariumCapability.LIMITED, cpu_cores=3, total_memory_gb=6
        )
        == 1
    )

    assert (
        detector._calculate_max_aquariums(
            MultiAquariumCapability.MODERATE, cpu_cores=4, total_memory_gb=8
        )
        == 2
    )

    assert (
        detector._calculate_max_aquariums(
            MultiAquariumCapability.GOOD, cpu_cores=6, total_memory_gb=8
        )
        == 3
    )

    assert (
        detector._calculate_max_aquariums(
            MultiAquariumCapability.EXCELLENT, cpu_cores=10, total_memory_gb=20
        )
        == 5
    )


def test_generate_recommendations_and_warnings():
    detector = _make_detector()

    recommendations = detector._generate_recommendations(
        capability=MultiAquariumCapability.LIMITED,
        cpu_cores=2,
        available_memory_gb=3.5,
        has_gpu=False,
        cpu_usage=75,
        memory_usage=85,
    )
    assert any("Sistema limitado" in rec for rec in recommendations)
    assert any("CPU" in rec for rec in recommendations)
    assert any("Memória" in rec for rec in recommendations)
    assert any("CPU com alta carga" in rec for rec in recommendations)
    assert any("Memória com alta ocupação" in rec for rec in recommendations)

    warnings = detector._generate_warnings(
        capability=MultiAquariumCapability.INSUFFICIENT,
        cpu_usage=85,
        memory_usage=95,
        available_memory_gb=2.5,
    )
    assert any("PROCESSAMENTO EM TEMPO REAL" in w for w in warnings)
    assert any("CPU sobrecarregada" in w for w in warnings)
    assert any("Memória crítica" in w for w in warnings)
    assert any("Memória disponível muito baixa" in w for w in warnings)


def test_report_string_format():
    report = HardwareCapabilityReport(
        capability=MultiAquariumCapability.GOOD,
        max_aquariums_recommended=2,
        cpu_cores=6,
        available_memory_gb=5.0,
        total_memory_gb=8.0,
        has_gpu=True,
        gpu_name="Test GPU",
        cpu_usage_percent=25.0,
        memory_usage_percent=40.0,
        can_process_realtime=True,
        recommendations=[],
        warnings=[],
        gpu_memory_total_gb=4.0,
        gpu_memory_available_gb=2.0,
    )

    summary = str(report)
    assert "Capability: GOOD" in summary
    assert "Max Aquariums: 2" in summary
    assert "CPU: 6 cores" in summary
    assert "GPU: Yes" in summary
    assert "Real-time: Yes" in summary
