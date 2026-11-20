"""``analysis/protocols/base.py`` — report-shape helpers and per-video inputs (ADR-014)."""

from __future__ import annotations

import pytest

from zebtrack.analysis.protocols.base import (
    PROTOCOL_INPUTS_KEY,
    PROTOCOL_METRICS_KEY,
    GenericReportSection,
    ProtocolSpec,
    ProtocolStatus,
    UnavailableReason,
    clear_protocol_input,
    none_metrics,
    protocol_inputs_for,
    protocol_inputs_of_entry,
    set_protocol_input,
    unavailable_metrics,
)
from zebtrack.core.services.experiment_profile import ProtocolId


def test_the_persisted_tokens_are_frozen():
    assert PROTOCOL_METRICS_KEY == "protocol_metrics"
    assert PROTOCOL_INPUTS_KEY == "protocol_inputs"
    assert [s.value for s in ProtocolStatus] == ["none", "ok", "unavailable", "error"]
    assert [r.value for r in UnavailableReason] == [
        "unknown_protocol",
        "unregistered",
        "no_rois",
        "layout_unresolved",
        "multi_animal",
        "multi_aquarium",
        "no_trajectory",
        "exception",
    ]
    assert [s.value for s in GenericReportSection] == ["thigmotaxis", "geotaxis"]


def test_none_metrics_is_exactly_the_generic_shape_and_never_shared():
    first = none_metrics()
    first["status"] = "mutated"

    assert none_metrics() == {"status": "none"}


def test_unavailable_metrics_shape():
    assert unavailable_metrics("barnes", UnavailableReason.NO_ROIS) == {
        "status": "unavailable",
        "protocol": "barnes",
        "version": None,
        "reason": "no_rois",
    }


def test_unavailable_metrics_with_an_error_and_a_version():
    result = unavailable_metrics(
        "barnes",
        UnavailableReason.EXCEPTION,
        version=1,
        status=ProtocolStatus.ERROR,
        error="boom",
    )

    assert result == {
        "status": "error",
        "protocol": "barnes",
        "version": 1,
        "reason": "exception",
        "error": "boom",
    }


@pytest.mark.parametrize(
    "entry",
    [None, {}, {"protocol_inputs": None}, {"protocol_inputs": ["barnes"]}, "entry"],
)
def test_an_entry_without_inputs_has_none(entry):
    assert dict(protocol_inputs_of_entry(entry)) == {}


def test_inputs_of_entry_keep_mapping_blocks_only():
    entry = {"protocol_inputs": {"barnes": {"trial_type": "probe"}, "broken": 3}}

    inputs = protocol_inputs_of_entry(entry)

    assert {name: dict(block) for name, block in inputs.items()} == {
        "barnes": {"trial_type": "probe"}
    }


def test_inputs_of_entry_are_a_read_only_copy():
    block = {"trial_type": "probe"}
    entry = {"protocol_inputs": {"barnes": block}}

    inputs = protocol_inputs_of_entry(entry)
    block["trial_type"] = "training"

    assert inputs["barnes"]["trial_type"] == "probe"
    with pytest.raises(TypeError):
        inputs["barnes"]["trial_type"] = "x"  # type: ignore[index]


def test_inputs_for_selects_the_protocols_block():
    inputs = {"barnes": {"trial_type": "probe"}, "generic": {"a": 1}}

    assert dict(protocol_inputs_for(inputs, ProtocolId.BARNES)) == {"trial_type": "probe"}
    assert dict(protocol_inputs_for(inputs, ProtocolId.GENERIC)) == {"a": 1}


@pytest.mark.parametrize("inputs", [None, {}, {"barnes": "probe"}, ["barnes"]])
def test_inputs_for_degrades_to_empty(inputs):
    assert dict(protocol_inputs_for(inputs, ProtocolId.BARNES)) == {}


def test_set_protocol_input_creates_the_blocks():
    entry: dict = {"path": "v.mp4"}

    set_protocol_input(entry, ProtocolId.BARNES, "trial_type", "probe")

    assert entry == {"path": "v.mp4", "protocol_inputs": {"barnes": {"trial_type": "probe"}}}


def test_set_protocol_input_keeps_other_keys_and_replaces_malformed_blocks():
    entry: dict = {"protocol_inputs": {"barnes": "garbage", "other": {"k": 1}}}

    set_protocol_input(entry, ProtocolId.BARNES, "strategy_override", "serial")
    set_protocol_input(entry, ProtocolId.BARNES, "trial_type", "training")

    assert entry["protocol_inputs"] == {
        "barnes": {"strategy_override": "serial", "trial_type": "training"},
        "other": {"k": 1},
    }


def test_set_protocol_input_replaces_a_malformed_top_level():
    entry: dict = {"protocol_inputs": ["x"]}

    set_protocol_input(entry, ProtocolId.BARNES, "trial_type", "probe")

    assert entry["protocol_inputs"] == {"barnes": {"trial_type": "probe"}}


def test_clear_protocol_input_removes_empty_blocks():
    entry: dict = {"path": "v.mp4"}
    set_protocol_input(entry, ProtocolId.BARNES, "trial_type", "probe")
    set_protocol_input(entry, ProtocolId.BARNES, "strategy_override", "direct")

    clear_protocol_input(entry, ProtocolId.BARNES, "trial_type")
    assert entry["protocol_inputs"] == {"barnes": {"strategy_override": "direct"}}

    clear_protocol_input(entry, ProtocolId.BARNES, "strategy_override")
    assert entry == {"path": "v.mp4"}


def test_clear_protocol_input_keeps_other_protocols():
    entry: dict = {"protocol_inputs": {"barnes": {"trial_type": "probe"}, "other": {"k": 1}}}

    clear_protocol_input(entry, ProtocolId.BARNES, "trial_type")

    assert entry == {"protocol_inputs": {"other": {"k": 1}}}


def test_clear_protocol_input_on_an_entry_without_inputs_is_a_no_op():
    entry: dict = {"path": "v.mp4"}

    clear_protocol_input(entry, ProtocolId.BARNES, "trial_type")
    clear_protocol_input(entry, ProtocolId.BARNES, "missing")

    assert entry == {"path": "v.mp4"}


def test_clear_protocol_input_of_a_missing_key_keeps_the_block():
    entry: dict = {"protocol_inputs": {"barnes": {"trial_type": "probe"}}}

    clear_protocol_input(entry, ProtocolId.BARNES, "strategy_override")

    assert entry == {"protocol_inputs": {"barnes": {"trial_type": "probe"}}}


def test_a_spec_declares_no_columns_sections_or_assistant_by_default():
    spec = ProtocolSpec(
        protocol=ProtocolId.BARNES,
        display_name=lambda: "Barnes",
        compute_metrics=lambda context: {},
    )

    assert spec.tidy_columns({"n_holes": 20}) == ()
    assert spec.suppressed_report_sections == frozenset()
    assert spec.window_preset is None
    assert spec.zone_assistant is None
    assert spec.display_name() == "Barnes"
