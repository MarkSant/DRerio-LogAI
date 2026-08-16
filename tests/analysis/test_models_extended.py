"""
Extended unit tests for Analysis DTOs in analysis/models.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from zebtrack.analysis.models import AnalysisResult, CalibrationParams


class TestCalibrationParamsExtended:
    """Test CalibrationParams dataclass initialization and field access."""

    def test_init_all_fields(self):
        calib = CalibrationParams(
            pixelcm_x=10.5,
            pixelcm_y=10.5,
            video_height_px=720,
            arena_polygon_px=[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]],
            fps=30.0,
            calibration=None,
        )
        assert calib.pixelcm_x == 10.5
        assert calib.pixelcm_y == 10.5
        assert calib.video_height_px == 720
        assert len(calib.arena_polygon_px) == 4
        assert calib.fps == 30.0
        assert calib.calibration is None


class TestAnalysisResultExtended:
    """Test AnalysisResult dataclass defaults, custom parameters, and factories."""

    def test_init_minimal_and_defaults(self):
        calib = CalibrationParams(
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=1080,
            arena_polygon_px=[[0.0, 0.0]],
            fps=25.0,
        )
        df = pd.DataFrame({"frame": [1, 2], "x": [10.0, 12.0], "y": [20.0, 22.0]})

        res = AnalysisResult(
            report={"metrics": {}},
            behavioral_analyzer=MagicMock(),
            roi_analyzer=None,
            trajectory_df=df,
            metadata={"experiment_id": "exp_01"},
            calibration_params=calib,
            rois=[],
            roi_colors={},
        )

        assert res.report == {"metrics": {}}
        assert res.roi_analyzer is None
        assert res.metadata["experiment_id"] == "exp_01"
        assert res.sharp_turn_threshold == 45.0
        assert res.freezing_threshold == 1.5
        assert res.freezing_duration == 1.0
        assert res.smoothing_window_length is None
        assert res.smoothing_polyorder is None
        assert res.validation_warnings == []
        assert res.validation_stats == {}
        assert res.frame_crop_box is None
        assert res.behavioral_config == {}

    def test_init_custom_thresholds_and_configs(self):
        calib = CalibrationParams(
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=1080,
            arena_polygon_px=[[0.0, 0.0]],
            fps=30.0,
        )
        res = AnalysisResult(
            report={"dist": 150.0},
            behavioral_analyzer=MagicMock(),
            roi_analyzer=MagicMock(),
            trajectory_df=pd.DataFrame(),
            metadata={"group": "CBD"},
            calibration_params=calib,
            rois=[MagicMock()],
            roi_colors={"ROI1": (255, 0, 0)},
            video_path="/path/vid.mp4",
            sharp_turn_threshold=60.0,
            freezing_threshold=2.0,
            freezing_duration=1.5,
            smoothing_window_length=11,
            smoothing_polyorder=3,
            validation_warnings=["Warning: high jitter"],
            validation_stats={"gap_count": 2},
            frame_crop_box=(10, 20, 300, 200),
            behavioral_config={"geotaxis_num_zones": 3},
        )

        assert res.video_path == "/path/vid.mp4"
        assert res.sharp_turn_threshold == 60.0
        assert res.freezing_threshold == 2.0
        assert res.smoothing_window_length == 11
        assert res.smoothing_polyorder == 3
        assert res.validation_warnings == ["Warning: high jitter"]
        assert res.validation_stats["gap_count"] == 2
        assert res.frame_crop_box == (10, 20, 300, 200)
        assert res.behavioral_config["geotaxis_num_zones"] == 3
