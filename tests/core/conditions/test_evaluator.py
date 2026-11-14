"""Tests for the analysis-window evaluator (ADR-011, ``core/conditions/evaluator.py``).

Three layers:

- unit tests, one behaviour per node, on hand-written streams whose expected
  instants can be read off the page;
- the Barnes protocol on a VFR stream (98-142 ms between frames), the case that
  motivated the engine: START must land on the first frame of the valid run,
  STOP must be back-dated, and the 240 s ceiling must be the instant it claims;
- hypothesis properties over random specs and random streams: batch is the same
  fold as online, chunking and reading ``result`` mid-stream change nothing,
  back-dated instants never lie in the future, STOP never precedes START and
  duplicated frames do not speed up a hold measured in seconds.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Iterable, Mapping
from typing import Literal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from zebtrack.core.conditions import (
    AllOf,
    AllOfLevel,
    AnyOfLevel,
    ClassPresence,
    ClassTarget,
    ConditionEvaluator,
    Delay,
    EndOfStream,
    External,
    ExternalEvent,
    FirstOf,
    FrameObservation,
    FrameReached,
    Hold,
    Not,
    Persist,
    RoiEdge,
    RoiInside,
    Sequence,
    TimeReached,
    WindowEvent,
    WindowResult,
    WindowSpec,
    evaluate_window,
)

ROLES: Mapping[str, frozenset[str]] = {
    "subject": frozenset({"rat"}),
    "context": frozenset({"experimenter", "start_box"}),
}


def _obs(
    frame: int,
    t: float,
    *,
    classes: Mapping[str, tuple[float, ...]] | None = None,
    rois: Iterable[str] = (),
    external: tuple[ExternalEvent, ...] = (),
    t_wall: float | None = None,
    aquarium_id: int | None = None,
) -> FrameObservation:
    return FrameObservation(
        frame=frame,
        t_s=t,
        classes=dict(classes or {}),
        subject_rois=frozenset(rois),
        external=external,
        t_wall=t_wall,
        aquarium_id=aquarium_id,
    )


def _rat(present: bool = True, **kwargs: object) -> ClassPresence:
    return ClassPresence(target=ClassTarget.of_class("rat"), present=present, **kwargs)  # type: ignore[arg-type]


def _run(
    spec: WindowSpec,
    observations: Iterable[FrameObservation],
    roles: Mapping[str, frozenset[str]] = ROLES,
) -> tuple[list[WindowEvent], WindowResult]:
    evaluator = ConditionEvaluator(spec, role_names=roles)
    events: list[WindowEvent] = []
    for observation in observations:
        events.extend(evaluator.step(observation))
    events.extend(evaluator.finish())
    return events, evaluator.result


def _uniform(n: int, dt: float = 1.0, **kwargs: object) -> list[FrameObservation]:
    return [_obs(i, i * dt, **kwargs) for i in range(n)]  # type: ignore[arg-type]


def _start_when(level: object, hold: Hold, **kwargs: object) -> WindowSpec:
    return WindowSpec(start=Persist(level=level, hold=hold, **kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Level nodes (observed through Persist(hold=1 frame))
# ---------------------------------------------------------------------------


def _first_true_frame(level: object, frames: list[FrameObservation]) -> int | None:
    _, result = _run(_start_when(level, Hold(frames=1)), frames)
    return None if result.start is None else result.start.frame


class TestLevels:
    def test_class_presence_counts_detections_of_the_named_class(self) -> None:
        frames = [
            _obs(0, 0.0),
            _obs(1, 0.1, classes={"experimenter": (0.9,)}),
            _obs(2, 0.2, classes={"rat": (0.8,)}),
        ]
        assert _first_true_frame(_rat(), frames) == 2

    def test_class_absent_is_true_when_no_detection(self) -> None:
        frames = [_obs(0, 0.0, classes={"rat": (0.9,)}), _obs(1, 0.1, classes={"rat": ()})]
        assert _first_true_frame(_rat(present=False), frames) == 1

    def test_min_count_needs_that_many_detections(self) -> None:
        frames = [
            _obs(0, 0.0, classes={"rat": (0.9,)}),
            _obs(1, 0.1, classes={"rat": (0.9, 0.8)}),
        ]
        assert _first_true_frame(_rat(min_count=2), frames) == 1
        # Absent with min_count=2 means "fewer than two".
        assert _first_true_frame(_rat(present=False, min_count=2), frames) == 0

    def test_min_confidence_filters_before_counting(self) -> None:
        frames = [
            _obs(0, 0.0, classes={"rat": (0.3, 0.49)}),
            _obs(1, 0.1, classes={"rat": (0.5,)}),
        ]
        assert _first_true_frame(_rat(min_confidence=0.5), frames) == 1
        assert _first_true_frame(_rat(present=False, min_confidence=0.5), frames) == 0

    def test_role_target_resolves_through_the_role_map(self) -> None:
        level = ClassPresence(target=ClassTarget.of_role("context"))
        frames = [
            _obs(0, 0.0, classes={"rat": (0.9,)}),
            _obs(1, 0.1, classes={"start_box": (0.9,)}),
        ]
        assert _first_true_frame(level, frames) == 1

    def test_role_without_names_is_never_present(self) -> None:
        frames = [_obs(0, 0.0, classes={"rat": (0.9,), "experimenter": (0.9,)})]
        present = ClassPresence(target=ClassTarget.of_role("context"))
        absent = ClassPresence(target=ClassTarget.of_role("context"), present=False)
        roles = {"subject": frozenset({"rat"})}
        assert _run(_start_when(present, Hold(frames=1)), frames, roles)[1].start is None
        assert _run(_start_when(absent, Hold(frames=1)), frames, roles)[1].start is not None

    def test_role_names_are_normalized(self) -> None:
        level = ClassPresence(target=ClassTarget.of_role("subject"))
        frames = [_obs(0, 0.0, classes={"lab_rat": (0.9,)})]
        roles = {"subject": frozenset({"  Lab Rat "})}
        assert _run(_start_when(level, Hold(frames=1)), frames, roles)[1].start is not None

    def test_roi_inside_and_outside(self) -> None:
        frames = [_obs(0, 0.0, rois={"b"}), _obs(1, 0.1, rois={"a", "b"})]
        assert _first_true_frame(RoiInside(roi="a", state="inside"), frames) == 1
        assert _first_true_frame(RoiInside(roi="b", state="outside"), frames) is None
        assert _first_true_frame(RoiInside(roi="a", state="outside"), frames) == 0

    def test_not_all_any(self) -> None:
        frames = [
            _obs(0, 0.0, rois={"a"}),
            _obs(1, 0.1, rois={"b"}),
            _obs(2, 0.2, rois={"a", "b"}),
        ]
        in_a = RoiInside(roi="a", state="inside")
        in_b = RoiInside(roi="b", state="inside")
        assert _first_true_frame(Not(child=in_a), frames) == 1
        assert _first_true_frame(AllOfLevel(children=(in_a, in_b)), frames) == 2
        assert _first_true_frame(AnyOfLevel(children=(in_b, in_a)), frames) == 0


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------


class TestPersist:
    def test_frames_hold_fires_on_kth_observation_backdated_to_first(self) -> None:
        frames = [_obs(i, i * 0.1, classes={"rat": (0.9,)} if i >= 2 else {}) for i in range(8)]
        events, result = _run(_start_when(_rat(), Hold(frames=3)), frames)
        assert result.start is not None
        assert (result.start.frame, result.start.t_s) == (2, pytest.approx(0.2))
        assert result.start.confirmed_frame == 4
        assert result.start.reason == "persist"
        assert events[0] == result.start

    def test_run_resets_when_level_turns_false(self) -> None:
        present = [False, True, True, False, True, True, True]
        frames = [
            _obs(i, float(i), classes={"rat": (0.9,)} if p else {}) for i, p in enumerate(present)
        ]
        _, result = _run(_start_when(_rat(), Hold(frames=3)), frames)
        assert result.start is not None
        assert result.start.frame == 4
        assert result.start.confirmed_frame == 6

    def test_seconds_hold_fires_exactly_at_the_boundary(self) -> None:
        frames = [_obs(i, float(i), classes={"rat": (0.9,)}) for i in range(5)]
        _, result = _run(_start_when(_rat(), Hold(seconds=2.0)), frames)
        assert result.start is not None
        assert result.start.frame == 0
        assert result.start.confirmed_frame == 2
        assert result.start.confirmed_t_s == 2.0

    def test_seconds_hold_tolerates_float_noise_in_pts(self) -> None:
        # 4.7 + 2.0 is not representable: 6.7 - 4.7 == 1.9999999999999996.
        frames = [_obs(0, 4.7, classes={"rat": (0.9,)}), _obs(1, 6.7, classes={"rat": (0.9,)})]
        _, result = _run(_start_when(_rat(), Hold(seconds=2.0)), frames)
        assert result.start is not None
        assert result.start.confirmed_frame == 1

    def test_seconds_hold_short_of_the_boundary_does_not_fire(self) -> None:
        frames = [_obs(i, i * 0.5, classes={"rat": (0.9,)}) for i in range(4)]  # 0 .. 1.5 s
        _, result = _run(_start_when(_rat(), Hold(seconds=2.0)), frames)
        assert result.start is None
        assert result.status == "start_not_met"

    def test_explicit_max_gap_resets_the_run(self) -> None:
        times = [0.0, 0.1, 0.2, 1.0, 1.1, 1.2, 1.3]
        frames = [_obs(i, t, classes={"rat": (0.9,)}) for i, t in enumerate(times)]
        _, result = _run(_start_when(_rat(), Hold(frames=4), max_gap_s=0.5), frames)
        assert result.start is not None
        assert result.start.frame == 3
        assert result.start.t_s == 1.0

    def test_gap_equal_to_max_gap_does_not_reset(self) -> None:
        times = [0.0, 0.5, 1.0]
        frames = [_obs(i, t, classes={"rat": (0.9,)}) for i, t in enumerate(times)]
        _, result = _run(_start_when(_rat(), Hold(frames=3), max_gap_s=0.5), frames)
        assert result.start is not None
        assert result.start.frame == 0

    def test_default_max_gap_is_three_times_the_median_interval(self) -> None:
        # Median dt = 0.1, so the default limit is 0.3 s; a 0.5 s hole resets.
        times = [0.0, 0.1, 0.2, 0.3, 0.8, 0.9, 1.0]
        frames = [_obs(i, t, classes={"rat": (0.9,)}) for i, t in enumerate(times)]
        _, result = _run(_start_when(_rat(), Hold(seconds=0.6)), frames)
        assert result.start is None
        _, longer = _run(_start_when(_rat(), Hold(seconds=0.2)), frames)
        assert longer.start is not None
        assert longer.start.frame == 0

    def test_default_max_gap_tolerates_a_gap_within_three_medians(self) -> None:
        times = [0.0, 0.1, 0.2, 0.3, 0.55, 0.65]
        frames = [_obs(i, t, classes={"rat": (0.9,)}) for i, t in enumerate(times)]
        _, result = _run(_start_when(_rat(), Hold(seconds=0.6)), frames)
        assert result.start is not None
        assert result.start.frame == 0

    def test_no_history_means_no_gap_reset(self) -> None:
        frames = [_obs(0, 0.0, classes={"rat": (0.9,)}), _obs(1, 10.0, classes={"rat": (0.9,)})]
        _, result = _run(_start_when(_rat(), Hold(seconds=5.0)), frames)
        assert result.start is not None
        assert result.start.frame == 0

    def test_duplicate_timestamps_do_not_shrink_the_default_gap(self) -> None:
        # dt history is 0.1 plus many zeros; zeros must not drag the median down.
        times = [0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.1, 0.2, 0.3, 0.4]
        frames = [_obs(i, t, classes={"rat": (0.9,)}) for i, t in enumerate(times)]
        _, result = _run(_start_when(_rat(), Hold(seconds=0.4)), frames)
        assert result.start is not None
        assert result.start.frame == 0

    def test_duplicate_frames_do_not_accelerate_a_seconds_hold(self) -> None:
        base = [_obs(i, i * 0.1, classes={"rat": (0.9,)}) for i in range(10)]
        doubled = [o for o in base for _ in range(2)]
        spec = _start_when(_rat(), Hold(seconds=0.5))
        assert _run(spec, base)[1] == _run(spec, doubled)[1]


# ---------------------------------------------------------------------------
# Instant triggers
# ---------------------------------------------------------------------------


class TestInstantTriggers:
    def test_roi_edge_enter_needs_a_real_transition(self) -> None:
        frames = [
            _obs(0, 0.0, rois={"a"}),
            _obs(1, 0.1),
            _obs(2, 0.2, rois={"a"}),
        ]
        _, result = _run(WindowSpec(start=RoiEdge(roi="a", edge="enter")), frames)
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (2, "roi_edge")

    def test_roi_edge_exit(self) -> None:
        frames = [_obs(0, 0.0), _obs(1, 0.1, rois={"a"}), _obs(2, 0.2), _obs(3, 0.3)]
        _, result = _run(WindowSpec(start=RoiEdge(roi="a", edge="exit")), frames)
        assert result.start is not None
        assert result.start.frame == 2

    def test_time_reached_on_the_video_clock(self) -> None:
        frames = _uniform(10, dt=0.3)
        _, result = _run(WindowSpec(start=TimeReached(clock="video", at_s=1.0)), frames)
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (4, "time")

    def test_time_reached_exactly_on_a_frame(self) -> None:
        _, result = _run(WindowSpec(start=TimeReached(clock="video", at_s=3.0)), _uniform(6))
        assert result.start is not None
        assert result.start.frame == 3

    def test_time_reached_on_the_wall_clock_is_elapsed_since_first_frame(self) -> None:
        frames = [_obs(i, i * 0.1, t_wall=1_000.0 + i * 0.5) for i in range(10)]
        _, result = _run(WindowSpec(start=TimeReached(clock="wall", at_s=2.0)), frames)
        assert result.start is not None
        assert result.start.frame == 4

    def test_wall_clock_without_wall_times_never_fires(self) -> None:
        _, result = _run(WindowSpec(start=TimeReached(clock="wall", at_s=0.0)), _uniform(5))
        assert result.start is None

    def test_frame_reached_accepts_the_first_index_at_or_past_target(self) -> None:
        frames = [_obs(f, f * 0.1) for f in (0, 3, 6, 9)]
        _, result = _run(WindowSpec(start=FrameReached(frame=5)), frames)
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (6, "frame")
        _, exact = _run(WindowSpec(start=FrameReached(frame=6)), frames)
        assert exact.start is not None
        assert exact.start.frame == 6

    def test_external_matches_source_and_code(self) -> None:
        frames = [
            _obs(0, 0.0, external=(ExternalEvent(source="manual", code=1, t_s=0.0),)),
            _obs(1, 0.1, external=(ExternalEvent(source="arduino", code=2, t_s=0.05),)),
            _obs(2, 0.2, external=(ExternalEvent(source="arduino", code=1, t_s=0.15),)),
        ]
        _, result = _run(WindowSpec(start=External(source="arduino", code=1)), frames)
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (2, "external")
        _, any_code = _run(WindowSpec(start=External(source="arduino", code=None)), frames)
        assert any_code.start is not None
        assert any_code.start.frame == 1

    def test_delay_after_a_trigger_counts_from_its_instant(self) -> None:
        spec = WindowSpec(start=Delay(after=FrameReached(frame=2), seconds=1.5))
        _, result = _run(spec, _uniform(8, dt=0.5))
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (5, "delay")

    def test_delay_after_a_backdated_persist_counts_from_the_backdated_instant(self) -> None:
        frames = [_obs(i, float(i), classes={"rat": (0.9,)} if i >= 1 else {}) for i in range(8)]
        spec = WindowSpec(
            start=Delay(after=Persist(level=_rat(), hold=Hold(frames=3)), seconds=2.5)
        )
        _, result = _run(spec, frames)
        # Persist backdates to t=1 (confirmed at t=3); 1 + 2.5 = 3.5 -> first frame at 4.
        assert result.start is not None
        assert result.start.frame == 4


# ---------------------------------------------------------------------------
# Composites
# ---------------------------------------------------------------------------


class TestComposites:
    def test_first_of_fires_with_the_first_child(self) -> None:
        spec = WindowSpec(start=FirstOf(children=(FrameReached(frame=5), FrameReached(frame=3))))
        _, result = _run(spec, _uniform(8))
        assert result.start is not None
        assert result.start.frame == 3

    def test_all_of_takes_the_instant_of_the_last_child(self) -> None:
        spec = WindowSpec(start=AllOf(children=(FrameReached(frame=5), FrameReached(frame=2))))
        events, result = _run(spec, _uniform(8))
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (5, "frame")
        assert [e.kind for e in events] == ["start", "stop"]

    def test_all_of_waits_for_every_child(self) -> None:
        spec = WindowSpec(
            start=AllOf(children=(FrameReached(frame=1), External(source="manual", code=None)))
        )
        _, result = _run(spec, _uniform(8))
        assert result.start is None

    def test_all_of_keeps_a_child_that_fired_long_ago(self) -> None:
        frames = [_obs(i, float(i), rois={"a"} if i == 1 else ()) for i in range(6)]
        spec = WindowSpec(
            start=AllOf(children=(RoiEdge(roi="a", edge="enter"), FrameReached(frame=4)))
        )
        _, result = _run(spec, frames)
        assert result.start is not None
        assert result.start.frame == 4

    def test_sequence_requires_the_declared_order(self) -> None:
        frames = [
            _obs(0, 0.0),
            _obs(1, 1.0, rois={"b"}),
            _obs(2, 2.0),
            _obs(3, 3.0, rois={"a"}),
            _obs(4, 4.0),
            _obs(5, 5.0, rois={"b"}),
        ]
        spec = WindowSpec(
            start=Sequence(
                children=(RoiEdge(roi="a", edge="enter"), RoiEdge(roi="b", edge="enter"))
            )
        )
        _, result = _run(spec, frames)
        assert result.start is not None
        assert (result.start.frame, result.start.reason) == (5, "roi_edge")

    def test_sequence_restarts_when_within_runs_out(self) -> None:
        def ext(frame: int, t: float, code: int) -> FrameObservation:
            return _obs(frame, t, external=(ExternalEvent(source="manual", code=code, t_s=t),))

        frames = [ext(0, 0.0, 1), ext(1, 3.0, 2), ext(2, 4.0, 1), ext(3, 5.0, 2)]
        children = (External(source="manual", code=1), External(source="manual", code=2))
        _, strict = _run(WindowSpec(start=Sequence(children=children, within_s=2.0)), frames)
        assert strict.start is not None
        assert strict.start.frame == 3
        _, loose = _run(WindowSpec(start=Sequence(children=children, within_s=None)), frames)
        assert loose.start is not None
        assert loose.start.frame == 1

    def test_sequence_completing_exactly_at_within_is_accepted(self) -> None:
        frames = [_obs(0, 0.0), _obs(1, 1.0), _obs(2, 2.0), _obs(3, 3.0)]
        spec = WindowSpec(
            start=Sequence(children=(FrameReached(frame=0), FrameReached(frame=2)), within_s=2.0)
        )
        _, result = _run(spec, frames)
        assert result.start is not None
        assert result.start.frame == 2

    def test_sequence_stage_is_armed_on_a_later_observation(self) -> None:
        # One manual press must not satisfy two stages.
        press = (ExternalEvent(source="manual", code=None, t_s=0.0),)
        frames = [_obs(0, 0.0, external=press), _obs(1, 1.0), _obs(2, 2.0, external=press)]
        child = External(source="manual", code=None)
        _, result = _run(WindowSpec(start=Sequence(children=(child, child))), frames)
        assert result.start is not None
        assert result.start.frame == 2


# ---------------------------------------------------------------------------
# Window lifecycle and statuses
# ---------------------------------------------------------------------------


class TestWindow:
    def test_no_start_means_first_frame(self) -> None:
        events, result = _run(WindowSpec(), [_obs(7, 0.4), _obs(8, 0.5)])
        assert result.start is not None
        assert (result.start.frame, result.start.t_s, result.start.reason) == (
            7,
            0.4,
            "first_frame",
        )
        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (8, "end_of_stream")
        assert (result.status, result.censored) == ("complete", False)
        assert [e.kind for e in events] == ["start", "stop"]

    def test_explicit_end_of_stream_stop_is_not_censored(self) -> None:
        _, result = _run(WindowSpec(stop=EndOfStream()), _uniform(3))
        assert (result.status, result.censored) == ("complete", False)

    def test_stop_never_met_is_censored_at_the_last_frame(self) -> None:
        spec = WindowSpec(stop=FirstOf(children=(EndOfStream(), FrameReached(frame=99))))
        events, result = _run(spec, _uniform(4))
        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (3, "end_of_stream")
        assert (result.status, result.censored) == ("censored", True)
        assert events[-1] == result.stop

    def test_stop_met_is_complete(self) -> None:
        _, result = _run(WindowSpec(stop=FrameReached(frame=2)), _uniform(5))
        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (2, "frame")
        assert (result.status, result.censored) == ("complete", False)

    def test_start_never_met(self) -> None:
        events, result = _run(WindowSpec(start=FrameReached(frame=50)), _uniform(5))
        assert events == []
        assert result == WindowResult(start=None, stop=None, status="start_not_met", censored=False)

    def test_empty_stream_is_start_not_met(self) -> None:
        _, result = _run(WindowSpec(), [])
        assert result.status == "start_not_met"

    def test_result_is_pending_until_finish(self) -> None:
        evaluator = ConditionEvaluator(WindowSpec(start=FrameReached(frame=1)), role_names=ROLES)
        assert evaluator.result.status == "pending"
        evaluator.step(_obs(0, 0.0))
        evaluator.step(_obs(1, 0.1))
        assert evaluator.result.status == "pending"
        assert evaluator.result.start is not None
        evaluator.finish()
        assert evaluator.result.status == "complete"

    def test_stop_is_not_evaluated_before_start(self) -> None:
        spec = WindowSpec(start=FrameReached(frame=3), stop=FrameReached(frame=0))
        _, result = _run(spec, _uniform(6))
        assert result.start is not None
        assert result.stop is not None
        assert (result.start.frame, result.stop.frame) == (3, 4)

    def test_stop_skips_observations_at_the_start_confirmation_instant(self) -> None:
        frames = [_obs(0, 0.0), _obs(1, 1.0), _obs(1, 1.0), _obs(2, 2.0)]
        spec = WindowSpec(start=FrameReached(frame=1), stop=FrameReached(frame=0))
        _, result = _run(spec, frames)
        assert result.stop is not None
        assert result.stop.frame == 2

    def test_the_same_external_press_cannot_start_and_stop(self) -> None:
        press = (ExternalEvent(source="arduino", code=1, t_s=0.0),)
        frames = [_obs(0, 0.0, external=press), _obs(1, 1.0), _obs(2, 2.0, external=press)]
        trig = External(source="arduino", code=1)
        _, result = _run(WindowSpec(start=trig, stop=trig), frames)
        assert result.start is not None
        assert result.stop is not None
        assert (result.start.frame, result.stop.frame) == (0, 2)

    def test_delay_after_start_counts_from_the_backdated_start(self) -> None:
        frames = [_obs(i, float(i), classes={"rat": (0.9,)} if i >= 2 else {}) for i in range(20)]
        spec = WindowSpec(
            start=Persist(level=_rat(), hold=Hold(frames=3)),
            stop=Delay(after="start", seconds=5.0),
        )
        _, result = _run(spec, frames)
        assert result.start is not None
        assert result.stop is not None
        assert result.start.t_s == 2.0
        assert (result.stop.frame, result.stop.reason) == (7, "delay")

    def test_no_rearm_after_stop(self) -> None:
        evaluator = ConditionEvaluator(
            WindowSpec(start=FrameReached(frame=1), stop=FrameReached(frame=2)), role_names=ROLES
        )
        emitted = [evaluator.step(o) for o in _uniform(6)]
        assert [len(e) for e in emitted] == [0, 1, 1, 0, 0, 0]
        assert evaluator.finish() == []
        assert evaluator.result.status == "complete"

    def test_step_after_finish_is_an_error_and_finish_is_idempotent(self) -> None:
        spec = WindowSpec()
        evaluator = ConditionEvaluator(spec, role_names=ROLES)
        assert evaluator.spec is spec
        evaluator.step(_obs(0, 0.0))
        assert not evaluator.finished
        first = evaluator.finish()
        assert evaluator.finished
        assert len(first) == 1
        assert evaluator.finish() == []
        with pytest.raises(RuntimeError):
            evaluator.step(_obs(1, 0.1))

    def test_time_going_backwards_is_skipped_not_fatal(self) -> None:
        frames = [_obs(0, 0.0), _obs(1, 1.0), _obs(2, 0.5), _obs(3, 2.0)]
        evaluator = ConditionEvaluator(WindowSpec(start=FrameReached(frame=2)), role_names=ROLES)
        for observation in frames:
            evaluator.step(observation)
        evaluator.finish()
        assert evaluator.skipped_observations == 1
        assert evaluator.result.start is not None
        assert evaluator.result.start.frame == 3

    def test_mixing_aquariums_is_rejected(self) -> None:
        evaluator = ConditionEvaluator(WindowSpec(), role_names=ROLES)
        evaluator.step(_obs(0, 0.0, aquarium_id=0))
        with pytest.raises(ValueError, match="aquarium"):
            evaluator.step(_obs(1, 0.1, aquarium_id=1))

    def test_batch_is_the_online_fold(self) -> None:
        spec = WindowSpec(start=FrameReached(frame=2), stop=FrameReached(frame=4))
        frames = _uniform(6)
        assert evaluate_window(spec, frames, role_names=ROLES) == _run(spec, frames)[1]


# ---------------------------------------------------------------------------
# Barnes protocol on a VFR stream
# ---------------------------------------------------------------------------


def _barnes_spec(k: int = 3, absent_s: float = 2.0, ceiling_s: float = 240.0) -> WindowSpec:
    return WindowSpec(
        start=Persist(
            level=AllOfLevel(
                children=(
                    ClassPresence(target=ClassTarget.of_class("start_box"), present=False),
                    ClassPresence(target=ClassTarget.of_class("experimenter"), present=False),
                    ClassPresence(target=ClassTarget.of_class("rat"), present=True),
                )
            ),
            hold=Hold(frames=k),
        ),
        stop=FirstOf(
            children=(
                EndOfStream(),
                Persist(level=_rat(present=False), hold=Hold(seconds=absent_s)),
                Delay(after="start", seconds=ceiling_s),
            )
        ),
    )


def _barnes_stream(
    duration_s: float = 60.0, rat_leaves_at: float | None = 40.0, seed: int = 7
) -> list[FrameObservation]:
    """VFR stream, 98-142 ms between frames, scripted like the lab videos.

    - ``start_box`` visible until 3.0 s;
    - ``experimenter`` visible until 6.7 s, except a 2-frame dropout near 5 s
      (shorter than k=3, so it must not open the window);
    - ``rat`` visible from 2.0 s, with a 1 s dropout at 20 s (shorter than the
      2 s STOP hold) and gone for good from ``rat_leaves_at``.
    """
    rng = random.Random(seed)
    observations: list[FrameObservation] = []
    t = 0.0
    frame = 0
    dropout_frames = 0
    while t < duration_s:
        classes: dict[str, tuple[float, ...]] = {}
        if t < 3.0:
            classes["start_box"] = (0.95,)
        experimenter = t < 6.7
        if 5.0 <= t and dropout_frames < 2 and experimenter:
            dropout_frames += 1
            experimenter = False
        if experimenter:
            classes["experimenter"] = (0.9,)
        rat_visible = t >= 2.0 and not (20.0 <= t < 21.0)
        if rat_leaves_at is not None and t >= rat_leaves_at:
            rat_visible = False
        if rat_visible:
            classes["rat"] = (0.88,)
        observations.append(_obs(frame, t, classes=classes))
        # Rounded PTS, like POS_MSEC / 1000; the scripted thresholds read the same value.
        t = round(t + rng.uniform(0.098, 0.142), 6)
        frame += 1
    return observations


def _first_frame_at(stream: list[FrameObservation], t: float) -> FrameObservation:
    return next(o for o in stream if o.t_s >= t)


class TestBarnes:
    def test_start_lands_on_first_frame_of_the_valid_run(self) -> None:
        stream = _barnes_stream()
        _, result = _run(_barnes_spec(), stream)
        expected = _first_frame_at(stream, 6.7)
        assert result.start is not None
        assert result.start.frame == expected.frame
        assert result.start.t_s == expected.t_s
        assert result.start.reason == "persist"
        confirmed_index = stream.index(expected) + 2
        assert result.start.confirmed_frame == stream[confirmed_index].frame

    def test_stop_by_rat_absence_is_backdated(self) -> None:
        stream = _barnes_stream()
        _, result = _run(_barnes_spec(), stream)
        gone = _first_frame_at(stream, 40.0)
        assert result.stop is not None
        assert (result.stop.frame, result.stop.t_s) == (gone.frame, gone.t_s)
        assert result.stop.reason == "persist"
        assert result.stop.confirmed_t_s is not None
        assert result.stop.confirmed_t_s - gone.t_s >= 2.0 - 1e-6
        assert (result.status, result.censored) == ("complete", False)

    def test_ceiling_variant_stops_at_start_plus_ceiling(self) -> None:
        stream = _barnes_stream()
        _, result = _run(_barnes_spec(ceiling_s=10.0), stream)
        assert result.start is not None
        assert result.stop is not None
        expected = _first_frame_at(stream, result.start.t_s + 10.0)
        assert (result.stop.frame, result.stop.reason) == (expected.frame, "delay")
        assert result.stop.t_s - result.start.t_s == pytest.approx(10.0, abs=0.142)

    def test_video_ending_before_the_ceiling_is_censored(self) -> None:
        stream = _barnes_stream(rat_leaves_at=None)
        _, result = _run(_barnes_spec(), stream)
        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (stream[-1].frame, "end_of_stream")
        assert (result.status, result.censored) == ("censored", True)

    def test_experimenter_never_leaving_is_start_not_met(self) -> None:
        stream = [
            _obs(o.frame, o.t_s, classes={**o.classes, "experimenter": (0.9,)})
            for o in _barnes_stream(duration_s=20.0)
        ]
        _, result = _run(_barnes_spec(), stream)
        assert result.status == "start_not_met"
        assert result.stop is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

_CLASSES = ("rat", "experimenter", "start_box")
_ROIS = ("a", "b")
_SOURCES: tuple[Literal["arduino", "manual"], ...] = ("arduino", "manual")
_TARGETS = [ClassTarget.of_class(name) for name in _CLASSES] + [
    ClassTarget.of_role("subject"),
    ClassTarget.of_role("context"),
]

_levels = st.recursive(
    st.one_of(
        st.builds(
            ClassPresence,
            target=st.sampled_from(_TARGETS),
            present=st.booleans(),
            min_count=st.integers(1, 2),
            min_confidence=st.sampled_from([None, 0.5]),
        ),
        st.builds(
            RoiInside, roi=st.sampled_from(_ROIS), state=st.sampled_from(["inside", "outside"])
        ),
    ),
    lambda inner: st.one_of(
        st.builds(Not, child=inner),
        st.builds(AllOfLevel, children=st.lists(inner, min_size=1, max_size=3).map(tuple)),
        st.builds(AnyOfLevel, children=st.lists(inner, min_size=1, max_size=3).map(tuple)),
    ),
    max_leaves=4,
)

_holds = st.one_of(
    st.builds(Hold, seconds=st.sampled_from([0.1, 0.25, 0.5, 1.0])),
    st.builds(Hold, frames=st.integers(1, 4)),
)
_seconds_holds = st.builds(Hold, seconds=st.sampled_from([0.1, 0.25, 0.5, 1.0]))


def _persist(holds: st.SearchStrategy[Hold]) -> st.SearchStrategy[Persist]:
    return st.builds(
        Persist, level=_levels, hold=holds, max_gap_s=st.sampled_from([None, 0.3, 1.0])
    )


def _triggers(for_stop: bool) -> st.SearchStrategy[object]:
    leaves: list[st.SearchStrategy[object]] = [
        _persist(_holds),
        st.builds(RoiEdge, roi=st.sampled_from(_ROIS), edge=st.sampled_from(["enter", "exit"])),
        st.builds(
            TimeReached,
            clock=st.sampled_from(["video", "wall"]),
            at_s=st.sampled_from([0.0, 0.5, 1.0, 2.0]),
        ),
        st.builds(FrameReached, frame=st.integers(0, 30)),
        st.builds(
            External,
            source=st.sampled_from(["arduino", "manual"]),
            code=st.sampled_from([None, 1, 2]),
        ),
    ]
    if for_stop:
        leaves.append(st.just(EndOfStream()))
        leaves.append(
            st.builds(Delay, after=st.just("start"), seconds=st.sampled_from([0.0, 0.5, 1.0]))
        )
    return st.recursive(
        st.one_of(leaves),
        lambda inner: st.one_of(
            st.builds(FirstOf, children=st.lists(inner, min_size=1, max_size=3).map(tuple)),
            st.builds(AllOf, children=st.lists(inner, min_size=1, max_size=3).map(tuple)),
            st.builds(
                Sequence,
                children=st.lists(inner, min_size=1, max_size=3).map(tuple),
                within_s=st.sampled_from([None, 0.5, 2.0]),
            ),
            st.builds(Delay, after=inner, seconds=st.sampled_from([0.0, 0.5])),
        ),
        max_leaves=4,
    )


_specs = st.builds(
    WindowSpec,
    start=st.none() | _triggers(for_stop=False),
    stop=st.none() | _triggers(for_stop=True),
)

_seconds_specs = st.builds(
    WindowSpec,
    start=st.none() | _persist(_seconds_holds),
    stop=st.none() | st.just(EndOfStream()) | _persist(_seconds_holds),
)


@st.composite
def _streams(draw: st.DrawFn, max_len: int = 40) -> list[FrameObservation]:
    n = draw(st.integers(0, max_len))
    t = draw(st.sampled_from([0.0, 0.033, 1.5]))
    frame = draw(st.integers(0, 3))
    observations: list[FrameObservation] = []
    for index in range(n):
        if index:
            t = round(t + draw(st.sampled_from([0.0, 0.098, 0.1, 0.142, 0.5, 2.0])), 6)
            frame += draw(st.integers(1, 3))
        classes = {
            name: tuple(draw(st.lists(st.sampled_from([0.2, 0.5, 0.9]), max_size=2)))
            for name in _CLASSES
        }
        rois = draw(st.frozensets(st.sampled_from(_ROIS)))
        external = tuple(
            ExternalEvent(source=source, code=code, t_s=t)
            for source, code in draw(
                st.lists(
                    st.tuples(st.sampled_from(_SOURCES), st.sampled_from([None, 1, 2])),
                    max_size=1,
                )
            )
        )
        observations.append(
            _obs(frame, t, classes=classes, rois=rois, external=external, t_wall=50.0 + t * 1.01)
        )
    return observations


_PROPERTY_SETTINGS = settings(
    max_examples=150,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.mark.property
class TestProperties:
    @_PROPERTY_SETTINGS
    @given(spec=_specs, stream=_streams())
    def test_batch_equals_online(self, spec: WindowSpec, stream: list[FrameObservation]) -> None:
        events, online = _run(spec, stream)
        assert evaluate_window(spec, stream, role_names=ROLES) == online
        assert events == [e for e in (online.start, online.stop) if e is not None]

    @_PROPERTY_SETTINGS
    @given(spec=_specs, stream=_streams(), cuts=st.lists(st.integers(0, 40), max_size=5))
    def test_chunked_feeding_and_midstream_reads_change_nothing(
        self, spec: WindowSpec, stream: list[FrameObservation], cuts: list[int]
    ) -> None:
        bounds = sorted({0, len(stream), *(c for c in cuts if c <= len(stream))})
        evaluator = ConditionEvaluator(spec, role_names=ROLES)
        for lo, hi in itertools.pairwise(bounds):
            for observation in stream[lo:hi]:
                evaluator.step(observation)
            assert evaluator.result.status in {"pending", "complete"}
        evaluator.finish()
        assert evaluator.result == evaluate_window(spec, stream, role_names=ROLES)

    @_PROPERTY_SETTINGS
    @given(spec=_specs, stream=_streams())
    def test_backdated_instant_never_follows_the_firing_instant(
        self, spec: WindowSpec, stream: list[FrameObservation]
    ) -> None:
        events, _ = _run(spec, stream)
        for event in events:
            assert event.confirmed_frame is not None
            assert event.confirmed_t_s is not None
            assert event.t_s <= event.confirmed_t_s
            assert event.frame <= event.confirmed_frame

    @_PROPERTY_SETTINGS
    @given(spec=_specs, stream=_streams())
    def test_stop_never_precedes_start(
        self, spec: WindowSpec, stream: list[FrameObservation]
    ) -> None:
        _, result = _run(spec, stream)
        if result.stop is not None:
            assert result.start is not None
            assert result.stop.t_s >= result.start.t_s
            assert result.stop.frame >= result.start.frame
        if result.status == "start_not_met":
            assert result.start is None
            assert result.stop is None

    @_PROPERTY_SETTINGS
    @given(spec=_seconds_specs, stream=_streams(), dup=st.lists(st.booleans(), max_size=40))
    def test_duplicated_frames_do_not_change_a_seconds_hold(
        self, spec: WindowSpec, stream: list[FrameObservation], dup: list[bool]
    ) -> None:
        doubled: list[FrameObservation] = []
        for index, observation in enumerate(stream):
            doubled.append(observation)
            if index < len(dup) and dup[index]:
                doubled.append(observation)
        assert _run(spec, doubled)[1] == _run(spec, stream)[1]
