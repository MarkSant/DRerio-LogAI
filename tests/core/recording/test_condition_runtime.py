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
from shapely.geometry import box
from structlog.testing import capture_logs

from zebtrack.core.conditions import (
    AllOfLevel,
    ClassPresence,
    ClassTarget,
    EndOfStream,
    External,
    FirstOf,
    FrameObservation,
    FrameReached,
    Hold,
    LastSeenIn,
    Persist,
    RoiInside,
    SubjectOverRoi,
    SubjectVisibleFraction,
    TimeReached,
    WindowSpec,
    evaluate_window,
    read_artifact,
)
from zebtrack.core.conditions.presets import (
    barnes_maze_preset,
    barnes_maze_preset_v2,
    external_trigger_preset,
)
from zebtrack.core.recording.condition_runtime import (
    ConditionRuntime,
    WindowPhase,
    classes_from_observations,
    parse_window_spec,
    role_names_from_role_map,
    spec_listens_to,
    spec_needs_subject_geometry,
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


# ---------------------------------------------------------------------------
# Subject geometry and the burrow entry (#633)
# ---------------------------------------------------------------------------

#: Escape hole ``toca`` as the detector stores it: vertex lists, frame pixels.
TOCA_VERTICES = [[200.0, 0.0], [400.0, 0.0], [400.0, 200.0], [200.0, 200.0]]
TOCA_ROIS = [("toca", TOCA_VERTICES)]
_RAT = ClassPresence(target=ClassTarget.of_class("rat"))

#: START at frame 0; STOP as soon as half the rat's box is over ``toca``.
OVER_TOCA = WindowSpec(
    start=FrameReached(frame=0),
    stop=Persist(level=SubjectOverRoi(roi="toca"), hold=Hold(frames=1)),
)


def _geo_step(runtime: ConditionRuntime, frame: int, boxes, rois=TOCA_ROIS):
    return runtime.step(
        frame=frame,
        t_capture_perf=T0 + frame * 0.1,
        classes={"rat": (0.9,)} if boxes else {},
        subject_rois=(),
        subject_boxes=boxes,
        rois=rois,
    )


class TestSpecNeedsSubjectGeometry:
    def test_entry_presets_need_it_and_v1_does_not(self):
        assert spec_needs_subject_geometry(barnes_maze_preset_v2()) is True
        assert spec_needs_subject_geometry(barnes_maze_preset()) is False
        assert spec_needs_subject_geometry(None) is False

    def test_any_geometry_node_anywhere(self):
        nested = Persist(
            level=AllOfLevel(children=(_RAT, LastSeenIn(roi="toca"))), hold=Hold(frames=1)
        )
        in_start = WindowSpec(start=Persist(level=SubjectOverRoi(roi="a"), hold=Hold(frames=1)))
        size = WindowSpec(
            stop=Persist(level=SubjectVisibleFraction(max_fraction=0.3), hold=Hold(frames=1))
        )

        assert spec_needs_subject_geometry(WindowSpec(stop=nested)) is True
        assert spec_needs_subject_geometry(in_start) is True
        assert spec_needs_subject_geometry(size) is True
        assert _runtime(size).needs_subject_geometry is True
        assert _runtime(barnes_maze_preset()).needs_subject_geometry is False


class TestRuntimeSubjectGeometry:
    def test_cover_is_measured_from_the_boxes_and_roi_vertices(self):
        runtime = _runtime(OVER_TOCA)
        _geo_step(runtime, 0, [(0, 50, 60, 110, 0.9)])  # off the hole
        off = _geo_step(runtime, 1, [(150, 50, 210, 110, 0.9)])  # 1/6 over it
        update = _geo_step(runtime, 2, [(170, 50, 230, 110, 0.9)])  # exactly half

        assert off.stop_confirmed is False
        assert update.stop_confirmed is True
        assert runtime.result.stop is not None and runtime.result.stop.frame == 2

    def test_the_highest_confidence_box_is_the_subject(self):
        runtime = _runtime(OVER_TOCA)
        _geo_step(runtime, 0, [])
        update = _geo_step(runtime, 1, [(250, 50, 300, 100, 0.3), (0, 50, 60, 110, 0.9)])

        assert update.stop_confirmed is False

    def test_shapely_rois_are_accepted_and_bad_vertices_are_skipped(self):
        runtime = _runtime(OVER_TOCA)
        rois = [("toca", box(200, 0, 400, 200)), ("bad", [[0, 0], [1, 1]]), ("junk", "x")]
        _geo_step(runtime, 0, [], rois=rois)
        update = _geo_step(runtime, 1, [(250, 50, 300, 100, 0.9)], rois=rois)

        assert update.stop_confirmed is True

    def test_without_rois_nothing_is_over_the_hole(self):
        runtime = _runtime(OVER_TOCA)
        _geo_step(runtime, 0, [], rois=[])
        update = _geo_step(runtime, 1, [(250, 50, 300, 100, 0.9)], rois=[])

        assert update.stop_confirmed is False

    def test_geometry_is_skipped_when_the_spec_does_not_need_it(self, monkeypatch):
        import zebtrack.core.recording.condition_runtime as module

        def _boom(*_args, **_kwargs):
            raise AssertionError("geometry computed for a spec that does not read it")

        monkeypatch.setattr(module, "observe_subject", _boom)
        runtime = _runtime(barnes_maze_preset())

        update = _geo_step(runtime, 0, [(0, 0, 10, 10, 0.9)])

        assert update.phase is WindowPhase.WAITING_START

    def test_roi_polygons_are_prepared_once_per_distinct_set(self, monkeypatch):
        import zebtrack.core.recording.condition_runtime as module

        calls = []
        real = module.prepare_rois

        def _counting(rois):
            calls.append([name for name, _shape in rois])
            return real(rois)

        monkeypatch.setattr(module, "prepare_rois", _counting)
        runtime = _runtime(OVER_TOCA)
        for frame in range(3):
            _geo_step(runtime, frame, [(0, 0, 10, 10, 0.9)])
        moved = [("toca", [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]])]
        _geo_step(runtime, 3, [(0, 0, 10, 10, 0.9)], rois=moved)

        assert calls == [["toca"], ["toca"]]


