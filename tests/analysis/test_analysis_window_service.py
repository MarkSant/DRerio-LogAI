"""Tests for ``analysis/analysis_window_service.py`` (ADR-011, front F4b)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from shapely.geometry import Polygon

import zebtrack.analysis.analysis_window_service as service_module
from zebtrack.analysis.analysis_window_service import (
    AnalysisWindowService,
    InvalidWindowSpecError,
    WindowBound,
    WindowResolution,
    analysis_window_artifact_path,
    project_subject_names,
    resolve_analysis_window,
    resolve_window_spec,
)
from zebtrack.analysis.roi import ROI
from zebtrack.core.conditions import (
    AllOfLevel,
    AnalysisWindowArtifact,
    ArtifactEvent,
    ArtifactExternalEvent,
    ClassPresence,
    ClassTarget,
    External,
    Hold,
    OnlineWindow,
    Persist,
    RoiInside,
    WindowSpec,
    read_artifact,
    spec_hash,
    write_artifact,
)
from zebtrack.io.object_sidecar import ObjectSidecarMetadata, build_object_table

NAMES = {0: "arena", 1: "experimenter", 2: "rat"}
ROLES = {"experimenter": "context", "rat": "subject"}
FPS = 10.0
BASE = "S01"


def _spec(**overrides) -> WindowSpec:
    start = Persist(
        level=AllOfLevel(
            children=(
                ClassPresence(target=ClassTarget.of_class("experimenter"), present=False),
                ClassPresence(target=ClassTarget.of_class("rat")),
            )
        ),
        hold=Hold(frames=3),
    )
    stop = Persist(
        level=ClassPresence(target=ClassTarget.of_class("rat"), present=False),
        hold=Hold(seconds=0.5),
    )
    fields = {"start": start, "stop": stop, **overrides}
    return WindowSpec(**fields)


def _write_recording(
    folder: Path,
    *,
    experimenter_until: int = 9,
    rat_frames: range = range(5, 30),
    n_frames: int = 40,
    with_objects: bool = True,
) -> Path:
    """Trajectory + 3c of a synthetic session at 10 fps; returns the trajectory path."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for frame in range(n_frames):
        t = round(frame / FPS, 9)
        rows.append(
            {
                "frame": frame,
                "timestamp": t,
                "t_event_s": t,
                "class_id": -1,
                "class_name": None,
                "role": "frame",
            }
        )
        if frame <= experimenter_until:
            rows.append(_det(frame, t, 1))
        if frame in rat_frames:
            rows.append(_det(frame, t, 2))
    if with_objects:
        metadata = ObjectSidecarMetadata(class_names=NAMES, class_roles=ROLES, clock="pts")
        pq.write_table(build_object_table(rows, metadata), folder / f"3c_Objetos_{BASE}.parquet")
    trajectory = pd.DataFrame(
        {
            "timestamp": [round(f / FPS, 9) for f in rat_frames],
            "frame": list(rat_frames),
            "track_id": [1] * len(rat_frames),
            "x1": [f * 4.0 for f in rat_frames],
            "y1": [40.0] * len(rat_frames),
            "x2": [f * 4.0 + 10 for f in rat_frames],
            "y2": [50.0] * len(rat_frames),
            "confidence": [0.9] * len(rat_frames),
        }
    )
    trajectory["x_center_px"] = (trajectory["x1"] + trajectory["x2"]) / 2
    trajectory["y_center_px"] = 45.0
    path = folder / f"3_CoordMovimento_{BASE}.parquet"
    trajectory.to_parquet(path)
    return path


def _bound(bound: WindowBound | None) -> tuple[int, float, str | None] | None:
    return None if bound is None else (bound.frame, bound.t_s, bound.reason)


def _det(frame: int, t: float, class_id: int) -> dict:
    name = NAMES[class_id]
    return {
        "frame": frame,
        "timestamp": t,
        "t_event_s": t,
        "class_id": class_id,
        "class_name": name,
        "role": ROLES[name],
        "x1": 1.0,
        "y1": 1.0,
        "x2": 2.0,
        "y2": 2.0,
        "confidence": 0.9,
    }


