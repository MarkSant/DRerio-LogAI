from pathlib import Path

import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService, mask_sidecar_in_local_space
from zebtrack.analysis.analysis_window_service import WindowBound, WindowResolution
from zebtrack.settings import Settings, load_settings


@pytest.fixture
def settings_obj() -> Settings:
    """Load settings for tests."""
    return load_settings()


@pytest.fixture
def trajectory_file(tmp_path: Path) -> Path:
    """Create a dummy trajectory file for testing."""
    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2],
            "frame": [0, 1, 2],
            "track_id": [1, 1, 1],
            "x1": [10, 11, 12],
            "y1": [20, 21, 22],
            "x2": [30, 31, 32],
            "y2": [40, 41, 42],
        }
    )
    file_path = tmp_path / "trajectory.parquet"
    df.to_parquet(file_path)
    return file_path


def test_load_trajectory_dataframe_success(settings_obj: Settings, trajectory_file: Path):
    """Test that the service can load a valid trajectory file."""
    service = AnalysisService(settings_obj=settings_obj)
    df = service.load_trajectory_dataframe(trajectory_file)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert "track_id" in df.columns


def test_load_trajectory_dataframe_not_found(settings_obj: Settings):
    """Test that the service raises an error if the file is not found."""
    service = AnalysisService(settings_obj=settings_obj)
    with pytest.raises(FileNotFoundError):
        service.load_trajectory_dataframe("non_existent_file.parquet")


def test_collect_analysis_parameters_defaults(settings_obj: Settings):
    """Test that the service returns default parameters when no project data is provided."""
    service = AnalysisService(settings_obj=settings_obj)
    params = service.collect_analysis_parameters()
    assert (
        params["freezing_vel_threshold"]
        == settings_obj.video_processing.freezing_velocity_threshold
    )
    assert params["freezing_min_duration"] == settings_obj.video_processing.freezing_min_duration_s
    assert params["smoothing_window_length"] == settings_obj.trajectory_smoothing.window_length
    assert params["smoothing_polyorder"] == settings_obj.trajectory_smoothing.polyorder


def test_collect_analysis_parameters_with_overrides(settings_obj: Settings):
    """Test that the service correctly applies project-specific overrides."""
    service = AnalysisService(settings_obj=settings_obj)
    project_data = {
        "analysis_parameters": {
            "freezing_vel_threshold": 0.5,
            "smoothing_window_length": 11,
        }
    }
    params = service.collect_analysis_parameters(project_data)
    assert params["freezing_vel_threshold"] == 0.5
    assert params["smoothing_window_length"] == 11
    # Ensure other params fall back to defaults
    assert params["freezing_min_duration"] == settings_obj.video_processing.freezing_min_duration_s


def test_collect_analysis_parameters_honors_project_thresholds(settings_obj: Settings):
    """The nested ``analysis`` dict is what the reporters read.

    ``sharp_turn_threshold`` had no project home at all, even though the ad-hoc
    dialogs overwrite it globally; the freezing pair reached the flat keys but
    not the nested ones the reporters consume.
    """
    service = AnalysisService(settings_obj=settings_obj)
    params = service.collect_analysis_parameters(
        {
            "analysis_parameters": {
                "sharp_turn_threshold": 45.0,
                "freezing_vel_threshold": 3.25,
                "freezing_min_duration": 2.5,
            }
        }
    )

    assert params["analysis"]["sharp_turn_threshold"] == 45.0
    assert params["analysis"]["freezing_threshold"] == 3.25
    assert params["analysis"]["freezing_min_duration"] == 2.5


def test_collect_analysis_parameters_nested_analysis_falls_back(settings_obj: Settings):
    service = AnalysisService(settings_obj=settings_obj)
    params = service.collect_analysis_parameters({})

    assert params["analysis"]["sharp_turn_threshold"] == (
        settings_obj.video_processing.sharp_turn_threshold_deg_s
    )


