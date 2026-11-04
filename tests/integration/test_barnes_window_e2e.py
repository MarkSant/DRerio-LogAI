"""Barnes maze end to end: the analysis window on the REAL pre-recorded pipeline (ADR-011).

The acceptance case of v8. A synthetic Barnes trial (``write_barnes_video``)
draws each class in its own colour channel: the experimenter and the start box
are visible at the beginning and leave, the rat appears, walks, enters the
escape-hole ROI ``toca`` and disappears into the escape box. The real worker
(``_WorkerProcess``) tracks it with a weight that has no file but an explicit
class-role map, writing the trajectory and the ``3c_Objetos_`` sidecar; then the
window is resolved from what was recorded and applied to the metrics.

Timeline (video at 10 fps, settings at 30 fps on purpose)::

    frames 0-19   start box visible
    frames 0-24   experimenter visible
    frames 15-69  rat visible; its box reaches toca at frame 40
    frames 70-89  rat gone (in the escape box)

So START (start box and experimenter absent, rat present, held 3 frames) is
frame 25 = 2.5 s; STOP (rat absent for 1 s, back-dated) is frame 70 = 7.0 s;
the latency to ``toca`` counted from START is 4.0 - 2.5 = 1.5 s.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.helpers.prerecorded_pipeline import (
    BARNES_ARENA,
    BARNES_ROI_NAMES,
    BARNES_TOCA,
    BarnesRun,
    load_pristine_settings,
    run_barnes_pipeline,
)
from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.analysis_window_service import (
    WindowResolution,
    analysis_window_artifact_path,
    resolve_analysis_window,
)
from zebtrack.analysis.roi_builder import build_rois_from_zone_polygons
from zebtrack.analysis.time_base import resolve_time_base
from zebtrack.core.conditions import read_artifact
from zebtrack.core.conditions.presets import barnes_maze_preset
from zebtrack.io.object_sidecar import HEARTBEAT_CLASS_ID, read_object_sidecar

pytestmark = pytest.mark.integration

K_FRAMES = 3
ABSENT_S = 1.0


@pytest.fixture(scope="module")
def barnes(tmp_path_factory) -> tuple[BarnesRun, pd.DataFrame]:
    settings = load_pristine_settings()
    assert settings.video_processing.fps == 30  # the video is 10 fps: they disagree
    try:
        run = run_barnes_pipeline(tmp_path_factory.mktemp("barnes"), settings)
    except RuntimeError as exc:  # no codec on this machine
        pytest.skip(f"Cannot build the Barnes fixture video: {exc}")
    return run, pd.read_parquet(run.trajectory_path)


def _rois():
    return build_rois_from_zone_polygons([BARNES_TOCA], list(BARNES_ROI_NAMES))


def _resolve(run: BarnesRun, trajectory: pd.DataFrame, **preset) -> WindowResolution:
    spec = barnes_maze_preset(k_frames=K_FRAMES, absent_s=ABSENT_S, **preset)
    project = {"analysis_window": spec.model_dump(mode="json", by_alias=True)}
    service = AnalysisService(settings_obj=load_pristine_settings())
    window = resolve_analysis_window(
        project,
        run.trajectory_path,
        trajectory_df=trajectory,
        rois=_rois(),
        roi_rule=service.resolve_roi_rule(),
    )
    assert window is not None
    return window


def _analyse(trajectory: pd.DataFrame, window: WindowResolution | None) -> dict:
    settings = load_pristine_settings()
    report, *_ = AnalysisService(settings_obj=settings).run_full_analysis(
        trajectory_df=trajectory.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=BARNES_ARENA,
        rois=_rois(),
        fps=float(settings.video_processing.fps),  # 30: only the warned fallback
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        window=window,
    )
    return report


def test_object_sidecar_has_heartbeats_and_context_rows(barnes):
    run, _trajectory = barnes
    objects = read_object_sidecar(run.objects_path)
    assert objects is not None

    beats = objects[objects["class_id"] == HEARTBEAT_CLASS_ID]
    assert sorted(beats["frame"]) == list(range(90))
    by_class = objects.groupby("class_name")["frame"].agg(["min", "max", "count"])
    assert by_class.loc["start_box"].tolist() == [0, 19, 20]
    assert by_class.loc["experimenter"].tolist() == [0, 24, 25]
    assert by_class.loc["rat"].tolist() == [15, 69, 55]
    metadata = objects.attrs["objects_metadata"]
    assert metadata.class_roles["experimenter"] == "context"
    assert metadata.class_roles["rat"] == "subject"


def test_start_is_the_first_frame_of_the_condition_and_stop_is_backdated(barnes):
    run, trajectory = barnes

    window = _resolve(run, trajectory)

    assert window.status == "complete"
    assert window.start is not None and window.stop is not None
    assert (window.start.frame, window.start.reason) == (25, "persist")
    assert window.start.t_s == pytest.approx(2.5)
    assert (window.stop.frame, window.stop.reason) == (70, "persist")
    assert window.stop.t_s == pytest.approx(7.0)
    assert window.window_duration_s == pytest.approx(4.5)
    assert window.censored is False


def test_the_video_clock_beats_the_settings_fps(barnes):
    _run, trajectory = barnes

    time_base = resolve_time_base(trajectory, fallback_fps=30.0)

    # PTS of a 10 fps video: frame 25 is 2.5 s, not 25 / 30 = 0.83 s.
    assert time_base.fps_video == pytest.approx(10.0)
    row = trajectory.loc[trajectory["frame"] == 25, "timestamp"]
    assert float(row.iloc[0]) == pytest.approx(2.5)


def test_trajectory_keeps_the_rows_before_start(barnes):
    _run, trajectory = barnes

    assert int(trajectory["frame"].min()) == 15
    assert (trajectory["frame"] < 25).sum() == 10


def test_metrics_are_cut_to_the_window(barnes):
    run, trajectory = barnes
    window = _resolve(run, trajectory)

    report = _analyse(trajectory, window)

    block = report["analysis_window"]
    assert block["status"] == "complete"
    assert block["window_duration_s"] == pytest.approx(4.5)
    assert block["start"]["frame"] == 25 and block["stop"]["frame"] == 70
    # Latency to the escape hole counted from START, not from the first detection.
    assert report["analise_roi"]["latencia_primeira_entrada"]["toca"] == pytest.approx(1.5)
    assert report["latency_censored"]["toca"] is False
    assert report["latency_present_at_start"]["toca"] is False
    # Rows 25..69: the rows before START are kept on disk, not in the metrics.
    assert report["comportamento_geral"]["total_frames_analisados"] == 45
    plain = _analyse(trajectory, None)
    assert plain["analise_roi"]["latencia_primeira_entrada"]["toca"] == pytest.approx(2.5)
    assert plain["analysis_window"] == {"status": "none"}


def test_ceiling_delay_censors_the_latency_at_the_window_length(barnes):
    """The 240 s protocol ceiling, scaled down to 1 s so it fires before ``toca``."""
    run, trajectory = barnes
    window = _resolve(run, trajectory, max_s=1.0)

    assert window.stop is not None
    assert (window.stop.frame, window.stop.reason) == (35, "delay")
    assert window.window_duration_s == pytest.approx(1.0)

    report = _analyse(trajectory, window)

    assert report["latency_censored"]["toca"] is True
    assert report["analise_roi"]["latencia_primeira_entrada"]["toca"] == pytest.approx(1.0)


def test_artifact_is_written_and_reused(barnes):
    run, trajectory = barnes
    first = _resolve(run, trajectory)
    path = analysis_window_artifact_path(run.trajectory_path)

    artifact = read_artifact(path)
    second = _resolve(run, trajectory)

    assert Path(path).name == "7_AnalysisWindow_BARNES_01.json"
    assert artifact is not None and artifact.offline is not None
    assert artifact.offline.start is not None and artifact.offline.start.frame == 25
    assert artifact.clock == "pts"
    assert artifact.fps_video == pytest.approx(10.0)
    assert second.reused is True
    assert (second.start, second.stop) == (first.start, first.stop)