def _entry_script() -> list[list[tuple[float, float, float, float, float]]]:
    """A rat on the open table, then over ``toca`` and small, then gone.

    Frames 0-19 full size (60 x 60) off the hole; 20-24 full size half over it
    (the encounter); 25-34 a 25 x 25 box inside it (entry from frame 25);
    35-39 gone.
    """
    script: list[list[tuple[float, float, float, float, float]]] = []
    for frame in range(40):
        if frame < 20:
            x1 = 20.0 + 4 * frame
            script.append([(x1, 50.0, x1 + 60.0, 110.0, 0.9)])
        elif frame < 25:
            script.append([(170.0, 50.0, 230.0, 110.0, 0.9)])
        elif frame < 35:
            script.append([(260.0, 60.0, 285.0, 85.0, 0.9)])
        else:
            script.append([])
    return script


class TestBarnesEntryParity:
    """#633: live (boxes -> runtime) and analysis (trajectory -> builder) agree on the entry."""

    SPEC = barnes_maze_preset_v2(k_frames=3, entry_min_reference_frames=5)

    def _live(self) -> list:
        runtime = _runtime(self.SPEC, roles={"subject": {"rat"}})
        events = []
        for frame, boxes in enumerate(_entry_script()):
            events.extend(_geo_step(runtime, frame, boxes).events)
        events.extend(runtime.finish().events)
        return events

    def _offline(self):
        import pandas as pd
        from shapely.geometry import Polygon

        from zebtrack.analysis.roi import ROI
        from zebtrack.analysis.window_observations import build_window_observations

        rows = [
            {
                "timestamp": frame * 0.1,
                "frame": frame,
                "track_id": 1,
                "x1": b[0],
                "y1": b[1],
                "x2": b[2],
                "y2": b[3],
                "confidence": b[4],
            }
            for frame, boxes in enumerate(_entry_script())
            for b in boxes
        ]
        # The trajectory ends at the last detection; the builder needs the
        # stream to cover the absent tail too, which only a 3c heartbeat gives.
        built = build_window_observations(
            pd.DataFrame(rows),
            rois=[ROI("toca", Polygon(TOCA_VERTICES), coordinate_space="px")],
            subject_names=["rat"],
            min_track_duration_s=0.0,
        )
        return evaluate_window(self.SPEC, built.observations, role_names=built.role_names)

    def test_runtime_and_evaluate_window_agree_on_the_entry(self):
        live_stop = next(event for event in self._live() if event.kind == "stop")
        offline = self._offline()

        assert offline.stop is not None
        assert (live_stop.frame, live_stop.reason) == (25, "burrow_entry")
        assert (offline.stop.frame, offline.stop.reason) == (25, "burrow_entry")
        assert live_stop.t_s == pytest.approx(offline.stop.t_s)
        assert live_stop.confirmed_frame == offline.stop.confirmed_frame == 30


