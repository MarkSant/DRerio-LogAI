from pathlib import Path

import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService
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


def test_window_cut_is_not_silently_ignored(settings_obj: Settings):
    frames = range(30)
    df = _moving_track(frames, [f / 10 for f in frames], 1, 100.0)

    with pytest.raises(NotImplementedError):
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