def test_validate_trajectory_schema_success(settings_obj: Settings):
    """Test that the schema validation passes with a valid dataframe."""
    service = AnalysisService(settings_obj=settings_obj)
    df = pd.DataFrame(
        {
            "timestamp": [],
            "frame": [],
            "track_id": [],
            "x1": [],
            "y1": [],
            "x2": [],
            "y2": [],
        }
    )
    assert service.validate_trajectory_schema(df) is True


def test_validate_trajectory_schema_missing_columns(settings_obj: Settings):
    """Test that schema validation fails if columns are missing."""
    service = AnalysisService(settings_obj=settings_obj)
    df = pd.DataFrame({"timestamp": [], "frame": []})
    with pytest.raises(ValueError, match="missing required columns"):
        service.validate_trajectory_schema(df)


# ---------------------------------------------------------------------------
# Recording duration from the time base, not rows / fps
# ---------------------------------------------------------------------------

_ARENA = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]


def _moving_track(frames, timestamps, track_id: int, y: float) -> pd.DataFrame:
    frames = list(frames)
    x = [50.0 + 2.0 * (f % 50) for f in frames]
    return pd.DataFrame(
        {
            "timestamp": list(timestamps),
            "frame": frames,
            "track_id": [track_id] * len(frames),
            "x1": [v - 5 for v in x],
            "y1": [y - 5] * len(frames),
            "x2": [v + 5 for v in x],
            "y2": [y + 5] * len(frames),
            "x_center_px": x,
            "y_center_px": [y] * len(frames),
        }
    )


def _run(settings_obj: Settings, df: pd.DataFrame, fps: float, rois=None, **kwargs):
    service = AnalysisService(settings_obj=settings_obj)
    report, *_rest = service.run_full_analysis(
        trajectory_df=df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=rois or [],
        fps=fps,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        **kwargs,
    )
    return report


def test_duration_two_tracks_is_time_not_rows(settings_obj: Settings):
    """2 tracks x 100 frames at 10 fps last 10 s; ``len(df)/fps`` said 20."""
    frames = range(100)
    df = pd.concat(
        [
            _moving_track(frames, [f / 10 for f in frames], 1, 100.0),
            _moving_track(frames, [f / 10 for f in frames], 2, 300.0),
        ],
        ignore_index=True,
    )

    report = _run(settings_obj, df, fps=10.0)

    assert report["comportamento_geral"]["duracao_video_s"] == pytest.approx(10.0)
    assert report["validacao"]["estatisticas"]["duration_s"] == pytest.approx(10.0)


def test_duration_survives_frames_without_subject(settings_obj: Settings):
    """Half the frames with no detection (a block in the middle) is still 10 s."""
    frames = [*range(0, 25), *range(75, 100)]
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    report = _run(settings_obj, df, fps=10.0)

    assert report["comportamento_geral"]["duracao_video_s"] == pytest.approx(10.0)


def test_duration_with_analysis_interval_ten_is_real_time(settings_obj: Settings):
    """Every 10th frame of a 10 fps video: 10 rows, 10 s — rows/fps said 1 s."""
    frames = range(0, 100, 10)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    report = _run(settings_obj, df, fps=10.0)

    assert report["comportamento_geral"]["duracao_video_s"] == pytest.approx(10.0)


def test_duration_ignores_a_wrong_configured_fps(settings_obj: Settings):
    """settings at 30 fps, PTS at 10 fps: the PTS decides."""
    frames = range(100)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    report = _run(settings_obj, df, fps=30.0)

    assert report["comportamento_geral"]["duracao_video_s"] == pytest.approx(10.0)
    assert report["validacao"]["avisos"] == []


def test_analysis_window_is_always_reported(settings_obj: Settings):
    frames = range(30)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    report = _run(settings_obj, df, fps=10.0)

    assert report["analysis_window"] == {"status": "none"}
    assert report["latency_censored"] == {}
    assert report["latency_present_at_start"] == {}


def test_a_window_that_is_not_a_resolution_is_refused(settings_obj: Settings):
    frames = range(30)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    with pytest.raises(TypeError, match="WindowResolution"):
        _run(settings_obj, df, fps=10.0, window=object())


