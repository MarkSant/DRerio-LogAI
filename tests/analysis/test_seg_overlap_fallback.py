"""Degradação DECLARADA de ``seg_overlap`` para ``bbox_intersects``.

Antes deste PR a regra levantava ``ValueError`` incondicionalmente: escolhê-la
na UI (onde ela sempre esteve disponível) matava a análise inteira. O contrato
novo é degradar com aviso — o relatório sai, e diz que saiu com outra regra.

O que estes testes fixam:

1. Sem sidecar o resultado é IGUAL ao de ``bbox_intersects``, não aproximado.
2. Cada motivo de degradação produz um aviso legível.
3. Nada levanta, em nenhum dos caminhos.
4. O aviso chega a ``validation_warnings``, que é o que o relatório imprime.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer

ROI_SQUARE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

# Uma dentro, uma parcial, uma fora — para que a série comparada tenha
# variação real e não seja "tudo False" dos dois lados.
BBOXES = [(2.0, 2.0, 4.0, 4.0), (8.0, 3.0, 12.0, 7.0), (30.0, 30.0, 34.0, 34.0)]


def _behavior_analyzer() -> MagicMock:
    index = pd.to_datetime([f"2026-01-01 00:00:{i:02d}" for i in range(len(BBOXES))])
    trajectory = pd.DataFrame(
        {
            "frame": list(range(len(BBOXES))),
            "track_id": [1] * len(BBOXES),
            "x1": [b[0] for b in BBOXES],
            "y1": [b[1] for b in BBOXES],
            "x2": [b[2] for b in BBOXES],
            "y2": [b[3] for b in BBOXES],
            "x_center_px": [(b[0] + b[2]) / 2 for b in BBOXES],
            "y_center_px": [(b[1] + b[3]) / 2 for b in BBOXES],
        },
        index=index,
    )
    analyzer = MagicMock()
    analyzer.trajectory_data = trajectory
    analyzer._pixelcm_x = 1.0
    analyzer._pixelcm_y = 1.0
    analyzer._video_height_px = 100
    analyzer.is_multi_track = False
    analyzer.track_labels = None
    analyzer.track_keys = None
    return analyzer


def _build(rule: str, **kwargs) -> ROIAnalyzer:
    return ROIAnalyzer(
        behavior_analyzer=_behavior_analyzer(),
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        inclusion_rule=rule,
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        **kwargs,
    )


def test_missing_sidecar_matches_bbox_intersects_exactly() -> None:
    """O fallback não é "parecido" com ``bbox_intersects``: é o mesmo.

    Se divergisse, o relatório traria números que não correspondem a regra
    nenhuma — nem à escolhida, nem à de fallback.
    """
    degraded = _build("seg_overlap", mask_source=None)
    reference = _build("bbox_intersects")

    pd.testing.assert_series_equal(
        degraded._trajectory["in_R_stable"],
        reference._trajectory["in_R_stable"],
    )
    assert len(degraded.degradation_warnings) == 1
    assert degraded.degradation_warnings[0].startswith(
        "Regra de ROI 'seg_overlap' degradada para 'bbox_intersects'"
    )


def test_fallback_honours_the_bbox_threshold_and_basis() -> None:
    """Degradado, a regra usa os parâmetros de BBOX — que passam a valer.

    É o argumento para manter a validação cruzada de
    ``roi_min_bbox_overlap_ratio`` quando ``seg_overlap`` está selecionada: no
    caminho degradado ela é o limiar que efetivamente decide.
    """
    strict = _build("seg_overlap", mask_source=None, min_bbox_overlap_ratio=0.99)
    loose = _build("seg_overlap", mask_source=None, min_bbox_overlap_ratio=0.01)

    assert strict._trajectory["in_R_stable"].tolist() != loose._trajectory["in_R_stable"].tolist()


def test_nonexistent_path_degrades_without_raising(tmp_path: Path) -> None:
    """Caminho que não existe (dados antigos) degrada, não explode."""
    analyzer = _build("seg_overlap", mask_source=tmp_path / "3b_Mascaras_inexistente.parquet")

    assert len(analyzer.degradation_warnings) == 1
    assert "não existe" in analyzer.degradation_warnings[0]


def test_empty_sidecar_degrades(tmp_path: Path) -> None:
    """Sidecar existente mas vazio conta como ausente."""
    path = tmp_path / "3b_Mascaras_x.parquet"
    pd.DataFrame({"frame": [], "track_id": [], "mask_wkb": []}).to_parquet(path)

    analyzer = _build("seg_overlap", mask_source=path)
    assert len(analyzer.degradation_warnings) == 1
    assert "não tem linhas" in analyzer.degradation_warnings[0]


def test_sidecar_with_wrong_columns_degrades() -> None:
    """Colunas erradas: o motivo NOMEIA o que falta."""
    analyzer = _build("seg_overlap", mask_source=pd.DataFrame({"frame": [0], "geom": [b""]}))

    assert len(analyzer.degradation_warnings) == 1
    assert "mask_wkb" in analyzer.degradation_warnings[0]
    assert "track_id" in analyzer.degradation_warnings[0]


def test_sidecar_that_matches_nothing_degrades() -> None:
    """Sidecar de OUTRO vídeo: frames que não existem na trajetória.

    Sem esta checagem a análise rodaria com todas as máscaras ausentes, ou
    seja, com todos os animais "fora" de todas as ROIs — um relatório
    silenciosamente zerado.
    """
    mask = Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])
    foreign = pd.DataFrame(
        {"frame": [9000, 9001], "track_id": [1, 1], "mask_wkb": [mask.wkb, mask.wkb]}
    )

    analyzer = _build("seg_overlap", mask_source=foreign)
    assert len(analyzer.degradation_warnings) == 1
    assert "Nenhuma máscara" in analyzer.degradation_warnings[0]


def test_unreadable_file_degrades(tmp_path: Path) -> None:
    """Arquivo corrompido degrada com o motivo, sem propagar a exceção."""
    path = tmp_path / "3b_Mascaras_corrompido.parquet"
    path.write_bytes(b"isto nao e um parquet")

    analyzer = _build("seg_overlap", mask_source=path)
    assert len(analyzer.degradation_warnings) == 1
    assert "não pôde ser lido" in analyzer.degradation_warnings[0]


def test_warning_reaches_validation_warnings_of_the_report() -> None:
    """O aviso precisa chegar ao relatório, não só ao objeto do analisador.

    ``validation_warnings`` e ``report["validacao"]["avisos"]`` são o MESMO
    objeto, e o ``AnalysisService`` faz o ``extend`` ANTES de os relatórios
    serem gerados — um append posterior não apareceria no documento.
    """
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig

    trajectory = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2, 0.3, 0.4],
            "frame": [0, 1, 2, 3, 4],
            "track_id": [1] * 5,
            "x1": [2.0] * 5,
            "y1": [2.0] * 5,
            "x2": [4.0] * 5,
            "y2": [4.0] * 5,
            "x_center_px": [3.0] * 5,
            "y_center_px": [3.0] * 5,
        }
    )

    settings = MagicMock()
    settings.trajectory_smoothing.window_length = 1
    settings.trajectory_smoothing.polyorder = 0
    settings.angular_velocity.min_displacement_threshold_cm = 0.1
    settings.angular_velocity.angle_calculation_window = 1
    settings.angular_velocity.angular_velocity_smoothing_window = 1
    settings.behavioral_analysis.default_thigmotaxis_distance_cm = None
    settings.behavioral_analysis.default_geotaxis_distance_cm = None
    settings.behavioral_analysis.aquarium_perspective = "lateral"

    service = AnalysisService(
        settings_obj=settings,
        roi_rule=RoiRuleConfig(
            rule="seg_overlap",
            flutter_enter_frames=1,
            flutter_exit_frames=1,
            min_visit_s=0.0,
        ),
    )

    report, _b, r_analyzer, warnings, _stats = service.run_full_analysis(
        trajectory_df=trajectory,
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=100,
        arena_polygon_px=[(0, 0), (10, 0), (10, 10), (0, 10)],
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        fps=10.0,
        freezing_vel_threshold=1.5,
        freezing_min_duration=1.0,
        mask_sidecar_path=None,
    )

    assert r_analyzer is not None
    degradation = [w for w in warnings if "seg_overlap" in w]
    assert len(degradation) == 1
    # Mesmo objeto: o que está na lista está no relatório.
    assert degradation[0] in report["validacao"]["avisos"]


@pytest.mark.parametrize(
    "source",
    [None, "caminho/que/nao/existe.parquet", pd.DataFrame()],
    ids=["none", "caminho_inexistente", "dataframe_vazio"],
)
def test_no_path_raises(source) -> None:
    """Nenhuma entrada, por pior que seja, levanta exceção."""
    analyzer = _build("seg_overlap", mask_source=source)
    assert analyzer.degradation_warnings  # degradou...
    assert analyzer._trajectory["in_R_stable"].notna().all()  # ...e produziu série
