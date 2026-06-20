"""End-to-end ground-truth test through ``AnalysisService.run_full_analysis_as_dto``.

The unit tests pin metric maths in isolation; this proves the *whole chain*
(raw trajectory -> preprocessing -> behavioural report DTO) yields the exact
numbers a paper would quote. We feed a synthetic straight-line trajectory whose
distance and speed are computable by hand and assert the values that land in
``report["comportamento_geral"]`` -- the dict the Excel/Word reporters render.

A straight line is preserved by Savitzky-Golay for any polyorder, so the
expected values are independent of the smoothing settings.

Ground truth: 100 px horizontal over 11 frames @ pixelcm=10 -> 10.0 cm; fps=10
-> dt=0.1 s and a constant 10 cm/s speed.
"""

from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.models import AnalysisResult
from zebtrack.analysis.roi import ROI


def _settings() -> Mock:
    """Minimal duck-typed settings for AnalysisService (mirrors reporter tests)."""
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
    return settings


def _horizontal_trajectory() -> pd.DataFrame:
    xs = [100.0 + 10.0 * i for i in range(11)]  # 100..200 px
    ys = [240.0] * 11
    return pd.DataFrame(
        {
            "timestamp": [i / 10.0 for i in range(11)],  # fps = 10 -> dt = 0.1 s
            "frame": list(range(11)),
            "track_id": [1] * 11,
            "x1": [x - 5 for x in xs],
            "y1": [y - 5 for y in ys],
            "x2": [x + 5 for x in xs],
            "y2": [y + 5 for y in ys],
            "confidence": [0.95] * 11,
        }
    )


def _run(rois: list[ROI]) -> AnalysisResult:
    service = AnalysisService(settings_obj=_settings())  # type: ignore[arg-type]
    return service.run_full_analysis_as_dto(
        arena_polygon_px=[(0, 0), (480, 0), (480, 480), (0, 480)],
        calibration=None,
        fps=10.0,
        freezing_min_duration=2.0,
        freezing_vel_threshold=1.0,
        metadata={"experiment_id": "gt_001", "group_id": "G1"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        roi_colors={r.name: (255, 0, 0) for r in rois},
        rois=rois,
        sharp_turn_threshold=45.0,
        smoothing_polyorder=2,
        smoothing_window_length=5,
        trajectory_df=_horizontal_trajectory(),
        video_height_px=480,
        video_path="/fake/video.mp4",
    )


class TestEndToEndGroundTruth:
    """The full pipeline produces the hand-computed behavioural numbers."""

    def test_total_distance_matches_hand_computation(self) -> None:
        result = _run(rois=[])
        general = result.report["comportamento_geral"]
        assert general["distancia_total_cm"] == pytest.approx(10.0)

    def test_mean_velocity_matches_hand_computation(self) -> None:
        result = _run(rois=[])
        general = result.report["comportamento_geral"]
        assert general["estatisticas_velocidade"]["mean"] == pytest.approx(10.0)
        assert general["estatisticas_velocidade"]["max"] == pytest.approx(10.0)

    def test_straight_line_tortuosity_is_one(self) -> None:
        result = _run(rois=[])
        assert result.report["comportamento_geral"]["tortuosidade"] == pytest.approx(1.0)

    def test_no_rois_yields_no_roi_section_and_null_analyzer(self) -> None:
        result = _run(rois=[])
        assert result.roi_analyzer is None
        assert "analise_roi" not in result.report

    def test_with_roi_produces_roi_section(self) -> None:
        # The whole horizontal path lives inside this ROI (x 95..205, y 235..245).
        roi = ROI(
            name="Tank",
            geometry=Polygon([(0, 0), (480, 0), (480, 480), (0, 480)]),
            coordinate_space="px",
        )
        result = _run(rois=[roi])
        assert result.roi_analyzer is not None
        assert "analise_roi" in result.report
        entry_counts = result.report["analise_roi"]["contagem_entradas"]
        assert "Tank" in entry_counts
        # Spends ~100 % of the session in the all-encompassing ROI.
        time_spent = result.report["analise_roi"]["tempo_gasto_por_roi"]["Tank"]
        assert time_spent["percentage"] == pytest.approx(100.0, abs=1e-6)