def test_latency_flags_reach_the_report(settings_obj: Settings):
    """Born inside ``Left``: latency 0 and present at start; ``Far`` never entered."""
    from shapely.geometry import Polygon

    from zebtrack.analysis.roi import ROI

    frames = range(60)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)
    rois = [
        ROI("Left", Polygon([(0, 0), (60, 0), (60, 400), (0, 400)]), coordinate_space="px"),
        ROI("Far", Polygon([(350, 350), (400, 350), (400, 400), (350, 400)]), "px"),
    ]

    report = _run(settings_obj, df, fps=10.0, rois=rois)

    roi = report["analise_roi"]
    assert roi["latencia_primeira_entrada"]["Left"] == 0.0
    assert roi["latencia_primeira_entrada"]["Far"] is None
    assert report["latency_present_at_start"] == {"Left": True, "Far": False}
    assert report["latency_censored"] == {"Left": False, "Far": True}
    (per_animal,) = roi["por_animal"].values()
    assert per_animal["latency_present_at_start"] == {"Left": True, "Far": False}
    assert report["analysis_window"] == {"status": "none"}


# === Analysis window (ADR-011, F4b) ===


def _window(start: float | None, stop: float | None, **kwargs) -> WindowResolution:
    fields: dict = {"status": "complete", "spec_hash": "sha256:" + "a" * 64}
    if start is not None and stop is not None:
        fields["start"] = WindowBound(round(start * 10), start, "persist")
        fields["stop"] = WindowBound(round(stop * 10), stop, "delay")
    fields.update(kwargs)
    return WindowResolution(**fields)


def _rois():
    from shapely.geometry import Polygon

    from zebtrack.analysis.roi import ROI

    return [
        ROI("Left", Polygon([(0, 0), (60, 0), (60, 400), (0, 400)]), coordinate_space="px"),
        ROI("Right", Polygon([(100, 0), (400, 0), (400, 400), (100, 400)]), "px"),
        ROI("Far", Polygon([(350, 350), (400, 350), (400, 400), (350, 400)]), "px"),
    ]


def _walk() -> pd.DataFrame:
    frames = range(45)
    return _moving_track(frames, [round(f / 10, 9) for f in frames], 1, 100.0)