class TestPipelineGeometryInputs:
    """The pipeline's call site: the same detections as ``subject_rois``, raw ROI polygons."""

    @staticmethod
    def _inputs(pipeline, runtime, detections, aquarium_id=None):
        from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin

        return FrameProcessingMixin._condition_geometry_inputs(
            pipeline, runtime, detections, aquarium_id
        )

    def test_nothing_is_gathered_when_the_window_does_not_need_it(self):
        pipeline = SimpleNamespace(detector_service=None)
        runtime = SimpleNamespace(needs_subject_geometry=False)

        assert self._inputs(pipeline, runtime, [(0, 0, 1, 1, 0.9)]) == ([], [])

    def test_a_mock_runtime_is_not_mistaken_for_one_that_needs_it(self):
        from unittest.mock import MagicMock

        assert self._inputs(SimpleNamespace(), MagicMock(), [(0, 0, 1, 1)]) == ([], [])

    def test_single_aquarium_uses_the_detector_rois(self):
        detector = SimpleNamespace(roi_names=["toca", "b"], scaled_roi_polygons=["P1", "P2"])
        pipeline = SimpleNamespace(detector_service=SimpleNamespace(detector=detector))
        runtime = SimpleNamespace(needs_subject_geometry=True)
        detections = [(0, 0, 1, 1, 0.9, 3, 2)]

        boxes, rois = self._inputs(pipeline, runtime, detections)

        assert boxes == detections
        assert rois == [("toca", "P1"), ("b", "P2")]

    def test_multi_aquarium_keeps_only_that_aquariums_animal_and_rois(self):
        aquariums = [
            SimpleNamespace(id=0, roi_names=["toca"]),
            SimpleNamespace(id=1, roi_names=["toca", "b"]),
        ]
        multi = SimpleNamespace(
            get_multi_aquarium_data=lambda: aquariums,
            get_aquarium_roi_polygons=lambda aq_id: [f"A{aq_id}P0", f"A{aq_id}P1"],
        )
        pipeline = SimpleNamespace(_multi_aq_detector=multi)
        runtime = SimpleNamespace(needs_subject_geometry=True)
        mine = (5, 5, 9, 9, 0.8, 1002, 2)
        detections = [(0, 0, 1, 1, 0.9, 3, 2), mine, (0, 0, 1, 1, 0.9, None, 2), (1, 2)]

        boxes, rois = self._inputs(pipeline, runtime, detections, aquarium_id=1)

        assert boxes == [mine]
        assert rois == [("toca", "A1P0"), ("b", "A1P1")]

    def test_multi_aquarium_without_its_detector_yields_nothing(self):
        pipeline = SimpleNamespace(_multi_aq_detector=None)
        runtime = SimpleNamespace(needs_subject_geometry=True)

        assert self._inputs(pipeline, runtime, [(0, 0, 1, 1, 0.9, 1001)], aquarium_id=1) == (
            [],
            [],
        )


