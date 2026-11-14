"""Tests for the live analysis-window runtime (``core/recording/condition_runtime.py``).

The runtime is the live side of ADR-011: it dates every analysed frame by its
CAPTURE instant relative to the frame ledger's anchor, delivers Arduino and
manual events with the first frame captured at or after their stamp, and tells
the pipeline when to sweep the Arduino outputs and when to end the session.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zebtrack.core.conditions import (
    ClassPresence,
    ClassTarget,
    EndOfStream,
    External,
    FirstOf,
    FrameObservation,
    FrameReached,
    Hold,
    Persist,
    RoiInside,
    TimeReached,
    WindowSpec,
    evaluate_window,
    read_artifact,
)
from zebtrack.core.conditions.presets import barnes_maze_preset, external_trigger_preset
from zebtrack.core.recording.condition_runtime import (
    ConditionRuntime,
    WindowPhase,
    classes_from_observations,
    parse_window_spec,
    role_names_from_role_map,
    spec_listens_to,
    window_phase_message,
)

T0 = 1000.0  # perf_counter anchor of the session's frame ledger


def _runtime(spec: WindowSpec, *, origin: float | None = T0, roles=None) -> ConditionRuntime:
    return ConditionRuntime(
        spec,
        role_names=roles or {"subject": {"rat"}},
        clock_origin=(lambda: origin),
    )


def _step(runtime: ConditionRuntime, frame: int, t_perf: float, *, classes=None, rois=()):
    return runtime.step(
        frame=frame,
        t_capture_perf=t_perf,
        classes=classes or {},
        subject_rois=rois,
    )


ARDUINO_START = WindowSpec(start=External(source="arduino", code=1))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestParseWindowSpec:
    def test_none_and_empty_mean_no_window(self):
        assert parse_window_spec(None) is None
        assert parse_window_spec({}) is None

    def test_project_dict_round_trips(self):
        spec = barnes_maze_preset()
        raw = spec.model_dump(mode="json", by_alias=True)
        assert parse_window_spec(raw) == spec

    def test_spec_instance_is_returned_as_is(self):
        spec = external_trigger_preset()
        assert parse_window_spec(spec) is spec

    def test_invalid_spec_degrades_to_none(self):
        assert parse_window_spec({"start": {"kind": "no_such_node"}}) is None

    def test_non_mapping_degrades_to_none(self):
        assert parse_window_spec(["not", "a", "spec"]) is None


class TestSpecListensTo:
    def test_external_arduino_nested_in_stop(self):
        spec = WindowSpec(stop=FirstOf(children=(EndOfStream(), External(source="arduino"))))
        assert spec_listens_to(spec, "arduino") is True
        assert spec_listens_to(spec, "manual") is False

    def test_manual_start(self):
        spec = WindowSpec(start=External(source="manual"))
        assert spec_listens_to(spec, "manual") is True
        assert spec_listens_to(spec, "arduino") is False

    def test_no_spec_listens_to_nothing(self):
        assert spec_listens_to(None, "arduino") is False
        assert spec_listens_to(barnes_maze_preset(), "arduino") is False


class TestRoleNames:
    def test_groups_normalized_names_by_role(self):
        role_map = SimpleNamespace(
            roles_as_dict=lambda: {
                "Rat": "subject",
                "start box": "context",
                "experimenter": "context",
                "arena": "arena",
            }
        )
        assert role_names_from_role_map(role_map) == {
            "subject": frozenset({"rat"}),
            "context": frozenset({"start_box", "experimenter"}),
            "arena": frozenset({"arena"}),
        }

    def test_detector_without_roles_yields_nothing(self):
        assert role_names_from_role_map(None) == {}


class TestClassesFromObservations:
    def test_groups_confidences_under_normalized_names(self):
        observations = [
            {"class_name": "Start Box", "confidence": 0.8},
            {"class_name": "rat", "confidence": 0.9},
            {"class_name": "start-box", "confidence": 0.4},
        ]
        assert classes_from_observations(observations) == {
            "start_box": (0.8, 0.4),
            "rat": (0.9,),
        }

    def test_skips_malformed_items_and_keeps_presence_without_confidence(self):
        observations: list[Any] = [{"confidence": 0.9}, "garbage", {"class_name": "rat"}]
        assert classes_from_observations(observations) == {"rat": (0.0,)}


class TestWindowPhaseMessage:
    def test_every_phase_has_its_own_sentence(self):
        messages = {
            window_phase_message(WindowPhase.WAITING_START),
            window_phase_message(WindowPhase.IN_ANALYSIS, t_s=3.25),
            window_phase_message(WindowPhase.FINISHED, t_s=12.0),
            window_phase_message(WindowPhase.START_NOT_MET),
            window_phase_message(WindowPhase.START_NOT_MET, on_start_not_met="empty"),
        }
        assert len(messages) == 5

    def test_instant_is_shown_in_seconds(self):
        assert "3.2" in window_phase_message("in_analysis", t_s=3.25)
        assert "12.0" in window_phase_message("finished", t_s=12.0)


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class TestCaptureClock:
    def test_t_s_is_capture_minus_ledger_anchor(self):
        runtime = _runtime(WindowSpec(start=TimeReached(clock="video", at_s=3.0)))
        assert _step(runtime, 30, T0 + 1.0).events == ()
        assert _step(runtime, 60, T0 + 2.0).events == ()
        update = _step(runtime, 90, T0 + 3.2)
        (start,) = update.events
        assert start.kind == "start"
        assert start.t_s == pytest.approx(3.2)
        assert start.frame == 90
        assert runtime.origin_perf == T0

    def test_origin_falls_back_to_first_frame_without_anchor(self):
        runtime = _runtime(WindowSpec(start=TimeReached(clock="video", at_s=1.0)), origin=None)
        _step(runtime, 5, 500.0)
        (start,) = _step(runtime, 10, 501.0).events
        assert start.t_s == pytest.approx(1.0)
        assert runtime.origin_perf == 500.0

    def test_origin_is_read_once(self):
        calls = []

        def _origin():
            calls.append(1)
            return T0

        runtime = ConditionRuntime(WindowSpec(), role_names={}, clock_origin=_origin)
        for frame in range(3):
            _step(runtime, frame, T0 + frame)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# External events
# ---------------------------------------------------------------------------


class TestExternalEvents:
    def test_arduino_event_waits_for_a_frame_captured_after_it(self):
        runtime = _runtime(ARDUINO_START)
        runtime.offer_external("arduino", 1, T0 + 2.5)
        # captured BEFORE the press: the event is not delivered yet
        assert _step(runtime, 60, T0 + 2.0).events == ()
        (start,) = _step(runtime, 90, T0 + 3.0).events
        assert start.reason == "external"
        assert start.t_s == pytest.approx(3.0)

    def test_event_stamped_exactly_at_capture_is_delivered(self):
        runtime = _runtime(ARDUINO_START)
        runtime.offer_external("arduino", 1, T0 + 2.0)
        (start,) = _step(runtime, 60, T0 + 2.0).events
        assert start.frame == 60

    def test_wrong_code_does_not_start(self):
        runtime = _runtime(ARDUINO_START)
        runtime.offer_external("arduino", 7, T0 + 1.0)
        assert _step(runtime, 60, T0 + 2.0).events == ()
        assert runtime.phase is WindowPhase.WAITING_START

    def test_offer_claims_only_sources_the_spec_waits_for(self):
        runtime = _runtime(ARDUINO_START)
        assert runtime.offer_external("arduino", 0, T0) is True
        assert runtime.offer_external("manual", None, T0) is False
        assert _runtime(barnes_maze_preset()).offer_external("arduino", 1, T0) is False

    def test_manual_press_is_not_claimed_by_a_window_that_ignores_it(self):
        assert _runtime(ARDUINO_START).push_manual(T0) is False

    def test_manual_press_starts_a_manual_window(self):
        runtime = _runtime(WindowSpec(start=External(source="manual")))
        assert runtime.push_manual(T0 + 1.0) is True
        (start,) = _step(runtime, 30, T0 + 1.5).events
        assert start.reason == "external"

    def test_events_are_logged_even_when_never_delivered(self):
        runtime = _runtime(ARDUINO_START)
        runtime.offer_external("arduino", 1, T0 + 1.0)
        _step(runtime, 30, T0 + 1.0)
        runtime.offer_external("arduino", 0, T0 + 9.0)  # after the last frame
        runtime.finish()
        events = runtime.external_events
        assert [(e.code, e.t_s) for e in events] == [(1, 1.0), (0, 9.0)]
        assert all(e.source == "arduino" for e in events)

    def test_offer_is_safe_from_other_threads(self):
        runtime = _runtime(WindowSpec(start=External(source="manual")))
        threads = [
            threading.Thread(target=runtime.push_manual, args=(T0 + 0.1 * i,), daemon=True)
            for i in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)
        _step(runtime, 1, T0 + 5.0)
        assert len(runtime.external_events) == 20


# ---------------------------------------------------------------------------
# Phases, sweep and session end
# ---------------------------------------------------------------------------


class TestPhases:
    def test_waiting_then_open_then_finished(self):
        spec = WindowSpec(start=FrameReached(frame=2), stop=FrameReached(frame=4))
        runtime = _runtime(spec)
        first = _step(runtime, 1, T0 + 0.1)
        assert first.phase is WindowPhase.WAITING_START
        assert first.phase_changed is False
        opened = _step(runtime, 2, T0 + 0.2)
        assert opened.phase is WindowPhase.IN_ANALYSIS
        assert opened.phase_changed is True
        assert runtime.window_open is True
        same = _step(runtime, 3, T0 + 0.3)
        assert same.phase_changed is False
        closed = _step(runtime, 4, T0 + 0.4)
        assert closed.phase is WindowPhase.FINISHED
        assert closed.stop_confirmed is True
        assert runtime.window_open is False
        assert runtime.window_opened is True

    def test_start_never_met_at_finish(self):
        runtime = _runtime(ARDUINO_START)
        _step(runtime, 1, T0 + 0.1)
        update = runtime.finish()
        assert update.phase is WindowPhase.START_NOT_MET
        assert update.phase_changed is True
        assert update.stop_confirmed is False
        assert runtime.window_opened is False

    def test_open_window_closes_at_finish_without_ending_the_session(self):
        spec = WindowSpec(start=FrameReached(frame=1), on_stop="end_session")
        runtime = _runtime(spec)
        _step(runtime, 1, T0 + 0.1)
        update = runtime.finish()
        assert update.stop_confirmed is True
        assert update.end_session is False
        assert update.phase is WindowPhase.FINISHED

    def test_mark_only_marks(self):
        spec = WindowSpec(start=FrameReached(frame=1), stop=FrameReached(frame=2))
        runtime = _runtime(spec)
        _step(runtime, 1, T0 + 0.1)
        update = _step(runtime, 2, T0 + 0.2)
        assert update.stop_confirmed is True
        assert update.end_session is False

    def test_end_session_is_signalled_once(self):
        runtime = _runtime(external_trigger_preset())
        runtime.offer_external("arduino", 1, T0 + 0.5)
        _step(runtime, 1, T0 + 1.0)
        runtime.offer_external("arduino", 0, T0 + 1.5)
        stop = _step(runtime, 2, T0 + 2.0)
        assert stop.stop_confirmed is True
        assert stop.end_session is True
        assert _step(runtime, 3, T0 + 3.0).end_session is False
        assert runtime.finish().end_session is False

    def test_level_conditions_use_roles_and_rois(self):
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_role("subject")),
                hold=Hold(seconds=1.0),
            ),
            stop=Persist(level=RoiInside(roi="escape", state="inside"), hold=Hold(seconds=0.5)),
        )
        runtime = _runtime(spec, roles={"subject": {"Rat"}})
        rat = {"rat": (0.9,)}
        _step(runtime, 1, T0 + 1.0, classes=rat)
        (start,) = _step(runtime, 2, T0 + 2.0, classes=rat).events
        assert start.t_s == pytest.approx(1.0)  # back-dated to the run's first frame
        _step(runtime, 3, T0 + 3.0, classes=rat, rois={"escape"})
        (stop,) = _step(runtime, 4, T0 + 3.5, classes=rat, rois={"escape"}).events
        assert stop.t_s == pytest.approx(3.0)


class TestBarnesBurrowParity:
    """#650: live and analysis end the Barnes trial at the SAME burrow entry."""

    @staticmethod
    def _trial() -> list[tuple[int, float, dict, frozenset[str]]]:
        """Release at frame 2; the rat enters ``toca`` at 12 and stays visible there."""
        rows = []
        for frame in range(30):
            if frame < 2:
                classes = {"start_box": (0.9,), "experimenter": (0.9,), "rat": (0.9,)}
            else:
                classes = {"rat": (0.9,)}
            rois = frozenset({"toca"}) if frame >= 12 else frozenset()
            rows.append((frame, frame * 0.1, classes, rois))
        return rows

    def test_runtime_and_evaluate_window_agree_on_the_stop(self):
        spec = barnes_maze_preset(k_frames=3, absent_s=1.0)
        roles = {"subject": {"rat"}}
        runtime = _runtime(spec, roles=roles)
        live = []
        for frame, t_s, classes, rois in self._trial():
            live.extend(_step(runtime, frame, T0 + t_s, classes=classes, rois=rois).events)
        live.extend(runtime.finish().events)

        offline = evaluate_window(
            spec,
            (
                FrameObservation(frame=frame, t_s=t_s, classes=classes, subject_rois=rois)
                for frame, t_s, classes, rois in self._trial()
            ),
            role_names=roles,
        )

        live_stop = next(event for event in live if event.kind == "stop")
        assert offline.stop is not None
        assert (live_stop.frame, live_stop.reason) == (12, "roi_edge")
        assert (offline.stop.frame, offline.stop.reason) == (12, "roi_edge")
        assert live_stop.t_s == pytest.approx(offline.stop.t_s)
        assert runtime.result.censored is offline.censored is False


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


