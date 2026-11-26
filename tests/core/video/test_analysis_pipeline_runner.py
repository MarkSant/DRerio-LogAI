"""Testes unitários para os métodos puros do ``AnalysisPipelineRunnerMixin``.

Foco nos métodos que não orquestram threads/IO: coleta de parâmetros, filtragem
por track, enriquecimento de metadados e contexto de calibração. A orquestração
completa (``_run_analysis_pipeline``) fica fora deste módulo por depender de IO e
do barramento de eventos. A proximidade social tem módulo próprio:
``tests/core/video/test_social_proximity_outcome.py``.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pandas as pd
import pytest
from tests.helpers.object_sidecar_files import write_heartbeat_sidecar

from zebtrack.core.detection import ZoneData
from zebtrack.core.video.analysis_pipeline_runner import AnalysisPipelineRunnerMixin
from zebtrack.ui.event_bus_v2 import UIEvents


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
    # Como em produção (``VideoProcessingService.__init__``): a cópia pristina
    # capturada no startup é a fonte dos limiares de PROJETO. Sem ela o mixin
    # cairia no objeto compartilhado, que qualquer fluxo ad-hoc reescreve.
    instance.settings_baseline = _make_settings()
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

    def test_project_analysis_parameters_win_over_settings(self, runner):
        """O projeto declara seus limiares — eles têm de valer."""
        runner.project_manager.project_data = {
            "calibration": {},
            "analysis_parameters": {
                "sharp_turn_threshold": 45.0,
                "freezing_vel_threshold": 3.25,
                "freezing_min_duration": 2.5,
                "smoothing_window_length": 9,
                "smoothing_polyorder": 4,
            },
        }
        runner.project_manager.get_metadata_for_experiment.return_value = {"group_id": "G1"}

        _m, _w, _h, turn, freeze_vel, freeze_dur, win, poly = runner._collect_params_from_project(
            {}, "exp1", "/v/exp1.mp4"
        )

        assert (turn, freeze_vel, freeze_dur, win, poly) == (45.0, 3.25, 2.5, 9, 4)

    def test_ad_hoc_run_does_not_leak_into_the_project(self, runner):
        """Regressão do vazamento entre fluxos (2026-08-30).

        ``SingleVideoConfigDialog.apply()`` e ``LiveAnalysisDialog.apply()``
        escrevem suas escolhas no objeto ``Settings`` COMPARTILHADO e nunca as
        restauram. Este caminho — o processamento em lote de PROJETO — lia os
        cinco valores direto dali, então rodar um vídeo único e depois analisar
        um projeto aplicava os limiares do vídeo único aos vídeos do projeto,
        mudando tempo de freezing, curvas acentuadas, distância e velocidade
        no relatório, em silêncio.
        """
        runner.project_manager.project_data = {"calibration": {}}
        runner.project_manager.get_metadata_for_experiment.return_value = {"group_id": "G1"}

        before = runner._collect_params_from_project({}, "exp1", "/v/exp1.mp4")[3:]

        # O que um fluxo ad-hoc deixa para trás no objeto compartilhado.
        runner.settings.video_processing.sharp_turn_threshold_deg_s = 7.0
        runner.settings.video_processing.freezing_velocity_threshold = 99.0
        runner.settings.video_processing.freezing_min_duration_s = 42.0
        runner.settings.trajectory_smoothing.window_length = 21
        runner.settings.trajectory_smoothing.polyorder = 4

        after = runner._collect_params_from_project({}, "exp1", "/v/exp1.mp4")[3:]

        assert after == before


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
        meta = runner._enrich_metadata_with_profile(metadata={"a": 1}, analysis_profile=None)
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
        cal, arena_warped, rois, roi_colors, px, py = runner._prepare_analysis_calibration_context(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            width_cm=10.0,
            height_cm=10.0,
            zone_data=zone,
        )
        assert cal is not None
        assert arena_warped is not None
        assert len(rois) == 1
        assert rois[0].name == "ROI_A"
        assert roi_colors["ROI_A"] == (255, 0, 0)
        assert px is not None and py is not None


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


@pytest.mark.unit
class TestReporterFrameRate:
    """The reporter gets the recording's fps; the setting is only a fallback."""

    def _create(self, runner, df, trajectory_path=None):
        return self._kwargs(runner, df, trajectory_path)["fps"]

    def _kwargs(self, runner, df, trajectory_path=None):
        from unittest.mock import patch

        with patch("zebtrack.core.video.analysis_pipeline_runner.ReporterContext") as context:
            runner._create_reporter_instance(
                trajectory_path=trajectory_path,
                filtered_df=df,
                metadata={},
                calibration=SimpleNamespace(target_dims_px=(100, 100)),
                arena_polygon_warped=[],
                rois=[],
                roi_colors={},
                video_path="v.mp4",
                pixelcm_x=1.0,
                pixelcm_y=1.0,
                sharp_turn_threshold=90.0,
                freezing_threshold=1.5,
                freezing_duration=1.0,
                smoothing_window=5,
                smoothing_polyorder=2,
            )
        return context.call_args.kwargs

    def test_ten_fps_pts_beats_the_30_fps_setting(self, runner):
        df = pd.DataFrame({"timestamp": [f / 10 for f in range(50)], "frame": range(50)})

        assert self._create(runner, df) == pytest.approx(10.0)

    def test_without_timestamps_the_setting_is_used(self, runner, trajectory_df):
        assert self._create(runner, trajectory_df) == pytest.approx(30.0)

    def test_the_3c_heartbeat_beside_the_trajectory_beats_the_pts(self, runner, tmp_path):
        """A ~9.9 fps variable-rate video: the heartbeat, not the 10 fps PTS, dates it."""
        trajectory = tmp_path / "3_CoordMovimento_E1.parquet"
        beats = [0.0]
        for i in range(98):
            beats.append(beats[-1] + (0.09 if i % 2 == 0 else 0.112))
        write_heartbeat_sidecar(trajectory, beats)
        df = pd.DataFrame({"timestamp": [f / 10 for f in range(50)], "frame": range(50)})

        kwargs = self._kwargs(runner, df, str(trajectory))

        assert kwargs["time_base"].source == "objects_heartbeat"
        assert kwargs["fps"] == pytest.approx(98 / beats[-1])

    def test_without_a_sidecar_the_pts_time_base_is_handed_down(self, runner, tmp_path):
        df = pd.DataFrame({"timestamp": [f / 10 for f in range(50)], "frame": range(50)})

        kwargs = self._kwargs(runner, df, str(tmp_path / "3_CoordMovimento_E1.parquet"))

        assert kwargs["time_base"].source == "trajectory_timestamps"
        assert kwargs["fps"] == pytest.approx(10.0)


