"""Tests for ArduinoRoiEvaluator (per-frame ROI occupancy geometry)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.services.arduino_roi_evaluator import ArduinoRoiEvaluator
from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig

# Two disjoint 10x10 squares.
SQUARE_A = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)
SQUARE_B = np.array([[100, 100], [110, 100], [110, 110], [100, 110]], dtype=np.int32)


def test_centroid_inside_single_roi():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(5, 5)]) == {"A"}


def test_centroid_outside_all_rois():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(50, 50)]) == set()


def test_multiple_animals_occupy_multiple_rois():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    assert ev.occupied_rois([(5, 5), (105, 105)]) == {"A", "B"}


def test_any_track_scope_one_roi_two_animals():
    ev = ArduinoRoiEvaluator(["A", "B"], [SQUARE_A, SQUARE_B])
    # Two animals both in A -> still just {"A"} (set semantics)
    assert ev.occupied_rois([(3, 3), (7, 7)]) == {"A"}


def test_empty_and_degenerate_polygons_ignored():
    ev = ArduinoRoiEvaluator(
        ["A", "Empty", "Line"],
        [SQUARE_A, np.array([], dtype=np.int32), np.array([[0, 0], [1, 1]], dtype=np.int32)],
    )
    assert ev.roi_names == ["A"]
    assert ev.has_rois() is True


def test_no_rois():
    ev = ArduinoRoiEvaluator([], [])
    assert ev.has_rois() is False
    assert ev.occupied_rois([(5, 5)]) == set()


def test_centroid_of_bbox():
    assert ArduinoRoiEvaluator.centroid_of_bbox(0, 0, 10, 20) == (5.0, 10.0)


def test_accepts_list_polygons():
    ev = ArduinoRoiEvaluator(["A"], [[[0, 0], [10, 0], [10, 10], [0, 10]]])
    assert ev.occupied_rois([(5, 5)]) == {"A"}


# ======================================================================
# Regra de inclusão configurável
# ======================================================================

# ROI de 100x100 px na origem, e bboxes de 20x20 em posições conhecidas.
BIG_SQUARE = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)


def _cfg(rule: str, **kwargs) -> RoiRuleConfig:
    return RoiRuleConfig(rule=rule, **kwargs)


def test_bbox_intersects_uses_overlap_ratio():
    """Bbox metade dentro: passa com ratio 0.4, reprova com 0.6."""
    half_in = (90.0, 40.0, 110.0, 60.0)  # 50% da área dentro da ROI

    permissive = ArduinoRoiEvaluator(
        ["A"], [BIG_SQUARE], _cfg("bbox_intersects", min_bbox_overlap_ratio=0.4)
    )
    strict = ArduinoRoiEvaluator(
        ["A"], [BIG_SQUARE], _cfg("bbox_intersects", min_bbox_overlap_ratio=0.6)
    )

    assert permissive.occupied_rois([half_in]) == {"A"}
    assert strict.occupied_rois([half_in]) == set()


def test_centroid_in_ignores_bbox_overlap():
    """Centroide fora, bbox sobrepondo: ``centroid_in`` não dispara."""
    half_in = (90.0, 40.0, 110.0, 60.0)  # centroide em x=100 (na borda)
    ev = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], _cfg("centroid_in"))
    assert ev.occupied_rois([half_in]) == set()


def test_buffered_rule_dilates_polygon_once():
    outside = (104.0, 44.0, 116.0, 56.0)  # centroide em (110, 50)
    plain = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], _cfg("centroid_in"))
    buffered = ArduinoRoiEvaluator(
        ["A"], [BIG_SQUARE], _cfg("centroid_in_on_buffered_roi", buffer_radius_value=20.0)
    )
    assert plain.occupied_rois([outside]) == set()
    assert buffered.occupied_rois([outside]) == {"A"}


def test_buffer_radius_scaled_by_px_per_cm():
    """O raio em cm vira pixels pelo mesmo fator usado pelo ROIAnalyzer."""
    outside = (104.0, 44.0, 116.0, 56.0)  # centroide 10 px fora
    cfg = _cfg("centroid_in_on_buffered_roi", buffer_radius_value=2.0)  # 2 cm
    too_small = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], cfg, px_per_cm=1.0)
    calibrated = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], cfg, px_per_cm=10.0)
    assert too_small.occupied_rois([outside]) == set()
    assert calibrated.occupied_rois([outside]) == {"A"}


def test_seg_overlap_falls_back_to_centroid_without_crashing():
    ev = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], _cfg("seg_overlap"))
    assert ev.rule == "centroid_in"
    assert ev.occupied_rois([(40.0, 40.0, 60.0, 60.0)]) == {"A"}
    assert ev.occupied_rois([(200.0, 200.0, 220.0, 220.0)]) == set()


def test_bbox_rule_with_centroid_only_input_falls_back():
    """Chamador antigo (só centroides) não pode zerar a ocupação."""
    ev = ArduinoRoiEvaluator(
        ["A"], [BIG_SQUARE], _cfg("bbox_intersects", min_bbox_overlap_ratio=0.5)
    )
    assert ev.occupied_rois([(50, 50)]) == {"A"}


def test_timing_stats_are_collected():
    ev = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], _cfg("bbox_intersects"))
    for _ in range(10):
        ev.occupied_rois([(10.0, 10.0, 30.0, 30.0), (200.0, 200.0, 210.0, 210.0)])
    stats = ev.stats()
    assert stats["calls"] == 10
    # Orçamento generoso: 4 ROIs / 2 animais deve ficar bem abaixo de 1 ms.
    assert stats["avg_ms"] < 5.0


# ======================================================================
# Paridade com o ROIAnalyzer — mesma geometria, mesma regra
# ======================================================================

# (x1, y1, x2, y2) cobrindo dentro, fora, tangente e vértice exato.
PARITY_BOXES = [
    (40.0, 40.0, 60.0, 60.0),  # totalmente dentro
    (200.0, 200.0, 220.0, 220.0),  # totalmente fora
    (90.0, 40.0, 110.0, 60.0),  # metade dentro
    (100.0, 40.0, 120.0, 60.0),  # tangente à borda direita
    (-10.0, -10.0, 10.0, 10.0),  # centroide exatamente no vértice (0, 0)
    (95.0, 95.0, 105.0, 105.0),  # canto, centroide no vértice (100, 100)
]


def _roi_analyzer_presence(boxes, config: RoiRuleConfig) -> list[bool]:
    """Roda o ROIAnalyzer sobre as mesmas caixas e devolve a presença por frame."""
    timestamps = pd.date_range(start="2023-01-01", periods=len(boxes), freq="100ms")
    df = pd.DataFrame(
        {
            "x_center_px": [(b[0] + b[2]) / 2 for b in boxes],
            "y_center_px": [(b[1] + b[3]) / 2 for b in boxes],
            "x1": [b[0] for b in boxes],
            "y1": [b[1] for b in boxes],
            "x2": [b[2] for b in boxes],
            "y2": [b[3] for b in boxes],
        },
        index=timestamps,
    )

    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = df
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 300

    roi = ROI(
        name="A",
        geometry=Polygon([(0, 0), (100, 0), (100, 100), (0, 100)]),
        coordinate_space="px",  # já em pixels, como os polígonos do detector
    )
    analyzer = ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[roi],
        flutter_n_frames=1,  # sem filtro de flutuação: presença crua
        inclusion_rule=config.rule,
        buffer_radius_value=config.buffer_radius_value,
        min_bbox_overlap_ratio=config.min_bbox_overlap_ratio,
    )
    return [bool(v) for v in analyzer._trajectory["in_A_stable"]]


@pytest.mark.parametrize(
    "config",
    [
        RoiRuleConfig("centroid_in"),
        RoiRuleConfig("centroid_in_on_buffered_roi", buffer_radius_value=15.0),
        RoiRuleConfig("bbox_intersects", min_bbox_overlap_ratio=0.10),
        RoiRuleConfig("bbox_intersects", min_bbox_overlap_ratio=0.60),
    ],
    ids=["centroid_in", "buffered", "bbox_10pct", "bbox_60pct"],
)
def test_evaluator_agrees_with_roi_analyzer(config):
    """O gatilho ao vivo e o relatório precisam concordar caixa a caixa."""
    expected = _roi_analyzer_presence(PARITY_BOXES, config)
    evaluator = ArduinoRoiEvaluator(["A"], [BIG_SQUARE], config)
    actual = [evaluator.occupied_rois([box]) == {"A"} for box in PARITY_BOXES]
    assert actual == expected
