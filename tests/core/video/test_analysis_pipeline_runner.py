"""Testes unitários para os métodos puros do ``AnalysisPipelineRunnerMixin``.

Foco nos métodos que não orquestram threads/IO: coleta de parâmetros, filtragem
por track, enriquecimento de metadados, contexto de calibração e proximidade
social (caminhos degenerados). A orquestração completa (``_run_analysis_pipeline``)
fica fora deste módulo por depender de IO e do barramento de eventos.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.video.analysis_pipeline_runner import AnalysisPipelineRunnerMixin


def _make_settings():
    """Settings mínimo com os campos lidos pelo mixin."""
    return SimpleNamespace(
        video_processing=SimpleNamespace(
            sharp_turn_threshold_deg_s=90.0,
            freezing_velocity_threshold=1.5,
            freezing_min_duration_s=1.0,
            fps=30.0,
        ),
        trajectory_smoothing=SimpleNamespace(window_length=5, polyorder=2),
    )


@pytest.fixture
def runner():
    """Instância do mixin com atributos injetados (sem threads/IO)."""
    instance = AnalysisPipelineRunnerMixin()
    instance.settings = _make_settings()
    instance.project_manager = Mock()
    instance.ui_event_bus = Mock()
    return instance


@pytest.fixture
def trajectory_df():
    return pd.DataFrame(
        {
            "frame": [0, 1, 2, 3],
            "track_id": [1, 1, 2, 2],
            "x1": [10, 11, 12, 13],
            "y1": [20, 21, 22, 23],
            "x2": [30, 31, 32, 33],
            "y2": [40, 41, 42, 43],
        }
    )


@pytest.mark.unit
class TestCollectParamsFromSingleVideo:
    def test_defaults_from_settings_and_group_id(self, runner):
        metadata, w, h, sharp, freeze_v, freeze_d, win, poly = (
            runner._collect_params_from_single_video({}, "exp42")
        )
        assert metadata["experiment_id"] == "exp42"
        assert metadata["video_name"] == "exp42"
        assert metadata["group_id"] == "single_video"
        assert sharp == 90.0
        assert freeze_v == 1.5
        assert win == 5
        assert poly == 2

    def test_config_overrides_win(self, runner):
        config = {
            "aquarium_width_cm": 20.0,
            "sharp_turn_threshold_deg_s": 45.0,
            "smoothing_window_length": 9,
            "group_id": "G7",
        }
        metadata, w, h, sharp, *_rest, win, _poly = runner._collect_params_from_single_video(
            config, "exp1"
        )
        assert w == 20.0
        assert sharp == 45.0
        assert win == 9
        assert metadata["group_id"] == "G7"


@pytest.mark.unit
class TestCollectParamsFromProject:
    def test_csv_metadata_merged(self, runner):
        runner.project_manager.project_data = {
            "calibration": {"aquarium_width_cm": 15.0, "aquarium_height_cm": 8.0}
        }
        runner.project_manager.get_metadata_for_experiment.return_value = {"group_id": "G1"}

        metadata, w, h, *_ = runner._collect_params_from_project({}, "exp1", "/v/exp1.mp4")

        assert metadata["group_id"] == "G1"
        assert w == 15.0
        assert h == 8.0
        runner.project_manager.derive_processing_metadata.assert_not_called()

    def test_empty_metadata_triggers_derive_fallback(self, runner):
        runner.project_manager.project_data = {"calibration": {}}
        runner.project_manager.get_metadata_for_experiment.return_value = {}
        runner.project_manager.derive_processing_metadata.return_value = {"group_id": "derived"}

        metadata, *_ = runner._collect_params_from_project(None, "exp1", "/v/exp1.mp4")

        assert metadata == {"group_id": "derived"}
        runner.project_manager.derive_processing_metadata.assert_called_once()


@pytest.mark.unit
class TestFilterTrajectoryByTracks:
    def test_no_profile_returns_all_and_resolved_ids(self, runner, trajectory_df):
        filtered, resolved = runner._filter_trajectory_by_tracks(
            trajectory_df=trajectory_df, analysis_profile=None, experiment_id="e"
        )
        assert len(filtered) == 4
        assert resolved == ["1", "2"]

    def test_requested_tracks_narrows_df(self, runner, trajectory_df):
        filtered, resolved = runner._filter_trajectory_by_tracks(
            trajectory_df=trajectory_df,
            analysis_profile={"track_ids": [1]},
            experiment_id="e",
        )
        assert set(filtered["track_id"].unique()) == {1}
        assert resolved == ["1"]

    def test_requested_track_miss_keeps_full_df(self, runner, trajectory_df):
        """Track inexistente: mantém o df completo e loga aviso (sem narrowing)."""
        filtered, resolved = runner._filter_trajectory_by_tracks(
            trajectory_df=trajectory_df,
            analysis_profile={"track_ids": [999]},
            experiment_id="e",
        )
        assert len(filtered) == 4

    def test_missing_track_id_column(self, runner):
        df = pd.DataFrame({"frame": [0, 1], "x1": [1, 2]})
        filtered, resolved = runner._filter_trajectory_by_tracks(
            trajectory_df=df, analysis_profile={"track_ids": [1]}, experiment_id="e"
        )
        assert resolved == []
        assert len(filtered) == 2


@pytest.mark.unit
class TestEnrichMetadataWithProfile:
    def test_adds_profile_name_and_tracks(self, runner):
        meta = runner._enrich_metadata_with_profile(
            metadata={"experiment_id": "e"},
            analysis_profile={"name": "perfilA", "track_ids": [1, 2]},
        )
        assert meta["analysis_profile"] == "perfilA"
        assert meta["analysis_profile_tracks"] == [1, 2]

    def test_none_profile_is_noop(self, runner):
        meta = runner._enrich_metadata_with_profile(
            metadata={"a": 1}, analysis_profile=None
        )
        assert meta == {"a": 1}


@pytest.mark.unit
class TestPrepareCalibrationContext:
    def test_missing_dims_returns_empty_context(self, runner):
        result = runner._prepare_analysis_calibration_context(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            width_cm=None,
            height_cm=None,
            zone_data=ZoneData(),
        )
        assert result == (None, None, [], {}, None, None)

    def test_valid_context_builds_calibration_and_rois(self, runner):
        zone = ZoneData(
            roi_polygons=[[(10, 10), (40, 10), (40, 40), (10, 40)]],
            roi_names=["ROI_A"],
            roi_colors=[(255, 0, 0)],
        )
        cal, arena_warped, rois, roi_colors, px, py = (
            runner._prepare_analysis_calibration_context(
                arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
                width_cm=10.0,
                height_cm=10.0,
                zone_data=zone,
            )
        )
        assert cal is not None
        assert arena_warped is not None
        assert len(rois) == 1
        assert rois[0].name == "ROI_A"
        assert roi_colors["ROI_A"] == (255, 0, 0)
        assert px is not None and py is not None


@pytest.mark.unit
class TestAnalyzeSocialProximity:
    def test_disabled_returns_none(self, runner, trajectory_df):
        assert (
            runner._analyze_social_proximity(
                filtered_df=trajectory_df,
                analysis_profile={"social": {"enabled": False}},
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                experiment_id="e",
            )
            is None
        )

    def test_single_track_returns_none(self, runner):
        df = pd.DataFrame({"track_id": [1, 1, 1]})
        assert (
            runner._analyze_social_proximity(
                filtered_df=df,
                analysis_profile={"social": {"enabled": True}},
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                experiment_id="e",
            )
            is None
        )

    def test_missing_pixelcm_returns_none(self, runner, trajectory_df):
        assert (
            runner._analyze_social_proximity(
                filtered_df=trajectory_df,
                analysis_profile={"social": {"enabled": True}},
                pixelcm_x=None,
                pixelcm_y=None,
                experiment_id="e",
            )
            is None
        )

    def test_enabled_with_two_tracks_invokes_analyzer(self, runner, trajectory_df, monkeypatch):
        from zebtrack.analysis.roi import ROIAnalyzer

        sentinel = {"mean_distance_cm": 3.2}
        # Patch direto no atributo da classe (mais robusto que alvo em string).
        monkeypatch.setattr(
            ROIAnalyzer, "analyze_social_proximity", staticmethod(lambda *a, **k: sentinel)
        )
        result = runner._analyze_social_proximity(
            filtered_df=trajectory_df,
            analysis_profile={"social": {"enabled": True, "radius_cm": 4.0}},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            experiment_id="e",
        )
        assert result is sentinel


@pytest.mark.unit
class TestRegisterProjectOutputs:
    def test_registers_and_publishes_refresh(self, runner):
        runner._register_project_outputs(
            video_path="/v/e.mp4",
            results_dir="/v/e_results",
            trajectory_path="/v/e_results/traj.parquet",
            summary_parquet="/v/e_results/s.parquet",
            summary_excel="/v/e_results/s.xlsx",
            report_path="/v/e_results/r.docx",
        )
        runner.project_manager.register_processing_outputs.assert_called_once()
        runner.ui_event_bus.publish.assert_called_once()
