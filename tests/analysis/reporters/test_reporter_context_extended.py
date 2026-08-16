"""
Extended unit tests for ReporterContext.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from zebtrack.analysis.models import AnalysisResult, CalibrationParams
from zebtrack.analysis.reporters.reporter_context import ReporterContext


class TestReporterContextExtended:
    """Test ReporterContext factory and utility methods."""

    def test_normalize_aquarium_perspective_delegate(self):
        assert ReporterContext._normalize_aquarium_perspective("top_down") == "top_down"
        assert ReporterContext._normalize_aquarium_perspective("lateral") == "lateral"
        assert ReporterContext._normalize_aquarium_perspective(None) == "lateral"

    def test_from_analysis_factory(self):
        calib_params = CalibrationParams(
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[[0.0, 0.0], [480.0, 0.0], [480.0, 480.0], [0.0, 480.0]],
            fps=30.0,
            calibration=None,
        )

        traj_df = pd.DataFrame({"x_cm": [1.0], "y_cm": [2.0]})
        mock_b_analyzer = MagicMock()
        mock_b_analyzer.trajectory_data = traj_df
        mock_r_analyzer = MagicMock()

        dto = AnalysisResult(
            report={"metric_a": 123},
            behavioral_analyzer=mock_b_analyzer,
            roi_analyzer=mock_r_analyzer,
            trajectory_df=traj_df,
            metadata={"experiment_id": "EXP1", "group_id": "GRP1"},
            calibration_params=calib_params,
            rois=[],
            roi_colors={"Zone1": (255, 0, 0)},
            video_path="/path/to/vid.mp4",
            validation_warnings=["Warning A"],
            validation_stats={"valid_frames": 100},
        )

        with (
            patch("zebtrack.analysis.reporters.reporter_context.DataTransformer") as mock_dt_cls,
            patch("zebtrack.analysis.reporters.reporter_context.VisualizationGenerator"),
        ):
            mock_dt = MagicMock()
            tidy_df = pd.DataFrame({"experiment_id": ["EXP1"], "group_id": ["GRP1"]})
            mock_dt.create_tidy_dataframe.return_value = tidy_df
            mock_dt.standardize_tidy_dataframe.return_value = tidy_df
            mock_dt.build_per_animal_dataframe.return_value = pd.DataFrame({"subject_id": [1]})
            mock_dt_cls.return_value = mock_dt

            ctx = ReporterContext.from_analysis(dto)

            assert ctx.metadata == {"experiment_id": "EXP1", "group_id": "GRP1"}
            assert ctx.video_path == "/path/to/vid.mp4"
            assert ctx.validation_warnings == ["Warning A"]
            assert ctx.validation_stats == {"valid_frames": 100}
            assert ctx.b_analyzer is mock_b_analyzer
            assert ctx.r_analyzer is mock_r_analyzer
            assert ctx.tidy_data is not None
            assert ctx.per_animal_data is not None
