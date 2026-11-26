"""``analysis/protocols/registry.py`` — registry and the never-raising dispatch (ADR-014)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pandas as pd
import pytest

from zebtrack.analysis.protocols import registry
from zebtrack.analysis.protocols.base import ProtocolContext, ProtocolSpec
from zebtrack.analysis.protocols.registry import (
    compute_protocol_metrics,
    get_protocol,
    registered_protocols,
)
from zebtrack.analysis.time_base import TimeBase
from zebtrack.core.services.experiment_profile import (
    ExperimentProfile,
    ProtocolId,
    resolve_experiment_profile,
)


def _context(profile: ExperimentProfile, warnings: list[str] | None = None) -> ProtocolContext:
    return ProtocolContext(
        profile=profile,
        trajectory=pd.DataFrame(),
        rois=(),
        arena_polygon_px=(),
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        window=None,
        time_base=TimeBase(
            fps_sampling=10.0,
            fps_video=10.0,
            duration_s=1.0,
            t_first=0.0,
            t_last=1.0,
            median_dt=0.1,
            source="trajectory_pts",
        ),
        behavioral_config=MappingProxyType({}),
        inputs=MappingProxyType({}),
        behavioral_analyzer=None,  # type: ignore[arg-type]
        roi_analyzer=None,
        warnings=warnings if warnings is not None else [],
    )


def _barnes() -> ExperimentProfile:
    return resolve_experiment_profile(behavioral_config={"protocol": "barnes"})


@pytest.fixture
def with_specs(monkeypatch):
    """Install a registry built from ``specs`` for the duration of the test."""

    def install(*specs: ProtocolSpec) -> None:
        monkeypatch.setattr(registry, "_registry", registry._build_registry(specs))

    return install


def _spec(compute) -> ProtocolSpec:
    return ProtocolSpec(
        protocol=ProtocolId.BARNES, display_name=lambda: "Barnes", compute_metrics=compute
    )


def test_barnes_is_the_only_built_in_protocol(monkeypatch):
    from zebtrack.analysis.protocols.barnes.spec import BARNES_SPEC

    monkeypatch.setattr(registry, "_registry", None)

    assert registered_protocols() == (ProtocolId.BARNES,)
    assert get_protocol(ProtocolId.BARNES) is BARNES_SPEC
    assert get_protocol(ProtocolId.GENERIC) is None


def test_the_registry_is_built_once(monkeypatch):
    calls: list[int] = []

    def builtin() -> tuple[ProtocolSpec, ...]:
        calls.append(1)
        return ()

    monkeypatch.setattr(registry, "_registry", None)
    monkeypatch.setattr(registry, "_builtin_specs", builtin)

    registered_protocols()
    get_protocol(ProtocolId.BARNES)

    assert calls == [1]


def test_build_registry_refuses_generic_and_duplicates():
    generic = ProtocolSpec(
        protocol=ProtocolId.GENERIC, display_name=lambda: "", compute_metrics=lambda c: {}
    )
    barnes = _spec(lambda c: {})

    with pytest.raises(ValueError, match="generic"):
        registry._build_registry((generic,))
    with pytest.raises(ValueError, match="twice"):
        registry._build_registry((barnes, barnes))


def test_registered_specs_are_found(with_specs):
    spec = _spec(lambda c: {})
    with_specs(spec)

    assert get_protocol(ProtocolId.BARNES) is spec
    assert registered_protocols() == (ProtocolId.BARNES,)


def test_a_generic_profile_yields_exactly_status_none(with_specs):
    def must_not_run(context: ProtocolContext) -> dict[str, Any]:
        raise AssertionError("generic must not dispatch")

    with_specs(_spec(must_not_run))
    warnings: list[str] = []

    result = compute_protocol_metrics(_context(ExperimentProfile(), warnings))

    assert result == {"status": "none"}
    assert warnings == []


def test_an_unknown_declared_protocol_is_reported_as_such():
    profile = resolve_experiment_profile(behavioral_config={"protocol": "morris"})

    result = compute_protocol_metrics(_context(profile))

    assert result == {
        "status": "unavailable",
        "protocol": "morris",
        "version": None,
        "reason": "unknown_protocol",
    }


def test_a_known_protocol_without_a_spec_warns(with_specs):
    with_specs()
    warnings: list[str] = []

    result = compute_protocol_metrics(_context(_barnes(), warnings))

    assert result == {
        "status": "unavailable",
        "protocol": "barnes",
        "version": None,
        "reason": "unregistered",
    }
    assert len(warnings) == 1
    assert "barnes" in warnings[0]


def test_the_spec_receives_the_context_and_its_result_is_returned(with_specs):
    seen: list[ProtocolContext] = []
    produced = {"status": "ok", "protocol": "barnes", "version": 1, "reason": None, "x": 2}

    def compute(context: ProtocolContext) -> dict[str, Any]:
        seen.append(context)
        return produced

    with_specs(_spec(compute))
    context = _context(_barnes())

    assert compute_protocol_metrics(context) is produced
    assert seen == [context]


def test_a_raising_spec_becomes_an_error_entry_and_a_warning(with_specs):
    def compute(context: ProtocolContext) -> dict[str, Any]:
        raise RuntimeError("layout exploded")

    with_specs(_spec(compute))
    warnings: list[str] = []

    result = compute_protocol_metrics(_context(_barnes(), warnings))

    assert result == {
        "status": "error",
        "protocol": "barnes",
        "version": None,
        "reason": "exception",
        "error": "layout exploded",
    }
    assert len(warnings) == 1
    assert "layout exploded" in warnings[0]


@pytest.mark.parametrize(
    "returned",
    [
        None,
        ["status"],
        {"protocol": "barnes", "version": 1},
        {"status": "ok", "version": 1},
        {"status": "ok", "protocol": "barnes"},
    ],
)
def test_a_malformed_result_is_rejected(with_specs, returned):
    with_specs(_spec(lambda context: returned))
    warnings: list[str] = []

    result = compute_protocol_metrics(_context(_barnes(), warnings))

    assert result["status"] == "error"
    assert result["reason"] == "exception"
    assert result["error"] == "malformed result"
    assert len(warnings) == 1