def _run_full(settings_obj: Settings, **kwargs):
    service = AnalysisService(settings_obj=settings_obj)
    return service.run_full_analysis(
        trajectory_df=_walk(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[],
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        **kwargs,
    )


def test_window_report_is_complete(settings_obj: Settings):
    report = _run(settings_obj, _walk(), fps=10.0, window=_window(1.0, 4.0))

    window = report["analysis_window"]
    assert window["status"] == "complete"
    assert window["applied"] == "window"
    assert window["start"] == {"frame": 10, "t_s": 1.0, "reason": "persist"}
    assert window["stop"] == {"frame": 40, "t_s": 4.0, "reason": "delay"}
    assert window["reason"] == "delay"
    assert window["window_duration_s"] == pytest.approx(3.0)
    assert window["censored"] is False
    assert window["clock"] == "pts"
    assert window["spec_hash"] == "sha256:" + "a" * 64
    # The recording length stays the recording's; the window has its own.
    assert report["comportamento_geral"]["duracao_video_s"] == pytest.approx(4.5)
    assert report["comportamento_geral"]["total_frames_analisados"] == 31


def test_window_distance_counts_only_steps_inside(settings_obj: Settings):
    whole = _run(settings_obj, _walk(), fps=10.0)
    cut = _run(settings_obj, _walk(), fps=10.0, window=_window(1.0, 4.0))

    # 2 px/frame at 10 px/cm = 0.2 cm per step; 30 steps inside [1.0, 4.0].
    assert cut["comportamento_geral"]["distancia_total_cm"] == pytest.approx(30 * 0.2, rel=0.05)
    assert (
        cut["comportamento_geral"]["distancia_total_cm"]
        < (whole["comportamento_geral"]["distancia_total_cm"])
    )


def test_window_velocity_is_computed_before_the_cut(settings_obj: Settings):
    full_v = _run_full(settings_obj)[1].trajectory_data["v_mag"]

    report, b_analyzer, *_ = _run_full(settings_obj, window=_window(1.0, 4.0))

    v = b_analyzer.trajectory_data["v_mag"]
    assert v.index[0] == pd.Timedelta(seconds=1.0)
    pd.testing.assert_series_equal(v, full_v.loc[v.index])
    assert report["comportamento_geral"]["estatisticas_velocidade"]["mean"] == pytest.approx(
        full_v.loc[v.index].mean()
    )


def test_window_latency_is_measured_from_start(settings_obj: Settings):
    plain = _run(settings_obj, _walk(), fps=10.0, rois=_rois())
    cut = _run(settings_obj, _walk(), fps=10.0, rois=_rois(), window=_window(1.0, 4.0))

    plain_latency = plain["analise_roi"]["latencia_primeira_entrada"]["Right"]
    cut_latency = cut["analise_roi"]["latencia_primeira_entrada"]["Right"]
    assert plain_latency > 1.0
    assert cut_latency == pytest.approx(plain_latency - 1.0)
    # Never entered: the ceiling is the window length, flagged as censored.
    assert cut["analise_roi"]["latencia_primeira_entrada"]["Far"] == pytest.approx(3.0)
    assert cut["latency_censored"]["Far"] is True
    assert plain["analise_roi"]["latencia_primeira_entrada"]["Far"] is None


def test_window_subject_inside_at_start_has_latency_zero(settings_obj: Settings):
    report = _run(settings_obj, _walk(), fps=10.0, rois=_rois(), window=_window(0.2, 4.0))

    assert report["analise_roi"]["latencia_primeira_entrada"]["Left"] == 0.0
    assert report["latency_present_at_start"]["Left"] is True
    assert report["analise_roi"]["contagem_entradas"]["Left"] == 0
    (per_animal,) = report["analise_roi"]["por_animal"].values()
    assert per_animal["latency_present_at_start"]["Left"] is True


def test_window_percentages_use_the_window(settings_obj: Settings):
    report = _run(settings_obj, _walk(), fps=10.0, rois=_rois(), window=_window(1.0, 4.0))

    times = report["analise_roi"]["tempo_gasto_por_roi"]
    assert times["Left"]["seconds"] + times["Right"]["seconds"] <= 3.0 + 1e-9
    right = times["Right"]
    assert right["percentage"] == pytest.approx(right["seconds"] / 3.0 * 100, rel=1e-6)


def test_start_not_met_analyses_the_whole_recording_with_a_warning(settings_obj: Settings):
    warning = "window never started"
    plain = _run(settings_obj, _walk(), fps=10.0, rois=_rois())
    report = _run(
        settings_obj,
        _walk(),
        fps=10.0,
        rois=_rois(),
        window=_window(None, None, status="start_not_met", warnings=(warning,)),
    )

    assert report["analysis_window"]["status"] == "start_not_met"
    assert report["analysis_window"]["applied"] == "whole_recording"
    assert report["analysis_window"]["window_duration_s"] is None
    assert warning in report["validacao"]["avisos"]
    assert report["comportamento_geral"]["distancia_total_cm"] == pytest.approx(
        plain["comportamento_geral"]["distancia_total_cm"]
    )
    assert report["comportamento_geral"]["total_frames_analisados"] == 45


def test_start_not_met_with_empty_policy_yields_empty_metrics(settings_obj: Settings):
    report = _run(
        settings_obj,
        _walk(),
        fps=10.0,
        rois=_rois(),
        window=_window(None, None, status="start_not_met", on_start_not_met="empty"),
    )

    assert report["analysis_window"]["applied"] == "empty"
    assert report["analysis_window"]["window_duration_s"] == 0.0
    assert report["comportamento_geral"]["distancia_total_cm"] == 0.0
    assert report["comportamento_geral"]["total_frames_analisados"] == 0
    assert report["analise_roi"]["tempo_gasto_por_roi"]["Right"]["seconds"] == 0.0
    assert report["analise_roi"]["latencia_primeira_entrada"]["Right"] is None


def test_whole_window_equals_no_window(settings_obj: Settings):
    plain = _run(settings_obj, _walk(), fps=10.0, rois=_rois())
    cut = _run(settings_obj, _walk(), fps=10.0, rois=_rois(), window=_window(0.0, 4.4))

    for key in ("distancia_total_cm", "tortuosidade"):
        assert cut["comportamento_geral"][key] == pytest.approx(plain["comportamento_geral"][key])
    assert cut["analise_roi"]["contagem_entradas"] == plain["analise_roi"]["contagem_entradas"]
    assert cut["analise_roi"]["latencia_primeira_entrada"]["Right"] == pytest.approx(
        plain["analise_roi"]["latencia_primeira_entrada"]["Right"]
    )


def test_dto_carries_the_window(settings_obj: Settings):
    service = AnalysisService(settings_obj=settings_obj)

    result = service.run_full_analysis_as_dto(
        trajectory_df=_walk(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[],
        fps=10.0,
        metadata={"experiment_id": "W"},
        roi_colors={},
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        window=_window(1.0, 4.0),
    )

    assert result.report["analysis_window"]["status"] == "complete"
    assert result.behavioral_analyzer.window_bounds == (1.0, 4.0)


def _still(frames, x: float) -> pd.DataFrame:
    frames = list(frames)
    return pd.DataFrame(
        {
            "timestamp": [round(f / 10, 9) for f in frames],
            "frame": frames,
            "track_id": [1] * len(frames),
            "x1": [x - 5] * len(frames),
            "y1": [95.0] * len(frames),
            "x2": [x + 5] * len(frames),
            "y2": [105.0] * len(frames),
            "x_center_px": [x] * len(frames),
            "y_center_px": [100.0] * len(frames),
        }
    )


def test_report_does_not_walk_or_freeze_across_a_tracking_gap(settings_obj: Settings):
    """#632: still 0-2 s, hidden 2-5 s, reappears 30 cm away and stays still."""
    df = pd.concat([_still(range(0, 21), 100.0), _still(range(50, 71), 400.0)])

    report = _run(settings_obj, df.reset_index(drop=True), fps=10.0)

    general = report["comportamento_geral"]
    assert general["distancia_total_cm"] == pytest.approx(0.0, abs=1e-9)
    spans = [
        (ep["start_time"].total_seconds(), ep["end_time"].total_seconds())
        for ep in general["episodios_congelamento"]
    ]
    assert spans == pytest.approx([(0.1, 2.0), (5.1, 7.0)])


def test_report_gap_follows_the_project_roi_cap(settings_obj: Settings):
    """A ``roi_max_gap_s`` longer than the gap makes it continuous again."""
    from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

    df = pd.concat([_still(range(0, 21), 100.0), _still(range(50, 71), 400.0)])
    service = AnalysisService(
        settings_obj=settings_obj,
        roi_rule=resolve_roi_rule({"roi_settings": {"roi_max_gap_s": 10.0}}, settings_obj),
    )

    report, *_ = service.run_full_analysis(
        trajectory_df=df.reset_index(drop=True),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[],
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
    )

    assert report["comportamento_geral"]["distancia_total_cm"] > 30.0


def _two_animals() -> pd.DataFrame:
    frames = range(45)
    timestamps = [round(f / 10, 9) for f in frames]
    return pd.concat(
        [_moving_track(frames, timestamps, 1, 100.0), _moving_track(frames, timestamps, 2, 300.0)]
    ).reset_index(drop=True)


def test_frames_analysed_counts_frames_not_animals(settings_obj: Settings):
    """#641: two animals on 45 frames analysed 45 frames, not 90."""
    report = _run(settings_obj, _two_animals(), fps=10.0)

    assert report["comportamento_geral"]["total_frames_analisados"] == 45
    assert report["validacao"]["estatisticas"]["temporal_coverage"] == pytest.approx(1.0)


def test_frames_analysed_in_a_window_counts_frames_not_animals(settings_obj: Settings):
    report = _run(settings_obj, _two_animals(), fps=10.0, window=_window(1.0, 4.0))

    # Frames 10..40 inclusive.
    assert report["comportamento_geral"]["total_frames_analisados"] == 31


# ---------------------------------------------------------------------------
# #649: one-row tracks from a tracker glitch never make a one-animal report
# multi-animal.
# ---------------------------------------------------------------------------


def _rat_with_two_glitches() -> pd.DataFrame:
    """The ``Exemp_2`` shape: one rat on 60 frames plus ids 2 and 3, one row each."""
    frames = list(range(60))
    rat = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)
    rat = rat[rat["frame"] != 30]  # the rat's row of that frame went to id 2
    glitch_rat = _moving_track([30], [3.0], 2, 100.0)
    glitch_box = _moving_track([30], [3.0], 3, 300.0)
    return pd.concat([rat, glitch_rat, glitch_box]).sort_values("frame").reset_index(drop=True)


def test_one_row_tracks_do_not_turn_the_report_multi_animal(settings_obj: Settings):
    service = AnalysisService(settings_obj=settings_obj)
    report, b_analyzer, *_ = service.run_full_analysis(
        trajectory_df=_rat_with_two_glitches(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[],
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
    )

    assert b_analyzer.is_multi_track is False
    assert report["validacao"]["estatisticas"]["unique_tracks"] == 1
    warnings = report["validacao"]["avisos"]
    assert not any("animals (track_ids)" in w for w in warnings)
    assert any("track_id 2, 3; 2 row(s)" in w for w in warnings)


def test_the_screening_can_be_disabled(settings_obj: Settings):
    settings_obj.min_track_duration_s = 0.0

    report = _run(settings_obj, _rat_with_two_glitches(), fps=10.0)

    assert report["validacao"]["estatisticas"]["unique_tracks"] == 3


def test_two_real_animals_stay_two(settings_obj: Settings):
    report = _run(settings_obj, _two_animals(), fps=10.0)

    assert report["validacao"]["estatisticas"]["unique_tracks"] == 2
    assert any("animals (track_ids)" in w for w in report["validacao"]["avisos"])


# ---------------------------------------------------------------------------
# #671: rows without a track_id never become one more animal.
# ---------------------------------------------------------------------------


def _two_animals_with_untracked_rows() -> pd.DataFrame:
    """Two animals on 45 frames plus 3 s of rows without an id (a pre-fix parquet)."""
    untracked = _moving_track(range(5, 35), [f / 10 for f in range(5, 35)], 0, 200.0)
    untracked["track_id"] = float("nan")
    return (pd.concat([_two_animals(), untracked]).sort_values("frame", kind="stable")).reset_index(
        drop=True
    )


def test_untracked_rows_do_not_add_an_animal_and_all_readers_agree(settings_obj: Settings):
    from shapely.geometry import Polygon

    from zebtrack.analysis.roi import ROI

    roi = ROI(
        name="left",
        geometry=Polygon([(0, 0), (200, 0), (200, 400), (0, 400)]),
        coordinate_space="px",
    )
    service = AnalysisService(settings_obj=settings_obj)
    report, b_analyzer, r_analyzer, warnings, stats = service.run_full_analysis(
        trajectory_df=_two_animals_with_untracked_rows(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[roi],
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
    )

    assert stats["unique_tracks"] == 2
    assert report["analise_roi"]["n_animais"] == 2
    assert sorted(b_analyzer.track_keys) == [1, 2]
    assert len(report["analise_roi"]["por_animal"]) == 2
    assert any("30 row(s)" in w for w in warnings)


class TestMaskSidecarInLocalSpace:
    """The 3b masks follow a trajectory shifted into the arena's local space (#640)."""

    @staticmethod
    def _sidecar(tmp_path: Path, payloads: list) -> Path:
        path = tmp_path / "3b_Mascaras_exp1.parquet"
        pd.DataFrame(
            {"frame": range(len(payloads)), "track_id": 1, "mask_wkb": payloads}
        ).to_parquet(path)
        return path

    def test_masks_are_shifted_by_the_arena_offset(self, tmp_path):
        from shapely import wkb
        from shapely.geometry import box

        path = self._sidecar(tmp_path, [box(226, 226, 234, 234).wkb])

        moved = mask_sidecar_in_local_space(path, 200, 150)

        assert isinstance(moved, pd.DataFrame)
        assert wkb.loads(moved["mask_wkb"].iloc[0]).bounds == (26.0, 76.0, 34.0, 84.0)
        assert list(moved["frame"]) == [0] and list(moved["track_id"]) == [1]

    def test_zero_offset_hands_the_path_through(self, tmp_path):
        from shapely.geometry import box

        path = self._sidecar(tmp_path, [box(0, 0, 1, 1).wkb])

        assert mask_sidecar_in_local_space(path, 0, 0) == path
        assert mask_sidecar_in_local_space(None, 10, 10) is None

    def test_unreadable_file_is_left_for_the_analyzer_to_report(self, tmp_path):
        path = tmp_path / "3b_Mascaras_exp1.parquet"
        path.write_bytes(b"not a parquet file")

        assert mask_sidecar_in_local_space(path, 10, 10) == path

    @pytest.mark.parametrize(
        "frame",
        [
            pd.DataFrame({"frame": [0], "track_id": [1]}),
            pd.DataFrame({"frame": [], "track_id": [], "mask_wkb": []}),
        ],
        ids=["no-mask-column", "empty"],
    )
    def test_a_sidecar_without_masks_is_left_for_the_analyzer_to_report(self, tmp_path, frame):
        path = tmp_path / "3b_Mascaras_exp1.parquet"
        frame.to_parquet(path)

        assert mask_sidecar_in_local_space(path, 10, 10) == path

    def test_corrupt_payload_is_kept_for_the_analyzer_to_count(self, tmp_path):
        from shapely import wkb
        from shapely.geometry import box

        path = self._sidecar(tmp_path, [b"garbage", box(10, 10, 20, 20).wkb])

        moved = mask_sidecar_in_local_space(path, 10, 10)

        assert isinstance(moved, pd.DataFrame)
        assert moved["mask_wkb"].iloc[0] == b"garbage"
        assert wkb.loads(moved["mask_wkb"].iloc[1]).bounds == (0.0, 0.0, 10.0, 10.0)


# ---------------------------------------------------------------------------
# #631 — zebrafish defaults must not leak into a top-down (rodent) project
# ---------------------------------------------------------------------------

_GEOTAXIS_KEYS = ("geotaxis_indice", "geotaxis_avg_dist", "geotaxis_zones")


def _geotaxis_keys(report) -> set[str]:
    return set(_GEOTAXIS_KEYS) & set(report["comportamento_geral"])


class TestGeotaxisFollowsThePerspective:
    """Geotaxis is depth: a video filmed from above has no bottom to measure."""

    def test_top_down_project_computes_no_geotaxis(self, settings_obj: Settings):
        report = _run(
            settings_obj,
            _walk(),
            fps=10.0,
            behavioral_config={"aquarium_perspective": "top_down", "geotaxis_distance_cm": 1.5},
        )

        assert _geotaxis_keys(report) == set()

    def test_top_down_beats_an_inherited_enabled_flag(self, settings_obj: Settings):
        report = _run(
            settings_obj,
            _walk(),
            fps=10.0,
            behavioral_config={
                "aquarium_perspective": "top-down",
                "geotaxis_enabled": True,
                "geotaxis_distance_cm": 1.5,
            },
        )

        assert _geotaxis_keys(report) == set()

    def test_lateral_project_still_computes_geotaxis(self, settings_obj: Settings):
        report = _run(
            settings_obj,
            _walk(),
            fps=10.0,
            behavioral_config={"aquarium_perspective": "lateral", "geotaxis_distance_cm": 1.5},
        )

        assert _geotaxis_keys(report) == set(_GEOTAXIS_KEYS)

    def test_lateral_project_that_disabled_geotaxis_gets_none(self, settings_obj: Settings):
        report = _run(
            settings_obj,
            _walk(),
            fps=10.0,
            behavioral_config={
                "aquarium_perspective": "lateral",
                "geotaxis_enabled": False,
                "geotaxis_distance_cm": 1.5,
            },
        )

        assert _geotaxis_keys(report) == set()

    def test_settings_fallback_honours_a_top_down_snapshot(self, settings_obj: Settings):
        """The pre-recorded pipeline passes no config: the snapshot's settings decide."""
        settings_obj.behavioral_analysis.aquarium_perspective = "top_down"

        report = _run(settings_obj, _walk(), fps=10.0)

        assert _geotaxis_keys(report) == set()

    def test_settings_fallback_keeps_zebrafish_geotaxis(self, settings_obj: Settings):
        """The golden's path: pristine ``lateral`` settings, no project config."""
        settings_obj.behavioral_analysis.aquarium_perspective = "lateral"

        report = _run(settings_obj, _walk(), fps=10.0)

        assert _geotaxis_keys(report) == set(_GEOTAXIS_KEYS)

    def test_project_top_down_overrides_the_global_lateral_default(self, settings_obj: Settings):
        settings_obj.behavioral_analysis.aquarium_perspective = "lateral"
        service = AnalysisService(settings_obj=settings_obj)

        params = service.collect_analysis_parameters(
            {"behavioral_config": {"aquarium_perspective": "top_down"}}
        )

        assert params["behavioral_config"]["aquarium_perspective"] == "top_down"
        assert params["behavioral_config"]["geotaxis_enabled"] is False

    def test_lateral_default_without_project_keeps_geotaxis_enabled(self, settings_obj: Settings):
        settings_obj.behavioral_analysis.aquarium_perspective = "lateral"
        service = AnalysisService(settings_obj=settings_obj)

        params = service.collect_analysis_parameters({})

        assert params["behavioral_config"]["geotaxis_enabled"] is True


def _sprint() -> pd.DataFrame:
    """A subject that moves 8 cm per frame at 10 fps: 80 cm/s, a rat's sprint."""
    frames = list(range(45))
    x_cm = [10.0 if f % 2 == 0 else 18.0 for f in frames]
    df = _moving_track(frames, [round(f / 10, 9) for f in frames], 1, 100.0)
    df["x_center_px"] = [x * 10.0 for x in x_cm]
    df["x1"] = df["x_center_px"] - 5
    df["x2"] = df["x_center_px"] + 5
    df["x_cm"] = x_cm
    df["y_cm"] = 10.0
    return df


def _speed_violations(settings_obj: Settings, **kwargs):
    service = AnalysisService(settings_obj=settings_obj)
    *_rest, stats = service.run_full_analysis(
        trajectory_df=_sprint(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=400,
        arena_polygon_px=_ARENA,
        rois=[],
        fps=10.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=1.0,
        **kwargs,
    )
    return stats.get("speed_violations")


class TestPlausibleSpeedIsConfigurable:
    """50 cm/s is a zebrafish ceiling; a rat's sprint must not read as a tracking error."""

    def test_zebrafish_default_flags_a_sprint(self, settings_obj: Settings):
        violations = _speed_violations(settings_obj)

        assert violations is not None
        assert violations["threshold_cm_s"] == 50.0

    def test_project_ceiling_silences_the_sprint(self, settings_obj: Settings):
        violations = _speed_violations(
            settings_obj, behavioral_config={"max_plausible_speed_cm_s": 150.0}
        )

        assert violations is None

    def test_settings_ceiling_silences_the_sprint(self, settings_obj: Settings):
        settings_obj.behavioral_analysis.max_plausible_speed_cm_s = 150.0

        assert _speed_violations(settings_obj) is None

    def test_explicit_argument_wins_over_the_project(self, settings_obj: Settings):
        violations = _speed_violations(
            settings_obj,
            max_plausible_speed_cm_s=60.0,
            behavioral_config={"max_plausible_speed_cm_s": 150.0},
        )

        assert violations is not None
        assert violations["threshold_cm_s"] == 60.0
