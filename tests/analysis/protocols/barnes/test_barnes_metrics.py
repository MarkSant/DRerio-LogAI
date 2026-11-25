"""``analysis/protocols/barnes/metrics.py`` — scripted Barnes trials end to end (#633).

Every trial starts with the rat in the start box at the table centre for 1 s; the
window START is at t = 1 s, so ``t_start_s == 1.0`` and every visit time below is
relative to it. Travel between points takes 1 s at 10 fps, so the rat reaches its
n-th hole at roughly ``1.6 * n - 0.6`` s after START.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd
import pytest
from tests.analysis.protocols.barnes.barnes_builders import (
    V1_SPEC,
    V2_SPEC,
    BarnesTable,
    FakeRoiAnalyzer,
    RatScript,
    make_context,
    window,
)

from zebtrack.analysis.analysis_window_service import WindowResolution
from zebtrack.analysis.protocols.barnes.contract import METRICS_KEYS, VISIT_FIELDS
from zebtrack.analysis.protocols.barnes.metrics import compute_barnes_metrics
from zebtrack.analysis.protocols.registry import compute_protocol_metrics

TABLE = BarnesTable()


def rat(*offsets: int, dwell_s: float = 0.6) -> RatScript:
    script = RatScript(TABLE.center).stay(1.0)
    for offset in offsets:
        script.poke(TABLE.hole_xy(offset), travel_s=1.0, dwell_s=dwell_s)
    return script


def entry_at(script: RatScript, t: float | None = None) -> WindowResolution:
    return window(1.0, script.t if t is None else t, reason="burrow_entry", spec=V2_SPEC)


def run(script: RatScript | pd.DataFrame, rois=None, **kwargs) -> tuple[dict[str, Any], list]:
    warnings: list[str] = []
    trajectory = script if isinstance(script, pd.DataFrame) else script.frame()
    context = make_context(
        trajectory, TABLE.rois() if rois is None else rois, warnings=warnings, **kwargs
    )
    return compute_barnes_metrics(context), warnings


def offsets(result: dict[str, Any]) -> list[int]:
    return [visit["offset"] for visit in result["visit_sequence"]]


def zeros(**counts: int) -> dict[int, int]:
    histogram = dict.fromkeys(range(11), 0)
    histogram.update({int(k[1:]): v for k, v in counts.items()})
    return histogram


# --- full trials, one per strategy ------------------------------------------


def test_direct_trial_with_an_entry_reads_like_the_protocol():
    script = rat(0, dwell_s=2.0)

    result, warnings = run(script, window=entry_at(script, 3.5), quadrant_s=1.25)

    assert tuple(result) == METRICS_KEYS
    assert result == {
        "status": "ok",
        "protocol": "barnes",
        "version": 1,
        "reason": None,
        "trial_type": "training",
        "n_holes": 20,
        "t_start_s": 1.0,
        "start_source": "window",
        "encounter_latency_s": pytest.approx(1.0),
        "encounter_censored": False,
        "entry_latency_s": pytest.approx(2.5),
        "entry_censored": False,
        "entry_source": "window",
        "primary_errors": 0,
        "total_errors": 0,
        "perseverative_errors": 0,
        "primary_path_length_cm": pytest.approx(150.0),
        "entry_path_length_cm": pytest.approx(150.0),
        "target_quadrant_time_s": 1.25,
        "target_quadrant_time_pct": pytest.approx(50.0),
        "visits_by_distance": zeros(d0=1),
        "visit_sequence": [
            {
                "order": 1,
                "roi": "toca",
                "offset": 0,
                "distance": 0,
                "t_enter_s": pytest.approx(1.0),
                "t_exit_s": None,
                "dwell_s": None,
                "is_target": True,
                "is_perseverative": False,
                "before_encounter": False,
            }
        ],
        "strategy": "direct",
        "strategy_source": "auto",
        "strategy_auto": "direct",
        "strategy_features": {
            "errors_before_target": 0,
            "center_crossings": 0,
            "adjacent_transition_fraction": None,
            "n_transitions": 0,
        },
        "probe_first_hole_offset": None,
        "probe_first_hole_score": None,
        "probe_first_error_latency_s": None,
        "probe_attempts_to_target": None,
    }
    assert tuple(result["visit_sequence"][0]) == VISIT_FIELDS
    assert warnings == []


def test_three_errors_without_crossing_the_centre_is_still_direct():
    script = rat(3, 2, 1, 0)

    result, _warnings = run(script, window=entry_at(script))

    assert offsets(result) == [3, 2, 1, 0]
    assert result["primary_errors"] == 3
    assert result["strategy"] == "direct"
    assert result["visits_by_distance"] == zeros(d0=1, d1=1, d2=1, d3=1)
    first = result["visit_sequence"][0]
    assert first["roi"] == "buraco_+03"
    assert first["t_enter_s"] == pytest.approx(1.0)
    assert first["t_exit_s"] == pytest.approx(1.9)
    assert first["dwell_s"] == pytest.approx(0.9)
    assert [v["before_encounter"] for v in result["visit_sequence"]] == [True] * 3 + [False]


def test_serial_trial_travels_the_rim_hole_by_hole():
    script = rat(5, 4, 3, 2, 1, 0)

    result, _warnings = run(script, window=entry_at(script))

    assert offsets(result) == [5, 4, 3, 2, 1, 0]
    assert result["primary_errors"] == 5
    assert result["total_errors"] == 5
    assert result["strategy_features"] == {
        "errors_before_target": 5,
        "center_crossings": 0,
        "adjacent_transition_fraction": 1.0,
        "n_transitions": 5,
    }
    assert result["strategy"] == result["strategy_auto"] == "serial"
    # Centre -> +5, four rim chords, then part of the last chord: the visit to the
    # target opens before the rat is centred on it (cover >= 0.3).
    chord = 2 * 150.0 * math.sin(math.pi / 20)
    assert 150.0 + 4 * chord < result["primary_path_length_cm"] < 150.0 + 5 * chord


def test_random_trial_crosses_the_centre_repeatedly():
    script = RatScript(TABLE.center).stay(1.0)
    script.poke(TABLE.hole_xy(5)).move(TABLE.center, 1.0)
    script.poke(TABLE.hole_xy(-6)).move(TABLE.center, 1.0)
    script.poke(TABLE.hole_xy(4)).poke(TABLE.hole_xy(0))

    result, _warnings = run(script, window=entry_at(script))

    assert offsets(result) == [5, -6, 4, 0]
    assert result["strategy_features"] == {
        "errors_before_target": 3,
        "center_crossings": 2,
        "adjacent_transition_fraction": 0.0,
        "n_transitions": 3,
    }
    assert result["strategy"] == "random"


def test_center_crossings_after_the_encounter_do_not_count():
    script = rat(1, 0).move(TABLE.center, 1.0).poke(TABLE.hole_xy(-1))

    result, _warnings = run(script, window=window(1.0, script.t, reason="delay", spec=V2_SPEC))

    assert offsets(result) == [1, 0, -1]
    assert result["strategy_features"]["center_crossings"] == 0
    # The search ends at the target: +1 -> toca is the only transition.
    assert result["strategy_features"]["n_transitions"] == 1
    assert result["strategy"] == "direct"
    assert result["primary_errors"] == 1
    assert result["total_errors"] == 2


def test_manual_strategy_correction_wins_and_is_marked():
    script = rat(0)

    result, _warnings = run(script, window=entry_at(script), inputs={"strategy_override": "random"})

    assert result["strategy"] == "random"
    assert result["strategy_source"] == "manual"
    assert result["strategy_auto"] == "direct"


# --- errors -------------------------------------------------------------------


def test_perseverative_errors_are_repeat_visits_to_a_decoy():
    script = rat(3, 2, 3, 0, 4, 5, 4)

    result, _warnings = run(script, window=window(1.0, script.t, reason="delay", spec=V2_SPEC))

    assert offsets(result) == [3, 2, 3, 0, 4, 5, 4]
    assert result["primary_errors"] == 3
    assert result["total_errors"] == 6
    assert result["perseverative_errors"] == 2
    assert [v["is_perseverative"] for v in result["visit_sequence"]] == [
        False,
        False,
        True,
        False,
        False,
        False,
        True,
    ]
    assert [v["order"] for v in result["visit_sequence"]] == [1, 2, 3, 4, 5, 6, 7]


def test_target_revisits_are_never_errors():
    result, _warnings = run(rat(0, 1, 0), window=window(1.0, 20.0, reason="delay", spec=V2_SPEC))

    assert offsets(result) == [0, 1, 0]
    assert [v["is_perseverative"] for v in result["visit_sequence"]] == [False] * 3
    assert result["visits_by_distance"] == zeros(d0=2, d1=1)


# --- censoring and timing ------------------------------------------------------


def test_censored_trial_without_target_nor_entry():
    script = rat(4, 5, 6)

    result, warnings = run(script, window=window(1.0, script.t, reason="delay", spec=V2_SPEC))

    assert result["encounter_latency_s"] == 240.0
    assert result["encounter_censored"] is True
    assert result["entry_latency_s"] == 240.0
    assert result["entry_censored"] is True
    assert result["entry_source"] == "censored"
    assert result["primary_errors"] == result["total_errors"] == 3
    assert result["primary_path_length_cm"] is None
    assert result["entry_path_length_cm"] is None
    assert all(v["before_encounter"] for v in result["visit_sequence"])
    assert result["strategy"] == "serial"
    assert warnings == []


def test_the_trial_ends_at_max_trial_s():
    script = rat(4, 5, 0)

    result, _warnings = run(
        script,
        window=window(1.0, script.t, reason="delay", spec=V2_SPEC),
        params={"max_trial_s": 3.0},
    )

    assert offsets(result) == [4, 5]
    assert result["encounter_latency_s"] == 3.0
    assert result["entry_latency_s"] == 3.0
    assert result["encounter_censored"] is True


def test_an_entry_after_the_ceiling_is_censored():
    script = rat(4, 5, 0)

    result, _warnings = run(script, window=entry_at(script), params={"max_trial_s": 3.0})

    assert script.t - 1.0 > 3.0
    assert result["entry_latency_s"] == 3.0
    assert result["entry_censored"] is True
    assert result["entry_source"] == "censored"
    assert result["entry_path_length_cm"] is None
    assert offsets(result) == [4, 5]
    assert result["total_errors"] == 2


def test_an_entry_exactly_at_the_ceiling_is_measured():
    script = rat(0, dwell_s=4.0)

    result, _warnings = run(script, window=entry_at(script, 4.0), params={"max_trial_s": 3.0})

    assert result["entry_latency_s"] == pytest.approx(3.0)
    assert result["entry_censored"] is False
    assert result["entry_source"] == "window"
    assert result["entry_path_length_cm"] == pytest.approx(150.0)


def test_a_visit_open_at_start_starts_at_start():
    script = RatScript(TABLE.hole_xy(2)).stay(1.5).move(TABLE.center, 1.0).poke(TABLE.hole_xy(0))

    result, _warnings = run(script, window=entry_at(script))

    first = result["visit_sequence"][0]
    assert first["roi"] == "buraco_+02"
    assert first["t_enter_s"] == 0.0
    assert result["primary_errors"] == 1


def test_without_a_window_the_trial_starts_at_the_first_detection():
    script = RatScript(TABLE.center).move(TABLE.hole_xy(0), 1.0).stay(0.5)

    result, warnings = run(script, window=None)

    assert result["t_start_s"] == 0.0
    assert result["start_source"] == "recording"
    assert result["encounter_latency_s"] == pytest.approx(1.0)
    assert result["entry_latency_s"] is None
    assert result["entry_censored"] is None
    assert result["entry_source"] == "unavailable"
    assert len(warnings) == 2
    assert "START" in warnings[0]
    assert "burrow_entry" in warnings[1]


def test_a_v1_window_cannot_detect_the_entry():
    script = rat(0)

    result, warnings = run(script, window=window(1.0, 2.0, reason="roi_edge", spec=V1_SPEC))

    assert result["entry_source"] == "unavailable"
    assert result["entry_latency_s"] is None
    assert warnings == [
        "The analysis window of this Barnes trial cannot detect the burrow entry (it has "
        "no burrow_entry stop); the entry latency was not measured."
    ]


# --- probe ---------------------------------------------------------------------


def test_probe_trial_scores_the_first_hole():
    # -5 -> 0 cuts across the table: no other hole on the way.
    script = rat(3, -5, 0)

    result, _warnings = run(
        script, window=window(1.0, script.t, reason="delay"), inputs={"trial_type": "probe"}
    )

    assert offsets(result) == [3, -5, 0]
    assert result["trial_type"] == "probe"
    assert result["entry_latency_s"] is None
    assert result["entry_censored"] is None
    assert result["entry_source"] == "not_applicable"
    assert result["probe_first_hole_offset"] == 3
    assert result["probe_first_hole_score"] == 4
    assert result["probe_first_error_latency_s"] == pytest.approx(1.0)
    assert result["probe_attempts_to_target"] == 3


def test_probe_that_goes_straight_to_the_target():
    result, _warnings = run(
        rat(0), window=window(1.0, 5.0, reason="delay"), params={"default_trial_type": "probe"}
    )

    assert result["trial_type"] == "probe"
    assert result["probe_first_hole_offset"] == 0
    assert result["probe_first_hole_score"] == 1
    assert result["probe_first_error_latency_s"] is None
    assert result["probe_attempts_to_target"] == 1


def test_probe_score_is_capped_and_the_target_may_never_be_found():
    script = rat(10, 9)
    probe_window = window(1.0, script.t, reason="delay")

    default_cap, _ = run(script, window=probe_window, inputs={"trial_type": "probe"})
    small_cap, _ = run(
        script, window=probe_window, inputs={"trial_type": "probe"}, params={"probe_score_cap": 5}
    )

    assert default_cap["visit_sequence"][0]["roi"] == "buraco_oposto"
    assert default_cap["probe_first_hole_offset"] == 10
    assert default_cap["probe_first_hole_score"] == 10
    assert default_cap["probe_attempts_to_target"] is None
    assert small_cap["probe_first_hole_score"] == 5


def test_probe_without_any_visit_has_no_probe_metric():
    script = RatScript(TABLE.center).stay(3.0)

    result, _warnings = run(
        script, window=window(1.0, 3.0, reason="delay"), inputs={"trial_type": "probe"}
    )

    assert result["visit_sequence"] == []
    assert result["probe_first_hole_offset"] is None
    assert result["probe_first_hole_score"] is None
    assert result["strategy"] is None
    assert result["strategy_source"] is None
    assert result["strategy_auto"] is None


def test_the_video_trial_type_overrides_the_project_default():
    result, _warnings = run(
        rat(0),
        window=entry_at(rat(0)),
        inputs={"trial_type": "training"},
        params={"default_trial_type": "probe"},
    )

    assert result["trial_type"] == "training"
    assert result["probe_first_hole_offset"] is None


# --- quadrant ------------------------------------------------------------------


def test_the_quadrant_is_measured_over_the_trial_not_the_window():
    script = rat(4, 5, 0)
    context = make_context(
        script.frame(),
        TABLE.rois(),
        window=window(1.0, script.t, reason="delay", spec=V2_SPEC),
        params={"max_trial_s": 3.0},
        quadrant_s=1.5,
    )

    result = compute_barnes_metrics(context)

    analyser = context.roi_analyzer
    assert isinstance(analyser, FakeRoiAnalyzer)
    assert analyser.spans == [(1.0, 4.0)]
    assert result["target_quadrant_time_s"] == 1.5
    assert result["target_quadrant_time_pct"] == pytest.approx(50.0)


def test_quadrant_share_of_a_recording_longer_than_the_trial_stays_a_share():
    """Real ROI analyser, no window, 300 s in the quadrant: 240 s, 100 %."""
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.settings import load_settings

    in_quadrant = TABLE.ring_xy(0, radius=100.0)
    script = RatScript(in_quadrant).stay(300.0)

    report, *_rest = AnalysisService(settings_obj=load_settings()).run_full_analysis(
        trajectory_df=script.frame(),
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=428,
        arena_polygon_px=TABLE.arena(),
        rois=TABLE.rois(),
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        behavioral_config={"protocol": "barnes"},
    )

    metrics = report["protocol_metrics"]
    whole = report["analise_roi"]["tempo_gasto_por_roi"]["quadrante_alvo"]["seconds"]
    assert whole == pytest.approx(300.0, abs=0.2)
    assert metrics["start_source"] == "recording"
    assert metrics["target_quadrant_time_s"] == pytest.approx(240.0, abs=0.2)
    assert 99.0 <= metrics["target_quadrant_time_pct"] <= 100.0


def test_without_the_quadrant_roi_the_quadrant_metrics_are_none():
    script = rat(0)

    no_roi, warnings = run(script, TABLE.rois(quadrant=False), window=entry_at(script))
    no_time, more = run(script, window=entry_at(script), quadrant_s=None)

    for result in (no_roi, no_time):
        assert result["status"] == "ok"
        assert result["target_quadrant_time_s"] is None
        assert result["target_quadrant_time_pct"] is None
    assert warnings == more
    assert warnings == [
        "The Barnes ROI quadrante_alvo is missing; the time in the target quadrant was "
        "not computed."
    ]


# --- refusals --------------------------------------------------------------------


def _unavailable(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "protocol": "barnes", "version": 1, "reason": reason}


def test_no_rois_is_refused():
    result, warnings = run(rat(0), rois=[], window=entry_at(rat(0)))

    assert result == _unavailable("no_rois")
    assert warnings == ["This video has no ROIs; the Barnes metrics need the hole ROIs."]


def test_duplicate_barnes_names_are_warned():
    from zebtrack.analysis.roi import ROI

    stray = ROI("toca", TABLE.rois()[1].geometry.buffer(0.0), "px")

    result, warnings = run(rat(0), [*TABLE.rois(), stray], window=entry_at(rat(0)))

    assert result["status"] == "ok"
    assert warnings == [
        "Several ROIs share the Barnes name(s) toca; the Barnes metrics use the first ROI "
        "of each name."
    ]


def test_visits_the_slowdown_filter_cannot_judge_are_warned():
    script = rat(3, 0)

    result, warnings = run(
        script,
        window=entry_at(script),
        params={"visit_max_speed_cm_s": 20.0},
        gap_threshold_s=0.05,
    )

    assert result["visit_sequence"] == []
    assert warnings == [
        "2 possible hole visit(s) were left out of the Barnes metrics: the slowdown filter "
        "(visit_max_speed_cm_s) could not measure the speed around them (tracking gaps)."
    ]


def test_missing_holes_are_named():
    result, warnings = run(rat(0), TABLE.rois(omit=("toca", "buraco_-03")))

    assert result == _unavailable("layout_unresolved")
    assert warnings == [
        "The Barnes metrics were not computed: hole ROIs missing or empty: toca, buraco_-03."
    ]


def test_a_degenerate_ring_is_refused():
    from shapely.geometry import Point

    from zebtrack.analysis.roi import ROI

    rois = [ROI(r.name, Point(5.0, 5.0).buffer(3.0), "px") for r in TABLE.rois(quadrant=False)]

    result, warnings = run(rat(0), rois)

    assert result == _unavailable("layout_unresolved")
    assert warnings == ["The Barnes metrics were not computed: the hole ROIs do not form a ring."]


def test_two_animals_are_refused():
    first = rat(0).frame()
    second = rat(3).frame().assign(track_id=2.0)

    result, warnings = run(pd.concat([first, second], ignore_index=True))

    assert result == _unavailable("multi_animal")
    assert warnings == ["The Barnes metrics need one animal per video; this trajectory has 2."]


def test_untracked_rows_are_one_unidentified_subject():
    result, _warnings = run(rat(0).frame().assign(track_id=float("nan")), window=entry_at(rat(0)))

    assert result["status"] == "ok"


@pytest.mark.parametrize(
    "case",
    ["empty_trajectory", "empty_window", "start_after_the_data", "start_equals_stop"],
)
def test_nothing_to_measure(case):
    script = rat(0)
    trajectory: pd.DataFrame = script.frame()
    resolved: WindowResolution | None = entry_at(script)
    if case == "empty_trajectory":
        trajectory = trajectory.iloc[0:0]
    elif case == "empty_window":
        resolved = WindowResolution(
            status="start_not_met", spec_hash="sha256:" + "c" * 64, on_start_not_met="empty"
        )
    elif case == "start_after_the_data":
        resolved = window(50.0, 60.0)
    else:
        resolved = window(2.0, 2.0)

    result, warnings = run(trajectory, window=resolved)

    assert result == _unavailable("no_trajectory")
    assert warnings == [
        "The Barnes trial has no detection to measure; the Barnes metrics were not computed."
    ]


def test_the_trial_with_a_single_detection_is_measured():
    script = RatScript(TABLE.center)

    result, _warnings = run(script, window=window(0.0, 0.0001, reason="delay"))

    assert result["status"] == "ok"
    assert result["visit_sequence"] == []


def test_bad_params_and_inputs_warn_and_fall_back():
    result, warnings = run(
        rat(0),
        window=entry_at(rat(0)),
        params={"n_holes": "many"},
        inputs={"trial_type": "exam", "strategy_override": "zigzag"},
    )

    assert result["status"] == "ok"
    assert result["n_holes"] == 20
    assert result["trial_type"] == "training"
    assert result["strategy_source"] == "auto"
    assert len(warnings) == 3
    assert "n_holes" in warnings[0]
    assert "trial_type" in warnings[1]
    assert "strategy_override" in warnings[2]


# --- serialisation and dispatch ---------------------------------------------------


def test_metrics_survive_a_json_round_trip():
    script = rat(3, 2, 3, 0)
    result, _warnings = run(script, window=entry_at(script))

    restored = json.loads(json.dumps(result))

    assert list(restored["visits_by_distance"]) == [str(d) for d in range(11)]
    assert restored["visits_by_distance"]["3"] == 2
    assert all(isinstance(key, int) for key in result["visits_by_distance"])
    assert restored["visit_sequence"][2]["is_perseverative"] is True
    for key in ("t_start_s", "encounter_latency_s", "entry_latency_s", "primary_path_length_cm"):
        assert type(result[key]) is float
    for key in ("primary_errors", "total_errors", "perseverative_errors", "n_holes"):
        assert type(result[key]) is int
    assert restored == json.loads(json.dumps(restored))


def test_the_registry_dispatches_barnes_to_these_metrics():
    script = rat(0)
    context = make_context(script.frame(), TABLE.rois(), window=entry_at(script))

    assert compute_protocol_metrics(context)["strategy"] == "direct"


def test_full_analysis_reports_the_barnes_metrics_with_the_report_rule():
    """Through ``AnalysisService``: the real hook, ROI analyser and gap threshold."""
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.settings import load_settings

    script = rat(3, 2, 1, 0, dwell_s=1.0)
    service = AnalysisService(settings_obj=load_settings())

    report, *_rest = service.run_full_analysis(
        trajectory_df=script.frame(),
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=428,
        arena_polygon_px=TABLE.arena(),
        rois=TABLE.rois(),
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        behavioral_config={"protocol": "barnes"},
        window=entry_at(script),
        protocol_inputs={"barnes": {"strategy_override": "serial"}},
    )

    metrics = report["protocol_metrics"]
    assert metrics["status"] == "ok"
    assert offsets(metrics) == [3, 2, 1, 0]
    assert metrics["strategy"] == "serial"
    assert metrics["strategy_source"] == "manual"
    quadrant = report["analise_roi"]["tempo_gasto_por_roi"]["quadrante_alvo"]["seconds"]
    assert quadrant > 0
    assert metrics["target_quadrant_time_s"] == quadrant
