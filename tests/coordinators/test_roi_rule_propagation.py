"""Regressão: os QUATRO caminhos de decisão de ROI honram o projeto.

Antes, cada caminho resolvia a regra por conta própria e três deles ignoravam
``project_data["roi_settings"]``:

1. relatório pré-gravado  — honrava o projeto;
2. regeneração de relatório — ignorava (snapshot duplicado, sem ROI);
3. pós-processamento ao vivo — ignorava (``Settings`` global cru);
4. gatilho Arduino ao vivo — regra fixa por centroide.

O cenário é sempre o mesmo: global ``bbox_intersects``, projeto ``centroid_in``
— o resultado tem de ser ``centroid_in`` nos quatro.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.settings import load_settings

PROJECT_DATA = {
    "roi_settings": {
        "roi_inclusion_rule": "centroid_in",
        "roi_buffer_radius_value": 3.0,
        "roi_min_bbox_overlap_ratio": 0.42,
    }
}


@pytest.fixture
def global_settings():
    """``Settings`` real com a regra GLOBAL divergente da do projeto."""
    settings = load_settings()
    settings.roi_min_bbox_overlap_ratio = 0.10
    settings.roi_inclusion_rule = "bbox_intersects"
    return settings


def _assert_project_rule(obj) -> None:
    assert obj.roi_inclusion_rule == "centroid_in"
    assert obj.roi_buffer_radius_value == 3.0
    assert obj.roi_min_bbox_overlap_ratio == 0.42


# ----------------------------------------------------------------------
# 1. Relatório de vídeo pré-gravado
# ----------------------------------------------------------------------


def test_prerecorded_report_snapshot_honors_project(global_settings):
    from zebtrack.coordinators._video_selection_mixin import VideoSelectionMixin

    mixin: Any = VideoSelectionMixin()
    mixin.settings = global_settings
    mixin.project_manager = SimpleNamespace(project_data=dict(PROJECT_DATA))

    _assert_project_rule(mixin._create_project_settings_snapshot())
    # O Settings global não pode ser contaminado pelo snapshot.
    assert global_settings.roi_inclusion_rule == "bbox_intersects"


# ----------------------------------------------------------------------
# 2. Regeneração de relatório
# ----------------------------------------------------------------------


def test_report_regeneration_snapshot_honors_project(global_settings):
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator

    coordinator = ReportGenerationCoordinator(
        state_manager=MagicMock(),
        project_manager=cast(Any, SimpleNamespace(project_data=dict(PROJECT_DATA))),
        settings_obj=global_settings,
    )

    _assert_project_rule(coordinator._create_project_settings_snapshot())
    assert global_settings.roi_inclusion_rule == "bbox_intersects"


def test_processing_and_regeneration_snapshots_agree(global_settings):
    """O par processar → regenerar precisa produzir a MESMA regra."""
    from zebtrack.coordinators._video_selection_mixin import VideoSelectionMixin
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator

    project_manager = SimpleNamespace(project_data=dict(PROJECT_DATA))

    mixin: Any = VideoSelectionMixin()
    mixin.settings = global_settings
    mixin.project_manager = project_manager
    processing = mixin._create_project_settings_snapshot()

    regeneration = ReportGenerationCoordinator(
        state_manager=MagicMock(),
        project_manager=cast(Any, project_manager),
        settings_obj=global_settings,
    )._create_project_settings_snapshot()

    assert processing.roi_inclusion_rule == regeneration.roi_inclusion_rule
    assert processing.roi_buffer_radius_value == regeneration.roi_buffer_radius_value
    assert processing.roi_min_bbox_overlap_ratio == regeneration.roi_min_bbox_overlap_ratio


# ----------------------------------------------------------------------
# 3. Pós-processamento da sessão ao vivo
# ----------------------------------------------------------------------


def test_live_post_processing_service_honors_project(global_settings):
    from zebtrack.core.recording.live_analysis_post_processor import (
        LiveAnalysisPostProcessorMixin,
    )

    mixin: Any = LiveAnalysisPostProcessorMixin()
    mixin.settings = global_settings
    mixin.project_manager = SimpleNamespace(project_data=dict(PROJECT_DATA))

    service = mixin._build_post_analysis_service()
    config = service.resolve_roi_rule()

    assert config.rule == "centroid_in"
    assert config.buffer_radius_value == 3.0
    assert config.min_bbox_overlap_ratio == 0.42


def test_analysis_service_without_injected_rule_uses_its_settings(global_settings):
    """Compatibilidade: quem injeta um snapshot já resolvido segue funcionando."""
    from zebtrack.analysis.analysis_service import AnalysisService

    assert AnalysisService(settings_obj=global_settings).resolve_roi_rule().rule == (
        "bbox_intersects"
    )


# ----------------------------------------------------------------------
# 4. Gatilho Arduino ao vivo
# ----------------------------------------------------------------------


class _ArduinoPipelineStub:
    """Superfície mínima consumida por ``_build_arduino_evaluator``."""

    def __init__(self, settings, project_data):
        self.settings = settings
        self.project_manager = SimpleNamespace(project_data=project_data)
        self.detector_service = SimpleNamespace(
            detector=SimpleNamespace(
                roi_names=["A"],
                scaled_roi_polygons=[
                    np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
                ],
            )
        )

    _build_arduino_evaluator: Any = None  # substituído abaixo
    _arduino_buffer_px_per_cm: Any = None


def _make_arduino_stub(settings, project_data) -> Any:
    from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin

    stub = _ArduinoPipelineStub(settings, project_data)
    stub._build_arduino_evaluator = FrameProcessingMixin._build_arduino_evaluator.__get__(stub)
    stub._arduino_buffer_px_per_cm = FrameProcessingMixin._arduino_buffer_px_per_cm
    return stub


def test_arduino_evaluator_honors_project(global_settings):
    evaluator = _make_arduino_stub(global_settings, dict(PROJECT_DATA))._build_arduino_evaluator()
    assert evaluator.rule == "centroid_in"


def test_arduino_evaluator_falls_back_to_global_rule(global_settings):
    """Sem ``roi_settings`` no projeto, vale a regra global — não uma fixa."""
    evaluator = _make_arduino_stub(global_settings, {})._build_arduino_evaluator()
    assert evaluator.rule == "bbox_intersects"


@pytest.mark.parametrize(
    "project_data",
    [
        {"calibration": ["não", "é", "dict"]},
        {"calibration": "10.0"},
        {"calibration": {"pixelcm_x": "abc", "pixelcm_y": 10}},
        {"calibration": {"pixelcm_x": float("inf"), "pixelcm_y": 10}},
        "project_data corrompido",
    ],
    ids=["calib_lista", "calib_string", "px_texto", "px_inf", "project_data_nao_dict"],
)
def test_arduino_evaluator_survives_corrupted_project_data(global_settings, project_data):
    """O loop ao vivo não pode morrer por causa de metadado corrompido."""
    evaluator = _make_arduino_stub(global_settings, project_data)._build_arduino_evaluator()
    assert evaluator is not None
    assert evaluator.rule == "bbox_intersects"  # caiu na regra global


def test_arduino_evaluator_uses_calibration_scale(global_settings):
    """Com calibração válida, o raio de buffer vira pixels como no ROIAnalyzer."""
    calibrated = {"calibration": {"pixelcm_x": 9.0, "pixelcm_y": 4.0}}
    stub = _make_arduino_stub(global_settings, calibrated)
    # sqrt(9 * 4) = 6 — a mesma conversão de ROIAnalyzer._buffer_radius_px.
    assert stub._arduino_buffer_px_per_cm(calibrated) == 6.0


def test_arduino_and_report_agree_on_the_same_rule(global_settings):
    """O gatilho e o relatório da MESMA sessão resolvem a mesma regra."""
    from zebtrack.core.recording.live_analysis_post_processor import (
        LiveAnalysisPostProcessorMixin,
    )

    project_data = dict(PROJECT_DATA)

    mixin: Any = LiveAnalysisPostProcessorMixin()
    mixin.settings = global_settings
    mixin.project_manager = SimpleNamespace(project_data=project_data)
    report_rule = mixin._build_post_analysis_service().resolve_roi_rule()

    evaluator = _make_arduino_stub(global_settings, project_data)._build_arduino_evaluator()

    assert evaluator.rule == report_rule.rule


# ----------------------------------------------------------------------
# 5. Os dois snapshots concordam em TUDO, não só na regra de ROI
# ----------------------------------------------------------------------


ANALYSIS_PROJECT_DATA = {
    "analysis_parameters": {
        "freezing_vel_threshold": 3.25,
        "freezing_min_duration": 2.5,
        "sharp_turn_threshold": 45.0,
        "smoothing_window_length": 9,
        "smoothing_polyorder": 2,
    },
    "behavioral_config": {
        "aquarium_perspective": "top_down",
        "thigmotaxis_distance_cm": 2.75,
    },
    "analysis_interval_frames": 4,
    "display_interval_frames": 6,
}


def _both_snapshots(settings, project_data):
    """(processing, regeneration) snapshots for the same project."""
    from zebtrack.coordinators._video_selection_mixin import VideoSelectionMixin
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator

    project_manager = SimpleNamespace(project_data=dict(project_data))

    mixin: Any = VideoSelectionMixin()
    mixin.settings = settings
    mixin.project_manager = project_manager

    regeneration = ReportGenerationCoordinator(
        state_manager=MagicMock(),
        project_manager=cast(Any, project_manager),
        settings_obj=settings,
    )
    return (
        mixin._create_project_settings_snapshot(),
        regeneration._create_project_settings_snapshot(),
    )


def test_processing_and_regeneration_agree_on_analysis_parameters(global_settings):
    """Regenerar um relatório tem de dar o MESMO número que processar.

    As duas implementações do snapshot divergiam: a de processamento aplicava
    ``analysis_parameters`` e ``behavioral_config``, a de regeneração aplicava
    os intervalos — e nenhuma das duas aplicava os limiares de freezing e de
    curva acentuada. Este é o teste que mata essa divergência.
    """
    processing, regeneration = _both_snapshots(global_settings, ANALYSIS_PROJECT_DATA)

    for section, field in (
        ("video_processing", "freezing_velocity_threshold"),
        ("video_processing", "freezing_min_duration_s"),
        ("video_processing", "sharp_turn_threshold_deg_s"),
        ("video_processing", "processing_interval"),
        ("video_processing", "display_interval"),
        ("trajectory_smoothing", "window_length"),
        ("trajectory_smoothing", "polyorder"),
        ("behavioral_analysis", "aquarium_perspective"),
        ("behavioral_analysis", "default_thigmotaxis_distance_cm"),
    ):
        assert getattr(getattr(processing, section), field) == getattr(
            getattr(regeneration, section), field
        ), f"{section}.{field} diverge entre processar e regenerar"


def test_both_snapshots_actually_apply_the_project_values(global_settings):
    """Concordar em valores GLOBAIS não provaria nada."""
    processing, regeneration = _both_snapshots(global_settings, ANALYSIS_PROJECT_DATA)

    for snapshot in (processing, regeneration):
        assert snapshot.video_processing.freezing_velocity_threshold == 3.25
        assert snapshot.video_processing.sharp_turn_threshold_deg_s == 45.0
        assert snapshot.trajectory_smoothing.window_length == 9
        assert snapshot.behavioral_analysis.default_thigmotaxis_distance_cm == 2.75