@pytest.mark.unit
class TestAnalysisWindowResolution:
    """The pipeline runner resolves the window like every other entry (ADR-011)."""

    _RESOLVE = "zebtrack.core.video.analysis_pipeline_runner.resolve_analysis_window"

    def _zone(self) -> ZoneData:
        zone = ZoneData()
        zone.roi_polygons = [[(10, 10), (60, 10), (60, 60), (10, 60)]]
        zone.roi_names = ["toca"]
        return zone

    def test_raw_rois_and_the_trajectory_reach_the_resolver(self, runner, trajectory_df):
        from unittest.mock import patch

        runner.project_manager.project_data = {"analysis_window": {"version": 1}}
        runner.project_manager.find_video_entry.return_value = {"path": "v.mp4"}
        sentinel = object()

        with patch(self._RESOLVE, return_value=sentinel) as resolve:
            window = runner._resolve_analysis_window(
                trajectory_path="r/3_CoordMovimento_e.parquet",
                filtered_df=trajectory_df,
                zone_data=self._zone(),
                video_path="v.mp4",
            )

        assert window is sentinel
        args, kwargs = resolve.call_args
        assert args[1] == "r/3_CoordMovimento_e.parquet"
        assert kwargs["trajectory_df"] is trajectory_df
        assert kwargs["video_entry"] == {"path": "v.mp4"}
        (roi,) = kwargs["rois"]
        assert roi.name == "toca"
        assert roi.geometry.bounds == (10.0, 10.0, 60.0, 60.0)

    def test_without_a_project_there_is_no_window(self, runner, trajectory_df):
        runner.project_manager.project_data = None

        window = runner._resolve_analysis_window(
            trajectory_path="r/3_CoordMovimento_e.parquet",
            filtered_df=trajectory_df,
            zone_data=self._zone(),
            video_path="v.mp4",
        )

        assert window is None
        runner.project_manager.find_video_entry.assert_not_called()

    def test_reporter_context_receives_the_window(self, runner, trajectory_df):
        from unittest.mock import patch

        sentinel = object()
        with patch("zebtrack.core.video.analysis_pipeline_runner.ReporterContext") as context:
            runner._create_reporter_instance(
                filtered_df=trajectory_df,
                metadata={},
                calibration=SimpleNamespace(target_dims_px=(100, 100)),
                arena_polygon_warped=[],
                rois=[],
                roi_colors={},
                video_path="v.mp4",
                pixelcm_x=1.0,
                pixelcm_y=1.0,
                sharp_turn_threshold=90.0,
                freezing_threshold=1.5,
                freezing_duration=1.0,
                smoothing_window=5,
                smoothing_polyorder=2,
                window=sentinel,  # type: ignore[arg-type]
            )

        assert context.call_args.kwargs["window"] is sentinel


