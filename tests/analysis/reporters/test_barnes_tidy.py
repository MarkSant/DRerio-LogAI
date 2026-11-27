"""``barnes_*`` tidy columns (CONTRACTS section 8): present for Barnes, absent otherwise."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from tests.analysis.reporters.barnes_report_builders import (
    BARNES_CONFIG,
    N_HOLES,
    barnes_context,
    scripted_rat,
)

from zebtrack.analysis.data_transformer import (
    DISPLAY_COLUMN_MAPPING,
    WINDOW_COLUMNS,
    DataTransformer,
    barnes_columns,
)
from zebtrack.analysis.protocols.barnes.contract import barnes_tidy_columns


def _expected_columns() -> tuple[str, ...]:
    return barnes_tidy_columns(N_HOLES)


def test_a_barnes_project_gets_every_barnes_column_after_the_window_columns():
    context = barnes_context(scripted_rat(3, 2, 0))

    columns = list(context.tidy_data.columns)

    barnes = [c for c in columns if c.startswith("barnes_")]
    assert tuple(barnes) == _expected_columns()
    assert columns[-len(barnes) :] == barnes
    last_window = max(columns.index(c) for c in WINDOW_COLUMNS)
    assert columns.index(barnes[0]) == last_window + 1


def test_the_columns_carry_the_protocol_metrics_of_the_report():
    context = barnes_context(scripted_rat(3, 2, 0))
    row = context.tidy_data.iloc[0]
    metrics = context.report["protocol_metrics"]

    assert metrics["status"] == "ok"
    assert row["barnes_status"] == "ok"
    assert row["barnes_trial_type"] == "training"
    assert row["barnes_primary_errors"] == metrics["primary_errors"] == 2
    assert row["barnes_total_errors"] == metrics["total_errors"]
    assert row["barnes_encounter_latency_s"] == pytest.approx(metrics["encounter_latency_s"])
    assert bool(row["barnes_encounter_censored"]) is False
    assert row["barnes_strategy"] == metrics["strategy"]
    assert row["barnes_strategy_source"] == "auto"
    assert row["barnes_strategy_auto"] == metrics["strategy_auto"]
    assert row["barnes_center_crossings"] == metrics["strategy_features"]["center_crossings"]
    # one column per hole distance, from the in-memory int-keyed histogram
    assert row["barnes_visits_d03"] == metrics["visits_by_distance"][3] == 1
    assert row["barnes_visits_d02"] == metrics["visits_by_distance"][2] == 1
    assert row["barnes_visits_d00"] == metrics["visits_by_distance"][0] == 1
    assert row["barnes_visits_d09"] == 0


def test_probe_columns_are_empty_in_training_and_set_in_a_probe():
    training = barnes_context(scripted_rat(2, 0)).tidy_data.iloc[0]
    probe = barnes_context(
        scripted_rat(2, 0), protocol_inputs={"barnes": {"trial_type": "probe"}}
    ).tidy_data.iloc[0]

    for column in (
        "barnes_probe_first_hole_offset",
        "barnes_probe_first_hole_score",
        "barnes_probe_first_error_latency_s",
        "barnes_probe_attempts_to_target",
    ):
        assert pd.isna(training[column])
    assert probe["barnes_trial_type"] == "probe"
    assert probe["barnes_probe_first_hole_offset"] == 2
    assert probe["barnes_probe_first_hole_score"] == 3
    assert probe["barnes_probe_attempts_to_target"] == 2
    # a probe has no escape box: the entry is not applicable, and it is NOT zero
    assert pd.isna(probe["barnes_entry_latency_s"])
    assert probe["barnes_entry_source"] == "not_applicable"


def test_a_manual_strategy_is_marked_in_the_columns():
    context = barnes_context(
        scripted_rat(3, 2, 0), protocol_inputs={"barnes": {"strategy_override": "random"}}
    )

    row = context.tidy_data.iloc[0]

    assert row["barnes_strategy"] == "random"
    assert row["barnes_strategy_source"] == "manual"
    assert row["barnes_strategy_auto"] == context.report["protocol_metrics"]["strategy_auto"]


def test_a_generic_project_gets_no_barnes_column_and_the_same_columns_as_before():
    generic = barnes_context(
        scripted_rat(0), behavioral_config={"aquarium_perspective": "top_down"}
    )

    columns = list(generic.tidy_data.columns)

    assert generic.report["protocol_metrics"] == {"status": "none"}
    assert not [c for c in columns if c.startswith("barnes_")]
    assert columns[-len(WINDOW_COLUMNS) :] == list(WINDOW_COLUMNS)


def test_an_unavailable_barnes_report_keeps_the_schema_and_fills_only_the_status():
    context = barnes_context(
        scripted_rat(0),
        behavioral_config={**BARNES_CONFIG, "protocol_params": {"barnes": {"n_holes": N_HOLES}}},
        extra_metadata={},
    )
    report = {
        "protocol_metrics": {"status": "unavailable", "protocol": "barnes", "reason": "no_rois"}
    }

    values = barnes_columns(report, context.behavioral_config)

    assert tuple(values) == _expected_columns()
    assert values["barnes_status"] == "unavailable"
    assert all(v is None for k, v in values.items() if k != "barnes_status")


def test_an_errored_report_that_knows_its_trial_type_keeps_it():
    values = barnes_columns(
        {"protocol_metrics": {"status": "error", "trial_type": "probe"}}, BARNES_CONFIG
    )

    assert values["barnes_status"] == "error"
    assert values["barnes_trial_type"] == "probe"
    assert values["barnes_total_errors"] is None


def test_visits_by_distance_resolves_int_and_str_keys_and_missing_means_zero_when_ok():
    metrics = {
        "status": "ok",
        "visits_by_distance": {"3": 2, "0": 1},  # a JSON round trip: str keys
        "strategy_features": {},
    }

    from_json = barnes_columns({"protocol_metrics": metrics}, BARNES_CONFIG)
    from_memory = barnes_columns(
        {"protocol_metrics": {**metrics, "visits_by_distance": {3: 2, 0: 1}}}, BARNES_CONFIG
    )

    for values in (from_json, from_memory):
        assert values["barnes_visits_d03"] == 2
        assert values["barnes_visits_d00"] == 1
        assert values["barnes_visits_d05"] == 0
    assert from_json == from_memory


def test_a_none_latency_is_never_rendered_as_zero():
    metrics: dict[str, Any] = {
        "status": "ok",
        "entry_latency_s": None,
        "entry_censored": None,
        "visits_by_distance": {},
        "strategy_features": {},
    }

    values = barnes_columns({"protocol_metrics": metrics}, BARNES_CONFIG)

    assert values["barnes_entry_latency_s"] is None
    assert values["barnes_entry_censored"] is None


def test_the_columns_follow_the_project_hole_count():
    config = {**BARNES_CONFIG, "protocol_params": {"barnes": {"n_holes": 20}}}

    values = barnes_columns({"protocol_metrics": {"status": "ok"}}, config)

    assert "barnes_visits_d10" in values
    assert tuple(values) == barnes_tidy_columns(20)


def test_unknown_or_unregistered_protocols_add_nothing():
    assert barnes_columns({"protocol_metrics": {"status": "none"}}, None) == {}
    assert barnes_columns({}, {"protocol": "no_such_protocol"}) == {}


def test_every_scalar_column_and_the_distance_columns_have_a_display_name():
    transformer = DataTransformer()
    frame = pd.DataFrame([dict.fromkeys(_expected_columns(), 1)])

    shown = transformer.prepare_for_display(frame)

    assert next(iter(shown.columns)) == DISPLAY_COLUMN_MAPPING["barnes_status"]
    assert "Barnes Visits at Distance 3" in shown.columns
    assert not any(c.startswith("barnes_") for c in shown.columns)
    assert len(set(shown.columns)) == len(shown.columns)
