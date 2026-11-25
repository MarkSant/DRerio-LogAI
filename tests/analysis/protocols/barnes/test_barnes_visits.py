"""``analysis/protocols/barnes/visits.py`` — nose pokes from the subject bbox (#633)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from tests.analysis.protocols.barnes.barnes_builders import BarnesTable, RatScript

from zebtrack.analysis.protocols.barnes.contract import BarnesParams
from zebtrack.analysis.protocols.barnes.layout import resolve_layout
from zebtrack.analysis.protocols.barnes.visits import (
    HoleVisit,
    VisitDetection,
    detect_hole_visits,
    path_length_cm,
    subject_samples,
    visits_in_trial,
)

TABLE = BarnesTable()
LAYOUT = resolve_layout(TABLE.rois(), TABLE.arena(), 20).layout
assert LAYOUT is not None


def _samples(script: RatScript, *, gap: float = math.inf, pixelcm: float = 1.0, **kwargs):
    return subject_samples(
        script.frame(**kwargs), pixelcm_x=pixelcm, pixelcm_y=pixelcm, gap_threshold_s=gap
    )


def _detect(script: RatScript, **params) -> VisitDetection:
    assert LAYOUT is not None
    return detect_hole_visits(_samples(script), LAYOUT.holes, BarnesParams(**params))


def _visits(script: RatScript, **params) -> list[HoleVisit]:
    return _detect(script, **params).visits


def _from_center() -> RatScript:
    return RatScript(TABLE.center).stay(1.0)


# --- samples -----------------------------------------------------------------


def test_one_sample_per_timestamp_keeps_the_best_detection():
    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.0, 0.1, 0.1, 0.2, 0.3],
            "frame": [0, 0, 1, 1, 2, 3],
            "track_id": np.nan,
            "x1": [0.0, 10.0, 0.0, 20.0, np.nan, 30.0],
            "y1": [0.0, 10.0, 0.0, 20.0, 0.0, 30.0],
            "x2": [4.0, 14.0, 4.0, 30.0, 4.0, 34.0],
            "y2": [4.0, 14.0, 4.0, 30.0, 4.0, 34.0],
            "confidence": [0.5, 0.9, 0.7, 0.7, 0.9, 0.8],
        }
    )

    samples = subject_samples(df, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=math.inf)

    assert samples.t_s.tolist() == [0.0, 0.1, 0.3]
    # t=0: higher confidence; t=0.1: confidence tie -> larger box; t=0.2: NaN bbox
    assert samples.x1.tolist() == [10.0, 20.0, 30.0]
    assert samples.cx.tolist() == [12.0, 25.0, 32.0]
    # Steps 1 and 2 -> median 1.5: no frame is called missing on 3 samples.
    assert samples.missing_before.tolist() == [0, 0, 0]


def test_missing_frames_use_the_median_frame_step():
    regular = RatScript((0.0, 0.0)).stay(0.4).vanish(0.1).stay(0.1).frame()
    interval_10 = regular.assign(frame=[0, 10, 20, 21, 31, 51])

    def missing(df: pd.DataFrame) -> list[int]:
        found = subject_samples(df, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=math.inf)
        return found.missing_before.tolist()

    # Frames 0..4 then 6: one processed frame without a detection before the last.
    assert missing(regular) == [0, 0, 0, 0, 0, 1]
    # A 10-frame analysis interval with ONE odd adjacent pair (20, 21): the median
    # step stays 10, so only the 20-frame jump hides one processed frame. The
    # smallest step (1) would have called nine frames missing at every interval.
    assert missing(interval_10) == [0, 0, 0, 0, 0, 1]


def test_recorded_centres_win_over_the_bbox_centre():
    script = RatScript((50.0, 60.0)).move((80.0, 60.0), 0.3)

    samples = _samples(script, with_center_columns=True)
    df = script.frame()
    df["x_center_px"] = [1.0, np.nan, 3.0, 4.0]
    df["y_center_px"] = 2.0
    mixed = subject_samples(df, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=math.inf)

    assert samples.cx.tolist() == pytest.approx([50.0, 60.0, 70.0, 80.0])
    assert mixed.cx.tolist() == pytest.approx([1.0, 60.0, 3.0, 4.0])
    assert mixed.cy.tolist() == pytest.approx([2.0, 60.0, 2.0, 2.0])


def test_missing_frames_come_from_the_timestamps_without_a_frame_column():
    df = RatScript((0.0, 0.0)).stay(0.2).vanish(0.3).stay(0.1).frame().drop(columns="frame")

    samples = subject_samples(df, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=math.inf)

    assert samples.missing_before.tolist() == [0, 0, 0, 3]


def test_an_empty_or_columnless_trajectory_has_no_sample():
    assert len(subject_samples(pd.DataFrame(), pixelcm_x=1, pixelcm_y=1, gap_threshold_s=1)) == 0
    no_bbox = pd.DataFrame({"timestamp": [0.0], "x1": [1.0]})
    assert len(subject_samples(no_bbox, pixelcm_x=1, pixelcm_y=1, gap_threshold_s=1)) == 0


def test_speed_is_in_cm_per_second_and_breaks_at_gaps():
    script = RatScript((0.0, 0.0)).move((40.0, 0.0), 0.4).vanish(1.0).move((60.0, 0.0), 0.1)
    script.move((80.0, 0.0), 0.1).vanish(1.0).move((90.0, 0.0), 0.1)

    samples = _samples(script, gap=0.5, pixelcm=2.0)

    # 10 px per 0.1 s at 2 px/cm = 50 cm/s; the first sample takes the forward step.
    assert samples.speed_cm_s[:5].tolist() == pytest.approx([50.0] * 5)
    # 1.1 s gap > 0.5 s threshold: the jump has no speed; the next sample's
    # forward step (20 px per 0.1 s) is used instead.
    assert samples.speed_cm_s[5] == pytest.approx(100.0)
    # An isolated sample (gaps on both sides) has no speed at all.
    assert np.isnan(samples.speed_cm_s[7])
    no_calibration = _samples(script, pixelcm=0.0)
    assert np.isnan(no_calibration.speed_cm_s).all()


# --- visits ------------------------------------------------------------------


def test_a_poke_is_one_visit_with_back_dated_edges():
    script = _from_center().poke(TABLE.hole_xy(3), travel_s=1.0, dwell_s=0.6)
    script.move(TABLE.center, 1.0)

    visits = _visits(script)

    assert [(v.roi, v.offset) for v in visits] == [("buraco_+03", 3)]
    assert visits[0].t_enter_s == pytest.approx(2.0)
    assert visits[0].t_exit_s == pytest.approx(2.7)


def test_the_enter_debounce_needs_consecutive_covered_frames():
    hole = TABLE.hole_xy(-5)
    near = TABLE.ring_xy(-5, radius=125.0)
    touch = _from_center().move(near, 1.0).move(hole, 0.1).move(near, 0.1).stay(1.0)

    assert _visits(touch) == []
    assert [v.roi for v in _visits(touch, visit_enter_frames=1)] == ["buraco_-05"]


@pytest.mark.parametrize(("away_s", "expected"), [(0.2, 1), (0.3, 2)])
def test_the_exit_debounce_merges_short_absences(away_s, expected):
    hole = TABLE.hole_xy(4)
    away = TABLE.ring_xy(4, radius=120.0)
    script = _from_center().poke(hole).move(away, 0.1).stay(away_s - 0.1).move(hole, 0.1)
    script.stay(0.6).move(TABLE.center, 1.0)

    assert len(_visits(script)) == expected


@pytest.mark.parametrize(("hidden_s", "expected"), [(0.2, 1), (0.3, 2)])
def test_frames_without_a_detection_count_as_uncovered(hidden_s, expected):
    hole = TABLE.hole_xy(-2)
    script = _from_center().poke(hole).vanish(hidden_s).stay(0.6).move(TABLE.center, 1.0)

    visits = _visits(script)

    assert len(visits) == expected
    if expected == 2:
        assert visits[0].t_exit_s == pytest.approx(2.7)


def test_a_rat_walking_along_the_rim_pokes_nothing():
    """Bbox 15 px outside the ring: about 20 % of each hole covered, below 0.3."""
    script = RatScript(TABLE.ring_xy(-6, radius=165.0))
    for step in range(-5, 7):
        script.move(TABLE.ring_xy(step, radius=165.0), 0.5)

    assert _visits(script) == []
    assert _visits(script, visit_min_cover=0.15) == []  # one frame per hole only
    assert len(_visits(script, visit_min_cover=0.15, visit_enter_frames=1)) == 13


def test_the_slowdown_filter_drops_a_run_over_a_hole():
    hole = TABLE.hole_xy(6)
    before = TABLE.ring_xy(5.5, radius=150.0)
    after = TABLE.ring_xy(6.5, radius=150.0)
    run = RatScript(before).move(after, 0.3).move(TABLE.center, 1.0)
    poke = RatScript(before).move(hole, 0.3).stay(0.6).move(TABLE.center, 1.0)

    assert len(_visits(run)) == 1
    assert _visits(run, visit_max_speed_cm_s=20.0) == []
    # Too fast is a judgement, not a measurement failure: nothing to report.
    assert _detect(run, visit_max_speed_cm_s=20.0).unmeasured == []
    assert len(_visits(poke, visit_max_speed_cm_s=20.0)) == 1


def test_a_candidate_without_any_measurable_speed_is_reported_not_lost():
    assert LAYOUT is not None
    script = RatScript(TABLE.ring_xy(5.5)).move(TABLE.hole_xy(6), 0.3).stay(0.6)
    script.move(TABLE.center, 1.0)
    # Every step is longer than the gap threshold: no speed anywhere.
    samples = _samples(script, gap=0.05)

    filtered = detect_hole_visits(samples, LAYOUT.holes, BarnesParams(visit_max_speed_cm_s=20.0))
    unfiltered = detect_hole_visits(samples, LAYOUT.holes, BarnesParams())

    assert filtered.visits == []
    assert [(v.roi, v.offset) for v in filtered.unmeasured] == [("buraco_+06", 6)]
    # The reported candidate is exactly the visit the filter-less detection finds.
    assert filtered.unmeasured == unfiltered.visits
    assert unfiltered.unmeasured == []


def test_a_visit_open_at_the_end_has_no_exit():
    script = _from_center().poke(TABLE.hole_xy(0), dwell_s=2.0)

    visits = _visits(script)

    assert [(v.roi, v.t_exit_s) for v in visits] == [("toca", None)]
    assert visits[0].t_enter_s == pytest.approx(2.0)


def test_visits_are_sorted_by_start_then_offset():
    script = _from_center().poke(TABLE.hole_xy(5)).poke(TABLE.hole_xy(-5)).poke(TABLE.hole_xy(5))

    assert [v.offset for v in _visits(script)] == [5, -5, 5]


# --- trial cut ---------------------------------------------------------------


def test_visits_in_trial_clamps_filters_and_reopens():
    visits = [
        HoleVisit("buraco_+01", 1, 0.0, 0.9),  # closed before t0
        HoleVisit("buraco_+02", 2, 0.5, 1.0),  # closes exactly at t0
        HoleVisit("buraco_+03", 3, 0.8, 1.5),  # open at t0 -> starts at t0
        HoleVisit("buraco_+04", 4, 2.0, None),  # open at the end of the recording
        HoleVisit("toca", 0, 3.0, 5.5),  # exits after the trial end
        HoleVisit("buraco_-01", -1, 5.0, 5.2),  # starts at the trial end
        HoleVisit("buraco_-02", -2, 0.2, None),  # open since before t0, never closes
    ]

    counted = visits_in_trial(visits, t0=1.0, trial_end=5.0)

    assert counted == [
        HoleVisit("buraco_-02", -2, 1.0, None),
        HoleVisit("buraco_+03", 3, 1.0, 1.5),
        HoleVisit("buraco_+04", 4, 2.0, None),
        HoleVisit("toca", 0, 3.0, None),
    ]


def test_visits_in_trial_keeps_an_exit_at_the_trial_end():
    assert visits_in_trial([HoleVisit("toca", 0, 2.0, 5.0)], 1.0, 5.0) == [
        HoleVisit("toca", 0, 2.0, 5.0)
    ]


# --- path --------------------------------------------------------------------


def test_path_length_in_cm_between_two_instants():
    script = RatScript((0.0, 0.0)).move((60.0, 80.0), 1.0).move((60.0, 0.0), 1.0)
    samples = _samples(script)

    assert path_length_cm(samples, 0.0, 1.0, pixelcm_x=2.0, pixelcm_y=2.0, gap_threshold_s=1.0) == (
        pytest.approx(50.0)
    )
    assert path_length_cm(
        samples, 0.0, 2.0, pixelcm_x=1.0, pixelcm_y=2.0, gap_threshold_s=1.0
    ) == pytest.approx(math.hypot(60.0, 40.0) + 40.0)
    assert path_length_cm(samples, 0.5, 0.5, pixelcm_x=1, pixelcm_y=1, gap_threshold_s=1) == 0.0
    assert path_length_cm(samples, 0.0, 1.0, pixelcm_x=0, pixelcm_y=1, gap_threshold_s=1) is None
    assert (
        path_length_cm(samples, 0.0, 1.0, pixelcm_x=math.inf, pixelcm_y=1, gap_threshold_s=1)
        is None
    )


def test_path_length_skips_jumps_across_long_gaps():
    script = RatScript((0.0, 0.0)).move((10.0, 0.0), 0.1).vanish(1.0).move((110.0, 0.0), 0.1)
    samples = _samples(script)

    assert path_length_cm(
        samples, 0.0, 5.0, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=0.5
    ) == pytest.approx(10.0)
    assert path_length_cm(
        samples, 0.0, 5.0, pixelcm_x=1.0, pixelcm_y=1.0, gap_threshold_s=2.0
    ) == pytest.approx(110.0)