def _behavioural_settings(perspective: str = "lateral") -> SimpleNamespace:
    settings = _make_settings()
    settings.behavioral_analysis = SimpleNamespace(
        default_thigmotaxis_distance_cm=1.5,
        default_geotaxis_distance_cm=1.5,
        default_geotaxis_num_zones=3,
        default_geotaxis_bottom_zones=1,
        aquarium_perspective=perspective,
        geotaxis_mode="zones",
        max_plausible_speed_cm_s=50.0,
    )
    return settings


@pytest.mark.unit
class TestReportBehavioralConfig:
    """#695 item 3: the automatic pre-recorded report reads the project's
    behavioural config, as "Generate reports" always did. Until then the
    ``ReporterContext`` got ``{}``: the xlsx said ``lateral`` and 1.5 cm for a
    top-down rat project and never had geotaxis for a side-view fish project.
    """

    def test_project_values_reach_the_report(self, runner):
        runner.settings = _behavioural_settings()
        runner.settings_baseline = _behavioural_settings()
        runner.project_manager.project_data = {
            "behavioral_config": {
                "aquarium_perspective": "top_down",
                "thigmotaxis_distance_cm": 15.0,
            }
        }

        config = runner._resolve_report_behavioral_config(None)

        assert config["aquarium_perspective"] == "top_down"
        assert config["thigmotaxis_distance_cm"] == 15.0
        assert config["geotaxis_enabled"] is False

    def test_a_side_view_project_gets_geotaxis(self, runner):
        runner.settings = _behavioural_settings()
        runner.settings_baseline = _behavioural_settings()
        runner.project_manager.project_data = {
            "behavioral_config": {"aquarium_perspective": "lateral"}
        }

        assert runner._resolve_report_behavioral_config(None)["geotaxis_enabled"] is True

    def test_project_defaults_come_from_the_baseline_not_the_polluted_settings(self, runner):
        """An ad-hoc run rewrites the SHARED settings; the project must not inherit it."""
        runner.settings = _behavioural_settings("top_down")
        runner.settings.behavioral_analysis.default_thigmotaxis_distance_cm = 33.0
        runner.settings_baseline = _behavioural_settings("lateral")
        runner.project_manager.project_data = {}

        config = runner._resolve_report_behavioral_config(None)

        assert config["thigmotaxis_distance_cm"] == 1.5
        assert config["aquarium_perspective"] == "lateral"

    def test_single_video_uses_its_dialog_config(self, runner):
        runner.settings = _behavioural_settings()
        runner.project_manager.project_data = {
            "behavioral_config": {"thigmotaxis_distance_cm": 2.0}
        }
        single = {
            "behavioral_analysis": {
                "aquarium_perspective": "top_down",
                "thigmotaxis_distance_cm": 12.0,
            }
        }

        config = runner._resolve_report_behavioral_config(single)

        assert config["thigmotaxis_distance_cm"] == 12.0
        assert config["aquarium_perspective"] == "top_down"

    def test_single_video_without_dialog_config_reads_the_project_data(self, runner):
        runner.settings = _behavioural_settings()
        runner.project_manager.project_data = {
            "behavioral_config": {"thigmotaxis_distance_cm": 2.0}
        }

        config = runner._resolve_report_behavioral_config({"aquarium_width_cm": 10})

        assert config["thigmotaxis_distance_cm"] == 2.0

    def test_reporter_context_receives_it(self, runner, trajectory_df):
        from unittest.mock import patch

        with patch("zebtrack.core.video.analysis_pipeline_runner.ReporterContext") as context:
            runner._create_reporter_instance(
                filtered_df=trajectory_df,
                metadata={},
                calibration=SimpleNamespace(target_dims_px=(100, 100)),
                arena_polygon_warped=[],
                rois=[],
                roi_colors={},
                video_path="v.mp4",
                pixelcm_x=1.0,
                pixelcm_y=1.0,
                sharp_turn_threshold=90.0,
                freezing_threshold=1.5,
                freezing_duration=1.0,
                smoothing_window=5,
                smoothing_polyorder=2,
                behavioral_config={"aquarium_perspective": "top_down"},
            )

        assert context.call_args.kwargs["behavioral_config"] == {"aquarium_perspective": "top_down"}

    def test_the_pipeline_hands_it_to_the_reporter(self, runner, trajectory_df):
        import threading
        from unittest.mock import patch

        runner.settings = _behavioural_settings()
        runner.settings_baseline = _behavioural_settings()
        runner.project_manager.project_data = {
            "calibration": {"aquarium_width_cm": 30.0, "aquarium_height_cm": 20.0},
            "behavioral_config": {
                "aquarium_perspective": "top_down",
                "thigmotaxis_distance_cm": 15.0,
            },
        }
        runner.project_manager.get_metadata_for_experiment.return_value = {"group_id": "G"}
        runner.cancel_event = threading.Event()
        runner.load_trajectory_dataframe = Mock(return_value=trajectory_df)
        runner.ensure_arena_polygon = Mock(return_value=[(0, 0), (10, 0), (10, 10)])
        seen: dict = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            runner.cancel_event.set()  # stop right after the context is built
            return Mock()

        with (
            patch.object(
                runner,
                "_prepare_analysis_calibration_context",
                return_value=(Mock(), [(0, 0)], [], {}, 1.0, 1.0),
            ),
            patch.object(runner, "_resolve_analysis_window", return_value=None),
            patch.object(runner, "_create_reporter_instance", side_effect=fake_create),
        ):
            ok = runner._run_analysis_pipeline(
                experiment_id="exp1",
                video_path="/v/exp1.mp4",
                results_dir="/r",
                arena_polygon_px=[(0, 0), (10, 0), (10, 10)],
                metadata_context={},
                single_video_config=None,
                progress_callback=None,
                analysis_profile=None,
            )

        assert ok is False
        assert seen["behavioral_config"]["aquarium_perspective"] == "top_down"
        assert seen["behavioral_config"]["thigmotaxis_distance_cm"] == 15.0