class TestArtifact:
    def test_online_section_and_external_events(self, tmp_path: Path):
        runtime = _runtime(external_trigger_preset())
        runtime.offer_external("arduino", 1, T0 + 0.5)
        _step(runtime, 30, T0 + 1.0)
        runtime.offer_external("arduino", 0, T0 + 4.5)
        _step(runtime, 150, T0 + 5.0)
        runtime.finish()

        path = runtime.write_artifact(tmp_path, "session_A", fps_video=29.7)

        assert path == tmp_path / "7_AnalysisWindow_session_A.json"
        artifact = read_artifact(path)
        assert artifact is not None
        assert artifact.clock == "capture_perf"
        assert artifact.fps_video == pytest.approx(29.7)
        assert artifact.offline is None
        assert artifact.online.start is not None
        assert artifact.online.start.frame == 30
        assert artifact.online.start.t_s == pytest.approx(1.0)
        assert artifact.online.stop is not None
        assert artifact.online.stop.t_s == pytest.approx(5.0)
        assert [(e.code, e.t_s) for e in artifact.external_events] == [(1, 0.5), (0, 4.5)]

    def test_unknown_fps_is_omitted(self):
        runtime = _runtime(WindowSpec())
        _step(runtime, 1, T0 + 0.1)
        runtime.finish()
        assert runtime.build_artifact(fps_video=0.0).fps_video is None

    def test_start_not_met_has_no_online_instants(self):
        runtime = _runtime(ARDUINO_START)
        _step(runtime, 1, T0 + 0.1)
        runtime.finish()
        artifact = runtime.build_artifact()
        assert artifact.online.start is None
        assert artifact.online.stop is None


def test_frame_hold_is_accepted_live():
    spec = WindowSpec(
        start=Persist(level=ClassPresence(target=ClassTarget.of_class("rat")), hold=Hold(frames=2))
    )
    runtime = _runtime(spec)
    _step(runtime, 1, T0 + 0.1, classes={"rat": (0.9,)})
    (start,) = _step(runtime, 2, T0 + 0.2, classes={"rat": (0.9,)}).events
    assert start.frame == 1