class TestRuntimeGeometryCost:
    """Hub review of #633: no shapely work per frame once the zones are known."""

    def test_polygons_are_built_once_for_unchanged_vertices(self, monkeypatch):
        import zebtrack.core.recording.condition_runtime as module

        built = []
        real = module._roi_geometry

        def _counting(polygon):
            built.append(1)
            return real(polygon)

        monkeypatch.setattr(module, "_roi_geometry", _counting)
        runtime = _runtime(OVER_TOCA)
        # A distinct container each frame (kept alive, so no id is reused): the
        # key is the vertices, not the object that carries them.
        containers = [[list(vertex) for vertex in TOCA_VERTICES] for _ in range(5)]
        for frame, vertices in enumerate(containers):
            _geo_step(runtime, frame, [(0, 0, 10, 10, 0.9)], rois=[("toca", vertices)])

        assert len(built) == 1

    def test_prepared_shapes_are_not_prepared_again_per_frame(self, monkeypatch):
        import zebtrack.core.conditions.subject_geometry as geometry

        runtime = _runtime(OVER_TOCA)
        _geo_step(runtime, 0, [(0, 0, 10, 10, 0.9)])

        def _boom(_rois):
            raise AssertionError("prepare_rois called on already-prepared shapes")

        monkeypatch.setattr(geometry, "prepare_rois", _boom)
        update = _geo_step(runtime, 1, [(250, 50, 300, 100, 0.9)])

        assert update.stop_confirmed is True

    def test_a_shapely_roi_is_keyed_by_identity(self):
        runtime = _runtime(OVER_TOCA)
        shape = box(200, 0, 400, 200)
        _geo_step(runtime, 0, [], rois=[("toca", shape)])
        first = runtime._roi_shapes
        _geo_step(runtime, 1, [], rois=[("toca", shape)])

        assert runtime._roi_shapes is first


class TestRuntimeMissingGeometryInputs:
    """Hub review of #633: a v2 window without its ROI must not fail silently."""

    SPEC = barnes_maze_preset_v2(k_frames=1)

    def _run(self, runtime, rois, frames=6):
        for frame in range(frames):
            runtime.step(
                frame=frame,
                t_capture_perf=T0 + frame * 0.1,
                classes={"rat": (0.9,)},
                subject_rois=(),
                subject_boxes=[(0, 0, 10, 10, 0.9)],
                rois=rois,
            )

    def test_warns_once_after_start_when_the_burrow_roi_is_missing(self):
        runtime = _runtime(self.SPEC)

        with capture_logs() as logs:
            self._run(runtime, [("center", TOCA_VERTICES)])

        warnings = [
            e for e in logs if e["event"] == "condition_runtime.subject_geometry.inputs_missing"
        ]
        assert len(warnings) == 1
        assert warnings[0]["log_level"] == "warning"
        assert warnings[0]["missing"] == ["roi:toca"]
        assert warnings[0]["available"] == ["center"]
        assert runtime.missing_inputs == ("roi:toca",)

    def test_no_zones_at_all_is_reported_too(self):
        runtime = _runtime(self.SPEC)

        self._run(runtime, [])

        assert runtime.missing_inputs == ("roi:toca",)

    def test_nothing_is_reported_before_start(self):
        runtime = _runtime(self.SPEC)
        runtime.step(
            frame=0,
            t_capture_perf=T0,
            classes={"start_box": (0.9,)},
            subject_rois=(),
            subject_boxes=[],
            rois=[],
        )

        assert runtime.result.start is None
        assert runtime.missing_inputs == ()

    def test_present_roi_reports_nothing(self):
        runtime = _runtime(self.SPEC)

        with capture_logs() as logs:
            self._run(runtime, TOCA_ROIS)

        assert runtime.result.start is not None
        assert runtime.missing_inputs == ()
        assert not [e for e in logs if e["event"].endswith("inputs_missing")]