# ---------------------------------------------------------------------------
# _run_analysis_pipeline orchestration and report generation (TASK-087)
# ---------------------------------------------------------------------------


class _Cancel:
    """``threading.Event`` look-alike whose ``is_set`` answers from a script."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = 0

    def is_set(self):
        self.asked += 1
        return self.answers.pop(0) if self.answers else self.answers_default

    answers_default = True


class _Reporter:
    """Records the export a reporter was asked for, in a shared log."""

    def __init__(self, log, name):
        self.log = log
        self.name = name

    def __call__(self, ctx):
        self.ctx = ctx
        return self

    def export_summary(self, path):
        self.log.append((self.name, path))

    def export_individual_report_step_by_step(self, path, progress):
        self.log.append((self.name, path, progress))


@pytest.fixture
def reporters(monkeypatch):
    from zebtrack.core.video import analysis_pipeline_runner as module

    log: list[tuple] = []
    monkeypatch.setattr(module, "ParquetSummaryReporter", _Reporter(log, "parquet"))
    monkeypatch.setattr(module, "ExcelReporter", _Reporter(log, "excel"))
    monkeypatch.setattr(module, "WordReporter", _Reporter(log, "word"))
    return log


class TestGenerateReportsForVideo:
    def test_all_three_reports_are_written_next_to_the_trajectory(
        self, runner, reporters, tmp_path
    ):
        progress = object()

        paths = runner._generate_reports_for_video(
            ctx=object(),
            experiment_id="E1",
            results_dir=str(tmp_path),
            progress_callback=progress,
            cancel_event=None,
        )

        parquet = str(tmp_path / "E1_summary.parquet")
        excel = str(tmp_path / "E1_summary.xlsx")
        word = str(tmp_path / "E1_report.docx")
        assert paths == (parquet, excel, word)
        assert reporters == [("parquet", parquet), ("excel", excel), ("word", word, progress)]

    @pytest.mark.parametrize(
        ("answers", "written"),
        [
            # cancelled before anything is written
            ([True], []),
            # cancelled between the two entry checks
            ([False, True], []),
            # cancelled after the parquet summary
            ([False, False, True], ["parquet"]),
            # cancelled after the excel summary
            ([False, False, False, True], ["parquet", "excel"]),
        ],
    )
    def test_a_cancel_stops_the_remaining_reports(
        self, runner, reporters, tmp_path, answers, written
    ):
        result = runner._generate_reports_for_video(
            ctx=object(),
            experiment_id="E1",
            results_dir=str(tmp_path),
            progress_callback=None,
            cancel_event=_Cancel(*answers),
        )

        assert result is None
        assert [entry[0] for entry in reporters] == written


def _pipeline_rig(runner, monkeypatch, tmp_path, **over):
    """Stub every heavy step of ``_run_analysis_pipeline`` and record the calls."""
    runner.cancel_event = threading.Event()
    calls: list[tuple] = []
    state: dict[str, Any] = {
        "trajectory": pd.DataFrame({"frame": [0, 1], "track_id": [1, 2]}),
        "params": ({"experiment_id": "E1"}, 30.0, 20.0, 90.0, 1.5, 1.0, 5, 2),
        "arena": [[0, 0], [10, 0], [10, 10]],
        "calibration": (object(), [(0.0, 0.0)], [], {}, 20.0, 20.0),
        "reports": ("p.parquet", "e.xlsx", "r.docx"),
    }
    state.update(over)

    def load(path, experiment_id):
        calls.append(("load", path, experiment_id))
        return state["trajectory"]

    def collect(**kw):
        calls.append(("collect", kw))
        return state["params"]

    def ensure(arena, video_path, video_context=None):
        calls.append(("ensure_arena", arena, video_path, video_context))
        return state["arena"]

    def prepare(**kw):
        calls.append(("prepare", kw))
        return state["calibration"]

    def window(**kw):
        calls.append(("window", kw))
        return "WINDOW"

    def create(**kw):
        calls.append(("reporter", kw))
        return SimpleNamespace(validation_warnings=[])

    def social(**kw):
        calls.append(("social", kw))
        return SimpleNamespace(result={"pairs": 3})

    def warn(ctx, outcome):
        calls.append(("warn", outcome))

    def reports(**kw):
        calls.append(("reports", kw))
        return state["reports"]

    def register(**kw):
        calls.append(("register", kw))

    for name, fn in {
        "load_trajectory_dataframe": load,
        "_collect_analysis_parameters": collect,
        "ensure_arena_polygon": ensure,
        "_prepare_analysis_calibration_context": prepare,
        "_resolve_analysis_window": window,
        "_create_reporter_instance": create,
        "_resolve_report_behavioral_config": lambda _cfg: {"cfg": 1},
        "_analyze_social_proximity": social,
        "_record_social_outcome_warning": warn,
        "_generate_reports_for_video": reports,
        "_register_project_outputs": register,
    }.items():
        monkeypatch.setattr(runner, name, fn)
    runner.project_manager.get_zone_data.return_value = ZoneData(polygon=[[0, 0]])
    return calls, state


def _run(runner, tmp_path, **kw):
    kw.setdefault("analysis_profile", None)
    return runner._run_analysis_pipeline(
        experiment_id="E1",
        video_path="/v/E1.mp4",
        results_dir=str(tmp_path),
        arena_polygon_px=[[1, 1]],
        metadata_context=None,
        single_video_config=None,
        progress_callback="PROGRESS",
        **kw,
    )


def _events(runner):
    return [call.args[0] for call in runner.ui_event_bus.publish.call_args_list]


class TestRunAnalysisPipeline:
    def test_a_complete_run_registers_the_outputs_and_publishes_the_social_summary(
        self, runner, monkeypatch, tmp_path
    ):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path)

        assert _run(runner, tmp_path, analysis_profile={"name": "Focal", "track_ids": [2]}) is True

        names = [c[0] for c in calls]
        assert names == [
            "load",
            "collect",
            "ensure_arena",
            "prepare",
            "window",
            "reporter",
            "social",
            "warn",
            "reports",
            "register",
        ]
        trajectory_path = str(tmp_path / "3_CoordMovimento_E1.parquet")
        assert calls[0] == ("load", trajectory_path, "E1")
        register = calls[-1][1]
        assert register == {
            "video_path": "/v/E1.mp4",
            "results_dir": str(tmp_path),
            "trajectory_path": trajectory_path,
            "summary_parquet": "p.parquet",
            "summary_excel": "e.xlsx",
            "report_path": "r.docx",
        }
        reports = next(c for c in calls if c[0] == "reports")[1]
        assert reports["progress_callback"] == "PROGRESS"
        assert reports["cancel_event"] is runner.cancel_event
        # The profile narrows the trajectory the reporter sees, and its name and
        # tracks are stamped into the metadata the reporter gets.
        reporter = next(c for c in calls if c[0] == "reporter")[1]
        assert reporter["filtered_df"]["track_id"].tolist() == [2]
        assert reporter["metadata"]["analysis_profile"] == "Focal"
        assert reporter["window"] == "WINDOW"
        # The reporter dates the recording from the files beside the trajectory.
        assert reporter["trajectory_path"] == trajectory_path
        (summary,) = [e for e in _events(runner) if e.type == UIEvents.UI_UPDATE_SOCIAL_SUMMARY]
        assert summary.data.profile == "Focal"
        assert summary.data.stats == {"pairs": 3}
        assert summary.data.tracks == ["2"]

    def test_without_a_profile_the_summary_is_published_as_default(
        self, runner, monkeypatch, tmp_path
    ):
        _pipeline_rig(runner, monkeypatch, tmp_path)

        assert _run(runner, tmp_path) is True

        (summary,) = [e for e in _events(runner) if e.type == UIEvents.UI_UPDATE_SOCIAL_SUMMARY]
        assert summary.data.profile == "default"
        assert summary.data.tracks == ["1", "2"]

    def test_a_missing_trajectory_ends_the_run_quietly(self, runner, monkeypatch, tmp_path):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path, trajectory=None)

        assert _run(runner, tmp_path) is False

        assert [c[0] for c in calls] == ["load"]

    def test_a_cancel_before_the_pipeline_skips_every_step(self, runner, monkeypatch, tmp_path):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path)
        runner.cancel_event.set()

        assert _run(runner, tmp_path) is False

        assert [c[0] for c in calls] == ["load"]

    @pytest.mark.parametrize(
        "params",
        [
            ({"experiment_id": "E1"}, None, 20.0, 90.0, 1.5, 1.0, 5, 2),
            ({"experiment_id": "E1"}, 30.0, 0, 90.0, 1.5, 1.0, 5, 2),
        ],
    )
    def test_missing_aquarium_dimensions_show_the_calibration_error(
        self, runner, monkeypatch, tmp_path, params
    ):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path, params=params)

        assert _run(runner, tmp_path) is False

        (error,) = [e for e in _events(runner) if e.type == UIEvents.SHOW_ERROR]
        assert error.data.message == "Incomplete calibration data."
        assert "prepare" not in [c[0] for c in calls]

    def test_a_missing_arena_shows_the_same_error(self, runner, monkeypatch, tmp_path):
        _pipeline_rig(runner, monkeypatch, tmp_path, arena=None)

        assert _run(runner, tmp_path) is False

        (error,) = [e for e in _events(runner) if e.type == UIEvents.SHOW_ERROR]
        assert error.data.message == "Incomplete calibration data."

    @pytest.mark.parametrize(
        "calibration",
        [
            (None, [(0.0, 0.0)], [], {}, 20.0, 20.0),
            (object(), None, [], {}, 20.0, 20.0),
            (object(), [(0.0, 0.0)], [], {}, None, 20.0),
            (object(), [(0.0, 0.0)], [], {}, 20.0, None),
        ],
    )
    def test_an_unusable_calibration_stops_before_the_reports(
        self, runner, monkeypatch, tmp_path, calibration
    ):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path, calibration=calibration)

        assert _run(runner, tmp_path) is False

        (error,) = [e for e in _events(runner) if e.type == UIEvents.SHOW_ERROR]
        assert error.data.message == "Failed to prepare the calibration data."
        assert "reporter" not in [c[0] for c in calls]

    def test_a_cancel_after_the_context_is_built_skips_social_and_reports(
        self, runner, monkeypatch, tmp_path
    ):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path)
        original = runner._create_reporter_instance

        def create_then_cancel(**kw):
            runner.cancel_event.set()
            return original(**kw)

        monkeypatch.setattr(runner, "_create_reporter_instance", create_then_cancel)

        assert _run(runner, tmp_path) is False

        names = [c[0] for c in calls]
        assert "social" not in names and "reports" not in names

    def test_cancelled_reports_mean_no_registration_and_no_summary(
        self, runner, monkeypatch, tmp_path
    ):
        calls, _ = _pipeline_rig(runner, monkeypatch, tmp_path, reports=None)

        assert _run(runner, tmp_path) is False

        assert "register" not in [c[0] for c in calls]
        assert [e for e in _events(runner) if e.type == UIEvents.UI_UPDATE_SOCIAL_SUMMARY] == []


class TestRegisterOutputsWithoutBus:
    def test_the_refresh_event_is_skipped_when_there_is_no_bus(self, runner):
        runner.ui_event_bus = None

        runner._register_project_outputs(
            video_path="v",
            results_dir="r",
            trajectory_path="t",
            summary_parquet="p",
            summary_excel="e",
            report_path="d",
        )

        runner.project_manager.register_processing_outputs.assert_called_once_with(
            "v",
            results_dir="r",
            trajectory_path="t",
            summary_parquet="p",
            summary_excel="e",
            report_path="d",
        )
