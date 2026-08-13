"""Entrega das métricas de ROI ao resumo: escalar não observado + tabela por animal.

Os números aqui já eram calculados e testados (``tests/analysis/test_roi_metrics.py``,
``test_multi_track_roi.py``); o que este arquivo cobre é o TRANSPORTE deles até o
``combined_data`` do ``.xlsx``. Inclui a regressão que congela nome, ordem e valor
das colunas antigas do resumo — quem já tem script lendo esse arquivo não pode
quebrar.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.data_transformer import PER_ANIMAL_COLUMNS, DataTransformer
from zebtrack.analysis.roi import ROI, ROIAnalyzer

ROI_NAMES = ["ROI1", "ROI2"]


def _synthetic_roi_report() -> dict:
    """Relatório mínimo com o formato exato de ``report['analise_roi']``."""
    return {
        "analise_roi": {
            "tempo_gasto_por_roi": {
                "ROI1": {"seconds": 12.0, "percentage": 40.0},
                "ROI2": {"seconds": 6.0, "percentage": 20.0},
            },
            "contagem_entradas": {"ROI1": 3, "ROI2": 1},
            "contagem_saidas": {"ROI1": 2, "ROI2": 1},
            "latencia_primeira_entrada": {"ROI1": 1.5, "ROI2": 9.0},
            "distancia_por_roi": {"ROI1": 30.0, "ROI2": 11.0},
            "estatisticas_velocidade_por_roi": {"ROI1": {"mean": 2.5}},
            "congelamento_por_roi": {"ROI1": {"count": 2, "total_duration": 4.0}},
            "tempo_nao_observado_s": 3.25,
            "semantica": "any_track",
            "n_animais": 2,
            "por_animal": {
                "1": {
                    "tempo_gasto_por_roi": {
                        "ROI1": {"seconds": 8.0, "percentage": 26.0},
                        "ROI2": {"seconds": 2.0, "percentage": 7.0},
                    },
                    "latencia_primeira_entrada": {"ROI1": 1.5, "ROI2": 9.0},
                    "contagem_entradas": {"ROI1": 2, "ROI2": 1},
                    "contagem_saidas": {"ROI1": 1, "ROI2": 1},
                    "distancia_por_roi": {"ROI1": 20.0, "ROI2": 4.0},
                    "tempo_nao_observado_s": 1.25,
                },
                "2": {
                    "tempo_gasto_por_roi": {
                        "ROI1": {"seconds": 5.0, "percentage": 16.0},
                        "ROI2": {"seconds": 4.0, "percentage": 13.0},
                    },
                    "latencia_primeira_entrada": {"ROI1": 0.5, "ROI2": None},
                    "contagem_entradas": {"ROI1": 1, "ROI2": 0},
                    "contagem_saidas": {"ROI1": 1, "ROI2": 0},
                    "distancia_por_roi": {"ROI1": 10.0, "ROI2": 7.0},
                    "tempo_nao_observado_s": 2.0,
                },
            },
        }
    }


def _collect(report: dict) -> dict:
    """Roda ``_collect_roi_metrics`` isolado (só ``.rois`` é lido do analisador)."""
    transformer = DataTransformer()
    r_analyzer = cast(ROIAnalyzer, SimpleNamespace(rois=ROI_NAMES))
    return transformer._collect_roi_metrics({}, report, r_analyzer, {})


# ----------------------------------------------------------------------
# A.1 — tempo_nao_observado_s no resumo
# ----------------------------------------------------------------------


@pytest.mark.unit
def test_unobserved_time_reaches_combined_data():
    """O escalar do relatório aparece no ``combined_data`` com o mesmo valor."""
    report = _synthetic_roi_report()

    combined = _collect(report)

    assert combined["tempo_nao_observado_s"] == 3.25
    assert combined["tempo_nao_observado_s"] == report["analise_roi"]["tempo_nao_observado_s"]


@pytest.mark.unit
def test_unobserved_time_is_none_when_report_omits_it():
    """Relatório antigo (sem a chave) não quebra: a coluna existe com ``None``."""
    report = _synthetic_roi_report()
    del report["analise_roi"]["tempo_nao_observado_s"]

    assert _collect(report)["tempo_nao_observado_s"] is None


@pytest.mark.unit
def test_unobserved_time_is_translated_and_displayed():
    """A coluna nova tem tradução PT->EN e nome de exibição, como as vizinhas."""
    transformer = DataTransformer()

    assert transformer.translate_column_name("tempo_nao_observado_s") == "unobserved_time_s"

    display = transformer.prepare_for_display(pd.DataFrame([{"unobserved_time_s": 3.25}]))
    assert list(display.columns) == ["Unobserved Time (s)"]


@pytest.mark.unit
def test_unobserved_time_is_not_padded_per_roi():
    """É escalar por experimento: ``standardize_roi_columns`` não o sufixa por ROI."""
    transformer = DataTransformer()
    df = pd.DataFrame([{"unobserved_time_s": 3.25}])

    standardized = transformer.standardize_roi_columns(df, ["ROI1", "ROI2"])

    assert not [c for c in standardized.columns if c.startswith("unobserved_time_s_")]
    assert "tempo_nao_observado_s_ROI1" not in standardized.columns


# ----------------------------------------------------------------------
# Regressão: as colunas antigas do resumo
# ----------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_summary_columns_unchanged_in_name_order_and_value():
    """Nome, ORDEM e valor das colunas antigas ficam idênticos; a nova vem no fim.

    Congelado de propósito: scripts de terceiros leem o ``.xlsx`` por nome e por
    posição de coluna.
    """
    combined = _collect(_synthetic_roi_report())

    expected = {
        "tempo_no_ROI1_s": 12.0,
        "percentual_tempo_no_ROI1": 40.0,
        "entradas_no_ROI1": 3,
        "saidas_do_ROI1": 2,
        "latencia_para_ROI1_s": 1.5,
        "distancia_no_ROI1_cm": 30.0,
        "velocidade_media_no_ROI1_cm_s": 2.5,
        "episodios_congelamento_no_ROI1": 2,
        "duracao_total_congelamento_no_ROI1_s": 4.0,
        "tempo_no_ROI2_s": 6.0,
        "percentual_tempo_no_ROI2": 20.0,
        "entradas_no_ROI2": 1,
        "saidas_do_ROI2": 1,
        "latencia_para_ROI2_s": 9.0,
        "distancia_no_ROI2_cm": 11.0,
        "total_entradas_roi": 4,
    }

    assert list(combined) == [*expected, "tempo_nao_observado_s"]
    assert {key: combined[key] for key in expected} == expected


# ----------------------------------------------------------------------
# A.2 — tabela longa por animal
# ----------------------------------------------------------------------


@pytest.mark.unit
def test_per_animal_table_has_one_row_per_track_and_roi():
    """N tracks x M ROIs = N*M linhas, com os valores do dicionário de origem."""
    report = _synthetic_roi_report()
    per_animal = report["analise_roi"]["por_animal"]

    df = DataTransformer().build_per_animal_dataframe(report, "exp_001", "G1")

    assert list(df.columns) == list(PER_ANIMAL_COLUMNS)
    assert len(df) == len(per_animal) * len(ROI_NAMES) == 4
    assert set(df["track_id"]) == {"1", "2"}
    assert set(df["roi"]) == set(ROI_NAMES)
    assert set(df["experiment_id"]) == {"exp_001"}
    assert set(df["group_id"]) == {"G1"}

    for track_id, metrics in per_animal.items():
        for roi_name in ROI_NAMES:
            row = df[(df["track_id"] == track_id) & (df["roi"] == roi_name)].iloc[0]
            assert row["tempo_s"] == metrics["tempo_gasto_por_roi"][roi_name]["seconds"]
            assert (
                row["percentual_tempo"] == (metrics["tempo_gasto_por_roi"][roi_name]["percentage"])
            )
            assert row["entradas"] == metrics["contagem_entradas"][roi_name]
            assert row["saidas"] == metrics["contagem_saidas"][roi_name]
            assert row["distancia_cm"] == metrics["distancia_por_roi"][roi_name]
            assert row["tempo_nao_observado_s"] == metrics["tempo_nao_observado_s"]

    missing_latency = df[(df["track_id"] == "2") & (df["roi"] == "ROI2")].iloc[0]
    assert pd.isna(missing_latency["latencia_primeira_entrada_s"])


@pytest.mark.unit
def test_per_animal_table_is_empty_but_typed_without_roi_analysis():
    """Sem análise de ROI a tabela é vazia, porém COM as colunas (nada de aba torta)."""
    df = DataTransformer().build_per_animal_dataframe({}, "exp_001", "G1")

    assert df.empty
    assert list(df.columns) == list(PER_ANIMAL_COLUMNS)


# ----------------------------------------------------------------------
# Invariante de um único sujeito (roi.py: get_metrics_by_track)
# ----------------------------------------------------------------------


@pytest.fixture
def single_track_analysis():
    """Análise real com UM sujeito atravessando duas ROIs."""
    settings = Mock()
    settings.trajectory_smoothing = Mock(window_length=5, polyorder=2)
    settings.angular_velocity = Mock(
        min_displacement_threshold_cm=0.5,
        angle_calculation_window=3,
        angular_velocity_smoothing_window=5,
    )
    settings.roi_inclusion_rule = "centroid_in"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5

    n = 30
    trajectory = pd.DataFrame(
        {
            "timestamp": [i * 0.1 for i in range(n)],
            "frame": list(range(n)),
            "track_id": [1] * n,
            "x1": [10 + i for i in range(n)],
            "y1": [20 + i for i in range(n)],
            "x2": [30 + i for i in range(n)],
            "y2": [40 + i for i in range(n)],
            "confidence": [0.95] * n,
        }
    )
    rois = [
        ROI(
            name="ROI1",
            geometry=Polygon([(0, 0), (40, 0), (40, 40), (0, 40)]),
            coordinate_space="px",
        ),
        ROI(
            name="ROI2",
            geometry=Polygon([(40, 40), (80, 40), (80, 80), (40, 80)]),
            coordinate_space="px",
        ),
    ]

    report, _b, _r, _warnings, _stats = AnalysisService(settings_obj=settings).run_full_analysis(
        trajectory_df=trajectory,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        rois=rois,
        fps=30.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=2.0,
    )
    return report


@pytest.mark.unit
def test_single_track_rows_match_the_group_metrics(single_track_analysis):
    """Um sujeito: uma linha por ROI, e os valores coincidem com as métricas de grupo.

    É o invariante prometido no docstring de ``ROIAnalyzer.get_metrics_by_track``:
    com um único animal, ``any_track`` e "por animal" são o mesmo número.
    """
    report = single_track_analysis
    roi_analysis = report["analise_roi"]
    assert len(roi_analysis["por_animal"]) == 1

    df = DataTransformer().build_per_animal_dataframe(report, "exp_single", "G1")

    roi_names = list(roi_analysis["tempo_gasto_por_roi"])
    assert len(df) == len(roi_names)

    for roi_name in roi_names:
        row = df[df["roi"] == roi_name].iloc[0]
        group_time = roi_analysis["tempo_gasto_por_roi"][roi_name]
        assert row["tempo_s"] == pytest.approx(group_time["seconds"])
        assert row["percentual_tempo"] == pytest.approx(group_time["percentage"])
        assert row["entradas"] == roi_analysis["contagem_entradas"][roi_name]
        assert row["saidas"] == roi_analysis["contagem_saidas"][roi_name]
        assert row["distancia_cm"] == pytest.approx(roi_analysis["distancia_por_roi"][roi_name])
        assert row["tempo_nao_observado_s"] == pytest.approx(roi_analysis["tempo_nao_observado_s"])


# ----------------------------------------------------------------------
# A.4 — o aviso multi-animal aponta para onde o dado está
# ----------------------------------------------------------------------


@pytest.mark.unit
def test_multi_animal_warning_points_to_the_summary_sheet():
    """O aviso cita a ABA do resumo, não a chave interna do dicionário."""
    from zebtrack.analysis.reporters.excel_reporter import PER_ANIMAL_SHEET_NAME

    settings = Mock()
    settings.trajectory_smoothing = Mock(window_length=5, polyorder=2)
    settings.angular_velocity = Mock(
        min_displacement_threshold_cm=0.5,
        angle_calculation_window=3,
        angular_velocity_smoothing_window=5,
    )
    settings.roi_inclusion_rule = "centroid_in"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5

    n = 20
    trajectory = pd.DataFrame(
        {
            "timestamp": [i * 0.1 for i in range(n) for _ in (0, 1)],
            "frame": [i for i in range(n) for _ in (0, 1)],
            "track_id": [1, 2] * n,
            "x1": [10 + i for i in range(n) for _ in (0, 1)],
            "y1": [20 + i for i in range(n) for _ in (0, 1)],
            "x2": [30 + i for i in range(n) for _ in (0, 1)],
            "y2": [40 + i for i in range(n) for _ in (0, 1)],
            "confidence": [0.95] * (2 * n),
        }
    )

    _report, _b, _r, warnings, _stats = AnalysisService(settings_obj=settings).run_full_analysis(
        trajectory_df=trajectory,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        rois=[],
        fps=30.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=2.0,
    )

    multi_animal = [w for w in warnings if "animals (track_ids)" in w]
    assert multi_animal, "aviso multi-animal não emitido"
    assert PER_ANIMAL_SHEET_NAME in multi_animal[0]
    assert "_summary.xlsx" in multi_animal[0]
    assert "analise_roi.por_animal" not in multi_animal[0]