class TestResolve:
    def test_computes_the_window_and_writes_the_artifact(self, tmp_path):
        trajectory = _write_recording(tmp_path)

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert resolution.status == "complete"
        assert _bound(resolution.start) == (10, pytest.approx(1.0), "persist")
        assert _bound(resolution.stop) == (30, pytest.approx(3.0), "persist")
        assert resolution.window_duration_s == pytest.approx(2.0)
        assert resolution.reused is False
        assert resolution.clock == "pts"
        assert resolution.to_report()["spec"] == _spec().model_dump(mode="json", by_alias=True)
        artifact = read_artifact(tmp_path / f"7_AnalysisWindow_{BASE}.json")
        assert artifact is not None
        assert artifact.spec_hash == spec_hash(_spec())
        assert artifact.offline is not None
        assert artifact.offline.start is not None and artifact.offline.start.frame == 10
        assert set(artifact.offline.inputs) == {"trajectory_sha", "objects_sha"}
        assert artifact.fps_video == pytest.approx(10.0)

    def test_second_resolution_reuses_the_offline_section(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        AnalysisWindowService().resolve(trajectory, _spec())

        again = AnalysisWindowService().resolve(trajectory, _spec())

        assert again.reused is True
        assert again.start is not None and again.start.frame == 10
        assert again.stop is not None and again.stop.frame == 30

    def test_a_changed_spec_is_recomputed(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        AnalysisWindowService().resolve(trajectory, _spec())
        other = _spec(on_start_not_met="empty")

        again = AnalysisWindowService().resolve(trajectory, other)

        assert again.reused is False
        artifact = read_artifact(analysis_window_artifact_path(trajectory))
        assert artifact is not None and artifact.spec_hash == spec_hash(other)

    def test_a_changed_object_sidecar_is_recomputed(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        AnalysisWindowService().resolve(trajectory, _spec())
        _write_recording(tmp_path, experimenter_until=14)

        again = AnalysisWindowService().resolve(trajectory, _spec())

        assert again.reused is False
        assert again.start is not None and again.start.frame == 15

    def test_a_changed_trajectory_is_recomputed(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        AnalysisWindowService().resolve(trajectory, _spec())
        df = pd.read_parquet(trajectory)
        df.loc[0, "confidence"] = 0.5
        df.to_parquet(trajectory)

        assert AnalysisWindowService().resolve(trajectory, _spec()).reused is False

    def test_changed_rois_are_recomputed_when_the_spec_uses_them(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        spec = _spec(stop=Persist(level=RoiInside(roi="toca", state="inside"), hold=Hold(frames=1)))
        near = ROI("toca", Polygon([(0, 0), (60, 0), (60, 100), (0, 100)]), "px")
        far = ROI("toca", Polygon([(80, 0), (200, 0), (200, 100), (80, 100)]), "px")
        service = AnalysisWindowService()
        first = service.resolve(trajectory, spec, rois=[near])

        second = service.resolve(trajectory, spec, rois=[far])

        assert second.reused is False
        assert first.stop is not None and second.stop is not None
        assert first.stop.frame != second.stop.frame

    def test_without_a_trajectory_path_nothing_is_written(self, tmp_path):
        trajectory = _write_recording(tmp_path, with_objects=False)
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_role("subject")), hold=Hold(frames=2)
            )
        )

        resolution = AnalysisWindowService().resolve(
            None, spec, trajectory_df=pd.read_parquet(trajectory)
        )

        assert resolution.artifact_path is None
        assert resolution.start is not None and resolution.start.frame == 5
        assert not list(tmp_path.glob("7_*"))

    def test_write_failure_still_returns_the_window(self, tmp_path, monkeypatch):
        trajectory = _write_recording(tmp_path)

        def _boom(*_args, **_kwargs):
            raise OSError("read-only")

        monkeypatch.setattr(service_module, "write_artifact", _boom)

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert resolution.status == "complete"
        assert not analysis_window_artifact_path(trajectory).exists()


class TestOnlineVersusOffline:
    def _seed(self, trajectory: Path, spec: WindowSpec, *, start_frame: int, **extra) -> None:
        artifact = AnalysisWindowArtifact.for_spec(
            spec,
            clock="pts",
            online=OnlineWindow(
                start=ArtifactEvent(frame=start_frame, t_s=start_frame / FPS, reason="persist")
            ),
            **extra,
        )
        write_artifact(analysis_window_artifact_path(trajectory), artifact)

    def test_offline_governs_and_a_divergence_is_reported(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        self._seed(trajectory, _spec(), start_frame=20)

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert resolution.start is not None and resolution.start.frame == 10
        assert any("frame 20" in w and "frame 10" in w for w in resolution.warnings)
        artifact = read_artifact(analysis_window_artifact_path(trajectory))
        assert artifact is not None
        assert artifact.online.start is not None and artifact.online.start.frame == 20

    def test_one_frame_apart_is_not_a_divergence(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        self._seed(trajectory, _spec(), start_frame=11)

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert not any("live session" in w for w in resolution.warnings)

    def test_reused_window_still_reports_the_divergence(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        self._seed(trajectory, _spec(), start_frame=25)
        AnalysisWindowService().resolve(trajectory, _spec())

        again = AnalysisWindowService().resolve(trajectory, _spec())

        assert again.reused is True
        assert any("frame 25" in w for w in again.warnings)

    def test_external_events_survive_and_drive_the_window(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        spec = WindowSpec(start=External(source="arduino", code=1))
        self._seed(
            trajectory,
            _spec(),  # recorded under another spec: the events are still facts
            start_frame=3,
            external_events=(ArtifactExternalEvent(t_s=1.25, source="arduino", code=1),),
        )

        resolution = AnalysisWindowService().resolve(trajectory, spec)

        assert resolution.start is not None and resolution.start.frame == 13
        artifact = read_artifact(analysis_window_artifact_path(trajectory))
        assert artifact is not None
        assert [e.code for e in artifact.external_events] == [1]
        # The online section belonged to the other spec and is dropped.
        assert artifact.online.start is None


class TestNotMet:
    def test_start_never_met_uses_the_whole_recording(self, tmp_path):
        trajectory = _write_recording(tmp_path, experimenter_until=39)

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert resolution.status == "start_not_met"
        assert resolution.applied == "whole_recording"
        assert resolution.cut is None
        assert resolution.window_duration_s is None
        assert resolution.reason == "start_not_met"
        assert any("never started" in w for w in resolution.warnings)

    def test_start_never_met_with_empty_policy(self, tmp_path):
        trajectory = _write_recording(tmp_path, experimenter_until=39)

        resolution = AnalysisWindowService().resolve(trajectory, _spec(on_start_not_met="empty"))

        assert resolution.is_empty is True
        assert resolution.applied == "empty"
        assert resolution.window_duration_s == 0.0
        assert any("empty" in w for w in resolution.warnings)

    def test_stop_never_met_is_censored_at_the_end(self, tmp_path):
        trajectory = _write_recording(tmp_path, rat_frames=range(5, 40))

        resolution = AnalysisWindowService().resolve(trajectory, _spec())

        assert resolution.status == "censored"
        assert resolution.censored is True
        assert resolution.stop is not None
        assert resolution.stop.frame == 39
        assert resolution.reason == "end_of_stream"
        assert any("censored" in w for w in resolution.warnings)

    def test_context_condition_without_sidecar_is_inputs_missing(self, tmp_path):
        trajectory = _write_recording(tmp_path, with_objects=False)

        resolution = AnalysisWindowService().resolve(trajectory, _spec(), subject_names=["rat"])

        assert resolution.status == "inputs_missing"
        assert resolution.missing == ("class:experimenter",)
        assert resolution.applied == "whole_recording"
        assert any("class:experimenter" in w for w in resolution.warnings)
        assert any("3c_Objetos_" in w for w in resolution.warnings)
        artifact = read_artifact(analysis_window_artifact_path(trajectory))
        assert artifact is not None and artifact.offline is not None
        assert artifact.offline.status == "inputs_missing"
        assert artifact.offline.inputs["objects_sha"] is None

    def test_reused_inputs_missing_keeps_its_explanation(self, tmp_path):
        trajectory = _write_recording(tmp_path, with_objects=False)
        AnalysisWindowService().resolve(trajectory, _spec(), subject_names=["rat"])

        again = AnalysisWindowService().resolve(trajectory, _spec(), subject_names=["rat"])

        assert again.reused is True
        assert again.status == "inputs_missing"
        assert again.missing


class TestSpecLookup:
    def test_no_project_or_no_key_is_the_whole_recording(self):
        assert resolve_window_spec(None) is None
        assert resolve_window_spec({"analysis_window": None}) is None
        assert resolve_window_spec({}) is None

    def test_project_spec_is_validated(self):
        raw = _spec().model_dump(mode="json", by_alias=True)

        spec = resolve_window_spec({"analysis_window": raw})

        assert spec is not None and spec_hash(spec) == spec_hash(_spec())

    def test_a_video_entry_key_wins_even_when_none(self):
        raw = _spec().model_dump(mode="json", by_alias=True)

        assert resolve_window_spec({"analysis_window": raw}, {"analysis_window": None}) is None
        assert resolve_window_spec({"analysis_window": None}, {"analysis_window": raw})
        assert resolve_window_spec({"analysis_window": raw}, {"path": "x.mp4"}) is not None

    def test_an_invalid_spec_raises_instead_of_analysing_everything(self):
        with pytest.raises(InvalidWindowSpecError):
            resolve_window_spec({"analysis_window": {"version": 1, "start": {"kind": "nope"}}})

    def test_project_subject_names(self):
        project = {"model_overrides": {"class_roles": {"rat": "subject", "box": "context"}}}

        assert project_subject_names(project) == ["rat"]
        assert project_subject_names({"model_overrides": {"class_roles": None}}) == []
        assert project_subject_names(None) == []


def test_artifact_path_is_derived_from_the_trajectory(tmp_path):
    nested = tmp_path / "Grupo_A" / "Dia_1" / "Sujeito_2"
    trajectory = nested / "3_CoordMovimento_V1_aquarium_2.parquet"

    assert analysis_window_artifact_path(trajectory) == (
        nested / "7_AnalysisWindow_V1_aquarium_2.json"
    )
    assert analysis_window_artifact_path(tmp_path / "other.parquet") == (
        tmp_path / "7_AnalysisWindow_other.json"
    )


class TestResolveAnalysisWindow:
    def test_no_spec_is_none(self, tmp_path):
        trajectory = _write_recording(tmp_path)

        assert resolve_analysis_window({"analysis_window": None}, trajectory) is None

    def test_project_spec_resolves(self, tmp_path):
        trajectory = _write_recording(tmp_path)
        project = {"analysis_window": _spec().model_dump(mode="json", by_alias=True)}

        resolution = resolve_analysis_window(project, trajectory)

        assert resolution is not None
        assert resolution.start is not None and resolution.start.frame == 10

    def test_project_subject_names_reach_the_trajectory_only_path(self, tmp_path):
        trajectory = _write_recording(tmp_path, with_objects=False)
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_class("rat")), hold=Hold(frames=2)
            )
        )
        project = {
            "analysis_window": spec.model_dump(mode="json", by_alias=True),
            "model_overrides": {"class_roles": {"rat": "subject"}},
        }

        resolution = resolve_analysis_window(project, trajectory)

        assert resolution is not None
        # No STOP condition: the window ends with the stream, uncensored. Without
        # a 3c the stream ends at the subject's last row.
        assert resolution.status == "complete"
        assert resolution.start is not None and resolution.start.frame == 5
        assert _bound(resolution.stop) == (29, pytest.approx(2.9), "end_of_stream")


class TestResolutionReport:
    def test_report_shape(self):
        resolution = WindowResolution(
            status="complete",
            spec_hash="sha256:" + "0" * 64,
            start=WindowBound(3, 0.3, "persist"),
            stop=WindowBound(9, 0.9, "delay"),
        )

        report = resolution.to_report()

        assert report == {
            "status": "complete",
            "applied": "window",
            "start": {"frame": 3, "t_s": 0.3, "reason": "persist"},
            "stop": {"frame": 9, "t_s": 0.9, "reason": "delay"},
            "reason": "delay",
            "censored": False,
            "spec_hash": "sha256:" + "0" * 64,
            "window_duration_s": pytest.approx(0.6),
            "clock": "pts",
            "on_start_not_met": "whole_recording",
            "missing_inputs": [],
            "spec": None,
        }
        json.dumps(report)

    def test_cache_token_depends_on_the_bounds(self):
        a = WindowResolution(
            status="complete",
            spec_hash="sha256:x",
            start=WindowBound(3, 0.3),
            stop=WindowBound(9, 0.9),
        )
        b = WindowResolution(
            status="complete",
            spec_hash="sha256:x",
            start=WindowBound(3, 0.3),
            stop=WindowBound(8, 0.8),
        )
        empty = WindowResolution(
            status="start_not_met", spec_hash="sha256:x", on_start_not_met="empty"
        )

        assert a.cache_token() != b.cache_token()
        assert empty.cache_token() != a.cache_token()
        assert "empty" in empty.cache_token()
