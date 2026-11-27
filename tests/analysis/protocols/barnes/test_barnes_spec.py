"""``analysis/protocols/barnes/spec.py`` — the registered Barnes spec (#633)."""

from __future__ import annotations

import json

from zebtrack import i18n
from zebtrack.analysis.protocols.barnes.contract import (
    ASSISTANT_ID,
    BarnesParams,
    barnes_tidy_columns,
)
from zebtrack.analysis.protocols.barnes.metrics import compute_barnes_metrics
from zebtrack.analysis.protocols.barnes.spec import BARNES_SPEC, barnes_window_preset
from zebtrack.analysis.protocols.base import GenericReportSection
from zebtrack.core.conditions.presets import barnes_maze_preset_v2
from zebtrack.core.services.experiment_profile import ProtocolId


def test_the_spec_declares_what_the_contract_says():
    assert BARNES_SPEC.protocol is ProtocolId.BARNES
    assert BARNES_SPEC.compute_metrics is compute_barnes_metrics
    assert BARNES_SPEC.suppressed_report_sections == frozenset(
        {GenericReportSection.THIGMOTAXIS, GenericReportSection.GEOTAXIS}
    )
    assert BARNES_SPEC.zone_assistant == ASSISTANT_ID
    assert BARNES_SPEC.window_preset is not None


def _dump(spec) -> dict:
    return spec.model_dump(mode="json", by_alias=True)


def test_window_preset_is_v2_with_the_default_params():
    preset = BARNES_SPEC.window_preset
    assert preset is not None

    window = preset({})

    assert _dump(window) == _dump(barnes_maze_preset_v2())
    assert "burrow_entry" in json.dumps(_dump(window))


def test_window_preset_reads_the_trial_ceiling_and_the_entry_thresholds():
    raw = {
        "max_trial_s": 120.0,
        "entry_min_cover": 0.6,
        "entry_max_visible_fraction": 0.25,
        "entry_hold_s": 1.0,
        "entry_absent_s": 2.0,
        "entry_min_reference_frames": 15,
        "n_holes": 20,
    }
    preset = BARNES_SPEC.window_preset
    assert preset is not None

    window = preset(raw)

    assert _dump(window) == _dump(
        barnes_maze_preset_v2(
            max_s=120.0,
            entry_min_cover=0.6,
            entry_max_visible_fraction=0.25,
            entry_hold_s=1.0,
            entry_absent_s=2.0,
            entry_min_reference_frames=15,
        )
    )
    # A bad value falls back to its default instead of raising.
    assert _dump(preset({"max_trial_s": "long"})) == _dump(barnes_maze_preset_v2())


def test_barnes_window_preset_keeps_the_overrides_of_a_v1_update():
    params = BarnesParams(n_holes=18, max_trial_s=200.0, entry_hold_s=0.8)

    window = barnes_window_preset(params, k_frames=7, max_s=60.0, burrow_roi="Toca")

    assert _dump(window) == _dump(
        barnes_maze_preset_v2(k_frames=7, max_s=60.0, burrow_roi="Toca", entry_hold_s=0.8)
    )
    assert _dump(barnes_window_preset(params)) == _dump(
        barnes_maze_preset_v2(max_s=200.0, entry_hold_s=0.8)
    )


def test_tidy_columns_follow_the_project_hole_count():
    # Default: the lab's 18-hole table, d00 (target) .. d09 (opposite).
    assert BARNES_SPEC.tidy_columns({}) == barnes_tidy_columns(18)
    assert BARNES_SPEC.tidy_columns({})[-1] == "barnes_visits_d09"
    assert BARNES_SPEC.tidy_columns({"n_holes": 20}) == barnes_tidy_columns(20)
    assert BARNES_SPEC.tidy_columns({"n_holes": 12}) == barnes_tidy_columns(12)
    assert BARNES_SPEC.tidy_columns({"n_holes": 12})[-1] == "barnes_visits_d06"
    # A bad value falls back to the default instead of raising.
    assert BARNES_SPEC.tidy_columns({"n_holes": "x"}) == barnes_tidy_columns(18)


def test_display_name_is_translated_at_call_time():
    previous = i18n.get_language()
    try:
        i18n.install("en")
        assert BARNES_SPEC.display_name() == "Barnes maze"
        i18n.install("pt_BR")
        assert BARNES_SPEC.display_name() == "Labirinto de Barnes"
    finally:
        i18n.install(previous)
