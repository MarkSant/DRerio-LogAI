"""The single analysis-concurrency rule (#725, A7-02)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.settings import PerformanceSettings
from zebtrack.utils.performance_policy import (
    analysis_max_workers,
    effective_batch_nireq,
    is_low_memory_mode,
    parallel_analysis_enabled,
)


def _settings(**performance: object) -> SimpleNamespace:
    return SimpleNamespace(performance=PerformanceSettings(**performance))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("performance", "expected"),
    [
        ({}, True),
        ({"enable_parallel_analysis": False}, False),
        ({"memory_mode": "low"}, False),
        ({"memory_mode": "low", "enable_parallel_analysis": True}, False),
        ({"memory_mode": "normal", "enable_parallel_analysis": True}, True),
    ],
)
def test_parallel_analysis_enabled(performance: dict[str, object], expected: bool) -> None:
    assert parallel_analysis_enabled(_settings(**performance)) is expected


def test_without_settings_the_defaults_apply() -> None:
    assert parallel_analysis_enabled(None) is True
    assert is_low_memory_mode(None) is False
    assert analysis_max_workers(None, 3) == 3
    assert effective_batch_nireq(None, 4) == 4
    # A settings stub without a performance section behaves like the defaults.
    assert analysis_max_workers(SimpleNamespace(), 5) == 5


def test_is_low_memory_mode_reads_memory_mode() -> None:
    assert is_low_memory_mode(_settings(memory_mode="low")) is True
    assert is_low_memory_mode(_settings(memory_mode="normal")) is False


@pytest.mark.parametrize(
    ("performance", "requested", "expected"),
    [
        ({}, 3, 3),
        ({}, 5, 5),
        ({}, 0, 1),
        ({"enable_parallel_analysis": False}, 3, 1),
        ({"memory_mode": "low"}, 3, 1),
        ({"memory_mode": "low", "enable_parallel_analysis": True}, 5, 1),
    ],
)
def test_analysis_max_workers(
    performance: dict[str, object], requested: int, expected: int
) -> None:
    assert analysis_max_workers(_settings(**performance), requested) == expected


@pytest.mark.parametrize(
    ("memory_mode", "configured", "expected"),
    [("normal", 4, 4), ("normal", 8, 8), ("low", 4, 1), ("low", 16, 1)],
)
def test_effective_batch_nireq(memory_mode: str, configured: int, expected: int) -> None:
    assert effective_batch_nireq(_settings(memory_mode=memory_mode), configured) == expected


def test_parallel_analysis_off_does_not_touch_batch_nireq() -> None:
    """Only the low-memory mode caps OpenVINO; sequential analysis alone does not."""
    assert effective_batch_nireq(_settings(enable_parallel_analysis=False), 4) == 4
