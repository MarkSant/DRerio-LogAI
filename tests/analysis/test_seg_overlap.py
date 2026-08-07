"""Geometria da regra ``seg_overlap``: ``área(máscara ∩ ROI) / área(máscara)``.

As razões aqui são calculadas À MÃO a partir de figuras simples (quadrado,
meia-lua) e não derivadas do próprio código — um teste que recalcula a fração
com a mesma expressão da implementação passaria com o denominador trocado.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer

# ROI: quadrado 0..10 em x, 0..10 em y (área 100).
ROI_SQUARE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


def _behavior_analyzer(masks_bboxes: list[tuple[float, float, float, float]]) -> MagicMock:
    """Analisador comportamental de mentira com uma linha por bbox."""
    n = len(masks_bboxes)
    index = pd.to_datetime([f"2026-01-01 00:00:{i:02d}" for i in range(n)])
    trajectory = pd.DataFrame(
        {
            "frame": list(range(n)),
            "track_id": [1] * n,
            "x1": [b[0] for b in masks_bboxes],
            "y1": [b[1] for b in masks_bboxes],
            "x2": [b[2] for b in masks_bboxes],
            "y2": [b[3] for b in masks_bboxes],
            "x_center_px": [(b[0] + b[2]) / 2 for b in masks_bboxes],
            "y_center_px": [(b[1] + b[3]) / 2 for b in masks_bboxes],
        },
        index=index,
    )

    analyzer = MagicMock()
    analyzer.trajectory_data = trajectory
    analyzer._pixelcm_x = 1.0
    analyzer._pixelcm_y = 1.0
    analyzer._video_height_px = 100
    # ``_resolve_track_axis`` VALIDA a adesão em vez de presumir: um MagicMock
    # é truthy em todo atributo, e sem estes valores explícitos a análise
    # entraria no caminho multi-animal com um agrupador de tamanho errado.
    analyzer.is_multi_track = False
    analyzer.track_labels = None
    analyzer.track_keys = None
    return analyzer


def _masks_frame(geometries: list[Any]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "frame": list(range(len(geometries))),
            "track_id": [1] * len(geometries),
            "mask_wkb": [g.wkb if g is not None else None for g in geometries],
        }
    )


def _analyze(
    geometries: list[Any],
    ratio: float,
    bboxes: list[tuple[float, float, float, float]] | None = None,
) -> pd.Series:
    """Roda o analisador com debounce/filtros DESLIGADOS.

    Sem isso o resultado testado seria o da camada temporal (debounce +
    duração mínima da visita), não o da geometria — que é o que este arquivo
    existe para cobrir.
    """
    boxes = bboxes or [g.bounds for g in geometries]
    analyzer = ROIAnalyzer(
        behavior_analyzer=_behavior_analyzer(boxes),
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        inclusion_rule="seg_overlap",
        min_seg_overlap_ratio=ratio,
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        mask_source=_masks_frame(geometries),
    )
    assert analyzer.degradation_warnings == [], "não deveria ter degradado"
    return analyzer._trajectory["in_R_stable"]


def test_fully_contained_mask_is_inside() -> None:
    """Máscara inteira dentro da ROI: razão 1.0."""
    mask = Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])  # área 4, toda dentro
    assert _analyze([mask], ratio=0.99).tolist() == [True]


def test_fully_outside_mask_is_outside() -> None:
    """Sem interseção: razão 0.0, e nem o limiar mínimo aceita."""
    mask = Polygon([(20, 20), (24, 20), (24, 24), (20, 24)])
    assert _analyze([mask], ratio=0.01).tolist() == [False]


def test_half_in_half_out_is_exactly_one_half() -> None:
    """Quadrado 4x4 com metade fora da borda direita da ROI: razão 0.5.

    Área total 16; a parte dentro (x de 8 a 10) é 2x4 = 8. 8/16 = 0.5.
    """
    mask = Polygon([(8, 3), (12, 3), (12, 7), (8, 7)])
    assert _analyze([mask], ratio=0.5).tolist() == [True]
    assert _analyze([mask], ratio=0.51).tolist() == [False]


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [(0.29, True), (0.31, False)],
    ids=["abaixo_do_limiar_entra", "acima_do_limiar_sai"],
)
def test_threshold_boundary(threshold: float, expected: bool) -> None:
    """Fronteira do limiar com razão conhecida de 0.30.

    Quadrado 10x10 (área 100) deslocado de modo que só a faixa ``x`` de 0 a 3
    caia dentro da ROI: 3x10 = 30 de interseção, razão exata 0.30. O teste
    prova que a comparação é ``>=`` contra o limiar PRÓPRIO da segmentação.
    """
    mask = Polygon([(-7, 0), (3, 0), (3, 10), (-7, 10)])
    assert _analyze([mask], ratio=threshold).tolist() == [expected]


def test_exact_threshold_is_inclusive() -> None:
    """Razão exatamente igual ao limiar CONTA como dentro (``>=``)."""
    mask = Polygon([(-7, 0), (3, 0), (3, 10), (-7, 10)])
    assert _analyze([mask], ratio=0.3).tolist() == [True]


def test_crescent_shaped_mask_uses_real_area_not_bbox() -> None:
    """Meia-lua: a bbox mentiria, a máscara não.

    A lua é um disco grande com um pedaço mordido; a bbox dela invade a ROI
    muito mais do que a geometria real. Se a implementação usasse a bbox (ou o
    limiar de bbox) o resultado mudaria — é exatamente a distinção que
    justifica a regra existir.
    """
    outer = Point(12.0, 5.0).buffer(4.0, quad_segs=64)
    crescent = outer.difference(Point(13.5, 5.0).buffer(3.5, quad_segs=64))

    inside = crescent.intersection(ROI_SQUARE).area
    ratio = inside / crescent.area
    # A figura precisa ser genuinamente parcial para o teste ter valor.
    assert 0.0 < ratio < 1.0

    bbox = crescent.bounds
    assert _analyze([crescent], ratio=ratio - 0.01, bboxes=[bbox]).tolist() == [True]
    assert _analyze([crescent], ratio=ratio + 0.01, bboxes=[bbox]).tolist() == [False]


def test_row_without_mask_is_outside_not_bbox_fallback() -> None:
    """Linha sem máscara fica FORA, não herda o resultado da bbox.

    Misturar as duas regras linha a linha produziria uma série que não
    corresponde a critério nenhum — o relatório diria ``seg_overlap`` e os
    números seriam de outra coisa.
    """
    inside_mask = Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])
    # Segunda linha: bbox bem dentro da ROI, mas SEM máscara no sidecar.
    masks = _masks_frame([inside_mask, None])

    analyzer = ROIAnalyzer(
        behavior_analyzer=_behavior_analyzer([(2, 2, 4, 4), (5, 5, 7, 7)]),
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        inclusion_rule="seg_overlap",
        min_seg_overlap_ratio=0.5,
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        mask_source=masks,
    )

    assert analyzer.degradation_warnings == []
    assert analyzer._trajectory["in_R_stable"].tolist() == [True, False]


def test_degenerate_mask_does_not_crash() -> None:
    """Geometria degenerada no sidecar é ignorada, sem exceção.

    O recorder já descarta contornos com menos de 3 pontos, mas um sidecar
    pode vir de outra origem — e a análise nunca pode morrer por causa dele.
    """
    good = Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])
    masks = pd.DataFrame(
        {
            "frame": [0, 1],
            "track_id": [1, 1],
            # WKB inválido: bytes que não descrevem geometria nenhuma.
            "mask_wkb": [good.wkb, b"\x00\x01lixo"],
        }
    )

    analyzer = ROIAnalyzer(
        behavior_analyzer=_behavior_analyzer([(2, 2, 4, 4), (2, 2, 4, 4)]),
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        inclusion_rule="seg_overlap",
        min_seg_overlap_ratio=0.5,
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        mask_source=masks,
    )

    assert analyzer._trajectory["in_R_stable"].tolist() == [True, False]


def test_masks_are_matched_per_animal_not_per_frame() -> None:
    """Com dois animais no MESMO frame, cada um recebe a sua máscara.

    A junção é por ``(frame, track_id)``: só o ``frame`` colocaria a máscara de
    um peixe na linha do outro — o mesmo erro de "fantasma" que a análise
    multi-animal corrigiu.
    """
    inside = Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])
    outside = Polygon([(20, 20), (22, 20), (22, 22), (20, 22)])

    index = pd.to_datetime(["2026-01-01 00:00:00"] * 2)
    trajectory = pd.DataFrame(
        {
            "frame": [0, 0],
            "track_id": [1, 2],
            "x1": [2.0, 20.0],
            "y1": [2.0, 20.0],
            "x2": [4.0, 22.0],
            "y2": [4.0, 22.0],
            "x_center_px": [3.0, 21.0],
            "y_center_px": [3.0, 21.0],
        },
        index=index,
    )
    analyzer_mock = MagicMock()
    analyzer_mock.trajectory_data = trajectory
    analyzer_mock._pixelcm_x = 1.0
    analyzer_mock._pixelcm_y = 1.0
    analyzer_mock._video_height_px = 100
    analyzer_mock.is_multi_track = True
    analyzer_mock.track_labels = np.array([0, 1], dtype=np.int64)
    analyzer_mock.track_keys = [1, 2]

    masks = pd.DataFrame(
        {
            "frame": [0, 0],
            "track_id": [1, 2],
            "mask_wkb": [inside.wkb, outside.wkb],
        }
    )

    analyzer = ROIAnalyzer(
        behavior_analyzer=analyzer_mock,
        rois=[ROI(name="R", geometry=ROI_SQUARE, coordinate_space="px")],
        inclusion_rule="seg_overlap",
        min_seg_overlap_ratio=0.5,
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        mask_source=masks,
    )

    assert analyzer.degradation_warnings == []
    assert analyzer._trajectory["in_R_stable"].tolist() == [True, False]
