"""Tests for ``analysis/window_observations.py`` (ADR-011, front F4b)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI
from zebtrack.analysis.window_observations import (
    TRAJECTORY_SUBJECT_CLASS,
    build_window_observations,
    missing_inputs,
    role_names_from_metadata,
    subject_rois_by_frame,
)
from zebtrack.core.conditions import (
    AllOfLevel,
    ClassPresence,
    ClassTarget,
    ExternalEvent,
    Hold,
    Persist,
    RoiInside,
    WindowSpec,
    evaluate_window,
)
from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig
from zebtrack.io.object_sidecar import (
    ObjectSidecarMetadata,
    build_object_table,
    read_object_sidecar,
)

ROLES = {"rat": "subject", "experimenter": "context", "start_box": "context"}
NAMES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}
CENTROID_RULE = RoiRuleConfig(
    rule="centroid_in", flutter_enter_frames=1, flutter_exit_frames=1, min_visit_s=0.0
)
ROI_SQUARE = ROI(
    name="toca", geometry=Polygon([(0, 0), (100, 0), (100, 100), (0, 100)]), coordinate_space="px"
)


def _heartbeat(frame: int, t_event: float, aquarium_id: int | None = None) -> dict:
    return {
        "frame": frame,
        "timestamp": t_event + 1000.0,  # a different clock: t_event_s must win
        "t_event_s": t_event,
        "class_id": -1,
        "class_name": None,
        "role": "frame",
        "aquarium_id": aquarium_id,
    }


def _detection(
    frame: int,
    t_event: float,
    class_id: int,
    confidence: float = 0.9,
    aquarium_id: int | None = None,
) -> dict:
    name = NAMES[class_id]
    return {
        "frame": frame,
        "timestamp": t_event + 1000.0,
        "t_event_s": t_event,
        "class_id": class_id,
        "class_name": name,
        "role": ROLES.get(name, "arena"),
        "x1": 1.0,
        "y1": 1.0,
        "x2": 5.0,
        "y2": 5.0,
        "confidence": confidence,
        "aquarium_id": aquarium_id,
    }


def _objects(tmp_path: Path, rows: list[dict], clock: str = "pts") -> pd.DataFrame:
    metadata = ObjectSidecarMetadata(
        class_names=NAMES, class_roles=ROLES, weight_sha256="abc", clock=clock
    )
    path = tmp_path / "3c_Objetos_X.parquet"
    pq.write_table(build_object_table(rows, metadata), path)
    df = read_object_sidecar(path)
    assert df is not None
    return df


def _trajectory(frames, xs, *, fps: float = 10.0, track_ids=None) -> pd.DataFrame:
    frames = list(frames)
    xs = list(xs)
    df = pd.DataFrame(
        {
            "timestamp": [round(f / fps, 9) for f in frames],
            "frame": frames,
            "track_id": track_ids if track_ids is not None else [1] * len(frames),
            "x_center_px": xs,
            "y_center_px": [50.0] * len(frames),
            "confidence": [0.8] * len(frames),
        }
    )
    df["x1"] = df["x_center_px"] - 5
    df["x2"] = df["x_center_px"] + 5
    df["y1"] = df["y_center_px"] - 5
    df["y2"] = df["y_center_px"] + 5
    return df


class TestFromObjectSidecar:
    def test_one_observation_per_heartbeat_on_the_event_clock(self, tmp_path):
        rows = [_heartbeat(f, f / 10) for f in (4, 2, 0)]
        objects = _objects(tmp_path, rows)

        built = build_window_observations(None, objects_df=objects)

        assert [o.frame for o in built.observations] == [0, 2, 4]
        assert [o.t_s for o in built.observations] == pytest.approx([0.0, 0.2, 0.4])
        assert built.has_objects is True
        assert built.warnings == ()
        assert built.clock == "pts"

    def test_detection_rows_become_classes_by_normalised_name(self, tmp_path):
        rows = [
            _heartbeat(0, 0.0),
            _detection(0, 0.0, 1, 0.7),
            _detection(0, 0.0, 2, 0.95),
            _detection(0, 0.0, 2, 0.6),
            _heartbeat(1, 0.1),
        ]
        built = build_window_observations(None, objects_df=_objects(tmp_path, rows))

        first, second = built.observations
        assert dict(first.classes) == {
            "experimenter": pytest.approx((0.7,)),
            "rat": pytest.approx((0.95, 0.6)),
        }
        assert dict(second.classes) == {}

    def test_role_names_come_from_the_sidecar_metadata(self, tmp_path):
        built = build_window_observations(None, objects_df=_objects(tmp_path, [_heartbeat(0, 0)]))

        assert built.role_names == {
            "subject": frozenset({"rat"}),
            "context": frozenset({"experimenter", "start_box"}),
        }
        assert built.subject_names == frozenset({"rat"})

    def test_capture_clock_is_reported(self, tmp_path):
        objects = _objects(tmp_path, [_heartbeat(0, 0.0)], clock="capture_perf")

        assert build_window_observations(None, objects_df=objects).clock == "capture_perf"

    def test_other_aquariums_rows_are_dropped_and_null_rows_kept(self, tmp_path):
        rows = [
            _heartbeat(0, 0.0, aquarium_id=0),
            _heartbeat(0, 0.0, aquarium_id=1),
            _detection(0, 0.0, 2, aquarium_id=1),
            _detection(0, 0.0, 1, aquarium_id=None),
        ]
        objects = _objects(tmp_path, rows)

        built = build_window_observations(None, objects_df=objects, aquarium_id=0)

        (obs,) = built.observations
        assert set(obs.classes) == {"experimenter"}
        assert obs.aquarium_id == 0

    def test_no_aquarium_keeps_every_row(self, tmp_path):
        rows = [_heartbeat(0, 0.0, 0), _detection(0, 0.0, 2, aquarium_id=1)]

        built = build_window_observations(None, objects_df=_objects(tmp_path, rows))

        assert set(built.observations[0].classes) == {"rat"}

    def test_subject_rois_come_from_the_trajectory(self, tmp_path):
        rows = [_heartbeat(f, f / 10) for f in range(4)]
        trajectory = _trajectory([0, 1, 3], [50.0, 300.0, 50.0])

        built = build_window_observations(
            trajectory,
            objects_df=_objects(tmp_path, rows),
            rois=[ROI_SQUARE],
            roi_rule=CENTROID_RULE,
        )

        assert [set(o.subject_rois) for o in built.observations] == [
            {"toca"},
            set(),
            set(),
            {"toca"},
        ]

    def test_external_event_reaches_the_first_frame_at_or_after_it(self, tmp_path):
        rows = [_heartbeat(f, f / 10) for f in range(5)]
        events = [
            ExternalEvent(source="arduino", code=1, t_s=0.15),
            ExternalEvent(source="manual", code=None, t_s=0.3),
            ExternalEvent(source="arduino", code=0, t_s=9.0),  # after the stream
        ]

        built = build_window_observations(
            None, objects_df=_objects(tmp_path, rows), external_events=events
        )

        delivered = {o.frame: [e.code for e in o.external] for o in built.observations}
        assert delivered == {0: [], 1: [], 2: [1], 3: [None], 4: []}


class TestSubjectRoisRule:
    def test_debounce_of_the_report_rule_is_applied(self):
        # Raw inside on frames 3-6; enter=2 backdates the entry to frame 3.
        trajectory = _trajectory(range(8), [300.0] * 3 + [50.0] * 4 + [300.0])
        rule = RoiRuleConfig(
            rule="centroid_in", flutter_enter_frames=2, flutter_exit_frames=1, min_visit_s=0.0
        )

        by_frame = subject_rois_by_frame(trajectory, [ROI_SQUARE], rule)

        inside = [frame for frame, rois in sorted(by_frame.items()) if rois]
        assert inside == [3, 4, 5, 6]

    def test_a_single_flicker_is_not_inside_under_debounce(self):
        trajectory = _trajectory(range(6), [300.0, 300.0, 50.0, 300.0, 300.0, 300.0])
        rule = RoiRuleConfig(
            rule="centroid_in", flutter_enter_frames=2, flutter_exit_frames=1, min_visit_s=0.0
        )

        assert not any(subject_rois_by_frame(trajectory, [ROI_SQUARE], rule).values())

    def test_any_animal_inside_occupies_the_roi(self):
        frames = [0, 0, 1, 1]
        trajectory = _trajectory(frames, [50.0, 300.0, 300.0, 300.0], track_ids=[1, 2, 1, 2])

        by_frame = subject_rois_by_frame(trajectory, [ROI_SQUARE], CENTROID_RULE)

        assert by_frame == {0: frozenset({"toca"}), 1: frozenset()}

    def test_no_rois_or_no_trajectory(self):
        assert subject_rois_by_frame(None, [ROI_SQUARE], CENTROID_RULE) == {}
        assert subject_rois_by_frame(_trajectory([0], [50.0]), [], CENTROID_RULE) == {}


class TestTrajectoryOnly:
    def test_grid_frames_without_a_subject_row_are_absences(self):
        trajectory = _trajectory([0, 1, 4, 5], [300.0] * 4)

        built = build_window_observations(trajectory)

        assert [o.frame for o in built.observations] == [0, 1, 2, 3, 4, 5]
        assert [o.t_s for o in built.observations] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        present = [bool(o.classes) for o in built.observations]
        assert present == [True, True, False, False, True, True]
        assert built.observations[0].classes == {TRAJECTORY_SUBJECT_CLASS: (0.8,)}
        assert built.role_names["subject"] == frozenset({TRAJECTORY_SUBJECT_CLASS})
        assert built.has_objects is False
        assert len(built.warnings) == 1

    def test_the_grid_follows_the_processing_cadence(self):
        trajectory = _trajectory([0, 10, 20, 50], [300.0] * 4)

        built = build_window_observations(trajectory)

        assert [o.frame for o in built.observations] == [0, 10, 20, 30, 40, 50]

    def test_a_known_subject_name_is_the_class_key(self):
        trajectory = _trajectory([0, 1], [300.0, 300.0])

        built = build_window_observations(trajectory, subject_names=["Rat"])

        assert set(built.observations[0].classes) == {"rat"}
        assert built.role_names["subject"] == frozenset({"rat"})
        assert built.subject_names == frozenset({"rat"})

    def test_role_subject_condition_evaluates_without_a_sidecar(self):
        trajectory = _trajectory([0, 1, 2, 3, 4], [300.0] * 5)
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_role("subject")), hold=Hold(frames=2)
            )
        )
        built = build_window_observations(trajectory)

        result = evaluate_window(spec, built.observations, role_names=built.role_names)

        assert result.start is not None
        assert result.start.frame == 0

    def test_empty_trajectory_has_no_observations(self):
        built = build_window_observations(None)

        assert built.observations == ()
        assert built.warnings


class TestMissingInputs:
    SPEC = WindowSpec(
        start=Persist(
            level=AllOfLevel(
                children=(
                    ClassPresence(target=ClassTarget.of_class("start_box"), present=False),
                    ClassPresence(target=ClassTarget.of_class("rat")),
                    RoiInside(roi="toca", state="outside"),
                )
            ),
            hold=Hold(frames=1),
        )
    )

    def test_context_class_without_sidecar_is_missing(self):
        missing = missing_inputs(
            self.SPEC, has_objects=False, subject_names=["rat"], roi_names=["toca"]
        )

        assert missing == ["class:start_box"]

    def test_with_the_sidecar_classes_are_available(self):
        assert (
            missing_inputs(self.SPEC, has_objects=True, subject_names=[], roi_names=["toca"]) == []
        )

    def test_unknown_subject_name_is_missing_without_sidecar(self):
        missing = missing_inputs(self.SPEC, has_objects=False, subject_names=[], roi_names=["toca"])

        assert missing == ["class:rat", "class:start_box"]

    def test_context_role_and_unknown_roi(self):
        spec = WindowSpec(
            start=Persist(
                level=AllOfLevel(
                    children=(
                        ClassPresence(target=ClassTarget.of_role("context"), present=False),
                        ClassPresence(target=ClassTarget.of_role("subject")),
                    )
                ),
                hold=Hold(frames=1),
            ),
            stop=Persist(level=RoiInside(roi="ghost", state="inside"), hold=Hold(frames=1)),
        )

        missing = missing_inputs(spec, has_objects=False, subject_names=[], roi_names=["toca"])

        assert missing == ["roi:ghost", "role:context"]


def test_role_names_from_metadata_ignores_other_roles():
    roles = role_names_from_metadata({"Rat": "subject", "arena": "arena", "box": "context"})

    assert roles == {"subject": frozenset({"rat"}), "context": frozenset({"box"})}


@settings(max_examples=30, deadline=None)
@given(frames=st.sets(st.integers(min_value=0, max_value=500), min_size=1, max_size=40))
def test_property_one_observation_per_heartbeat(tmp_path_factory, frames):
    tmp = tmp_path_factory.mktemp("objects")
    rows = [_heartbeat(f, f / 9.9) for f in frames]

    built = build_window_observations(None, objects_df=_objects(tmp, rows))

    assert [o.frame for o in built.observations] == sorted(frames)
    times = np.array([o.t_s for o in built.observations])
    assert np.all(np.diff(times) > 0)
