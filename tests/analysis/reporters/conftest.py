"""Fixtures compartilhadas para os testes dos reporters de exportação.

Reaproveita o padrão de construção de ``ReporterContext`` usado em
``tests/analysis/test_reporter.py``: cria um ``AnalysisResult`` via
``AnalysisService.run_full_analysis_as_dto`` e instancia o contexto com
``ReporterContext.from_analysis`` (caminho recomendado, sem ``DeprecationWarning``).
"""

from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporters import ReporterContext
from zebtrack.analysis.roi import ROI


@pytest.fixture
def reporter_mock_settings():
    """Configurações mínimas para o ``AnalysisService``."""
    settings = Mock()
    settings.trajectory_smoothing = Mock()
    settings.trajectory_smoothing.window_length = 5
    settings.trajectory_smoothing.polyorder = 2
    settings.angular_velocity = Mock()
    settings.angular_velocity.min_displacement_threshold_cm = 0.5
    settings.angular_velocity.angle_calculation_window = 3
    settings.angular_velocity.angular_velocity_smoothing_window = 5
    settings.roi_inclusion_rule = "centroid_in"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5
    return settings


@pytest.fixture
def reporter_trajectory_df():
    """Trajetória sintética com bbox (x1/y1/x2/y2) suficiente para análise."""
    n = 30
    return pd.DataFrame(
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


@pytest.fixture
def reporter_rois():
    """Duas ROIs retangulares não sobrepostas em espaço de pixels."""
    return [
        ROI(
            name="ROI1",
            geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            coordinate_space="px",
        ),
        ROI(
            name="ROI2",
            geometry=Polygon([(20, 20), (30, 20), (30, 30), (20, 30)]),
            coordinate_space="px",
        ),
    ]


def _build_context(settings, trajectory_df, rois, *, metadata=None):
    """Helper: roda a análise completa e devolve um ``ReporterContext``."""
    service = AnalysisService(settings_obj=settings)
    analysis = service.run_full_analysis_as_dto(
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        calibration=None,
        fps=30.0,
        freezing_min_duration=2.0,
        freezing_vel_threshold=1.0,
        metadata=metadata or {"experiment_id": "test_001", "group_id": "G1"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        roi_colors={"ROI1": (255, 0, 0), "ROI2": (0, 255, 0)},
        rois=rois,
        sharp_turn_threshold=45.0,
        smoothing_polyorder=2,
        smoothing_window_length=5,
        trajectory_df=trajectory_df,
        video_height_px=480,
        video_path="/fake/video.mp4",
    )
    return ReporterContext.from_analysis(analysis)


@pytest.fixture
def reporter_ctx(reporter_mock_settings, reporter_trajectory_df, reporter_rois):
    """``ReporterContext`` pronto, com duas ROIs e trajetória válida."""
    return _build_context(reporter_mock_settings, reporter_trajectory_df, reporter_rois)


@pytest.fixture
def reporter_ctx_no_rois(reporter_mock_settings, reporter_trajectory_df):
    """``ReporterContext`` sem ROIs (``r_analyzer`` é ``None``)."""
    return _build_context(reporter_mock_settings, reporter_trajectory_df, [])


@pytest.fixture
def build_reporter_context():
    """Fábrica para testes que precisam de metadados/ROIs customizados."""
    return _build_context
