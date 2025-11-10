"""Comprehensive tests for analysis/models.py."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.analysis.models import AnalysisResult, CalibrationParams


def test_calibration_params_creation():
    """Test CalibrationParams dataclass creation."""
    params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        fps=30.0,
    )

    assert params.pixelcm_x == 10.5
    assert params.pixelcm_y == 10.5
    assert params.video_height_px == 1080
    assert params.arena_polygon_px == [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert params.fps == 30.0
    assert params.calibration is None


def test_calibration_params_with_calibration():
    """Test CalibrationParams with calibration object."""
    mock_calibration = MagicMock()

    params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        fps=30.0,
        calibration=mock_calibration,
    )

    assert params.calibration == mock_calibration


def test_calibration_params_default_calibration():
    """Test CalibrationParams default calibration is None."""
    params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        fps=30.0,
    )

    assert params.calibration is None


def test_analysis_result_creation():
    """Test AnalysisResult dataclass creation."""
    mock_behavioral_analyzer = MagicMock()
    mock_roi_analyzer = MagicMock()
    mock_roi = MagicMock()

    trajectory_df = pd.DataFrame({"frame": [0, 1, 2], "x": [10, 20, 30], "y": [40, 50, 60]})

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        fps=30.0,
    )

    result = AnalysisResult(
        report={"metric1": 100, "metric2": 200},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=mock_roi_analyzer,
        trajectory_df=trajectory_df,
        metadata={"experiment_id": "exp_001", "group": "control"},
        calibration_params=calibration_params,
        rois=[mock_roi],
        roi_colors={"roi1": (255, 0, 0)},
    )

    assert result.report == {"metric1": 100, "metric2": 200}
    assert result.behavioral_analyzer == mock_behavioral_analyzer
    assert result.roi_analyzer == mock_roi_analyzer
    assert result.trajectory_df.equals(trajectory_df)
    assert result.metadata == {"experiment_id": "exp_001", "group": "control"}
    assert result.calibration_params == calibration_params
    assert result.rois == [mock_roi]
    assert result.roi_colors == {"roi1": (255, 0, 0)}


def test_analysis_result_optional_fields_defaults():
    """Test AnalysisResult optional fields have correct defaults."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert result.video_path is None
    assert result.sharp_turn_threshold == 45.0
    assert result.freezing_threshold == 1.5
    assert result.freezing_duration == 1.0
    assert result.smoothing_window_length is None
    assert result.smoothing_polyorder is None


def test_analysis_result_with_optional_fields():
    """Test AnalysisResult with optional fields set."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
        video_path="/path/to/video.mp4",
        sharp_turn_threshold=60.0,
        freezing_threshold=2.0,
        freezing_duration=2.0,
        smoothing_window_length=11,
        smoothing_polyorder=3,
    )

    assert result.video_path == "/path/to/video.mp4"
    assert result.sharp_turn_threshold == 60.0
    assert result.freezing_threshold == 2.0
    assert result.freezing_duration == 2.0
    assert result.smoothing_window_length == 11
    assert result.smoothing_polyorder == 3


def test_analysis_result_with_none_roi_analyzer():
    """Test AnalysisResult with None roi_analyzer (no ROIs defined)."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert result.roi_analyzer is None


def test_analysis_result_multiple_rois():
    """Test AnalysisResult with multiple ROIs."""
    mock_behavioral_analyzer = MagicMock()
    mock_roi_analyzer = MagicMock()
    mock_roi1 = MagicMock()
    mock_roi2 = MagicMock()
    mock_roi3 = MagicMock()

    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=mock_roi_analyzer,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[mock_roi1, mock_roi2, mock_roi3],
        roi_colors={"roi1": (255, 0, 0), "roi2": (0, 255, 0), "roi3": (0, 0, 255)},
    )

    assert len(result.rois) == 3
    assert len(result.roi_colors) == 3


def test_analysis_result_complex_metadata():
    """Test AnalysisResult with complex metadata."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    complex_metadata = {
        "experiment_id": "exp_001",
        "group": "control",
        "subject": "fish_01",
        "date": "2025-11-10",
        "researcher": "Dr. Smith",
        "notes": "First trial of the day",
        "nested": {"key1": "value1", "key2": "value2"},
    }

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata=complex_metadata,
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert result.metadata == complex_metadata
    assert result.metadata["nested"]["key1"] == "value1"


def test_analysis_result_empty_report():
    """Test AnalysisResult with empty report."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert result.report == {}


def test_analysis_result_nested_report():
    """Test AnalysisResult with nested report structure."""
    mock_behavioral_analyzer = MagicMock()
    trajectory_df = pd.DataFrame()

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    nested_report = {
        "global_metrics": {"distance": 100, "velocity": 5},
        "roi_metrics": {
            "roi1": {"time_in_roi": 10, "entries": 5},
            "roi2": {"time_in_roi": 20, "entries": 8},
        },
    }

    result = AnalysisResult(
        report=nested_report,
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert result.report["global_metrics"]["distance"] == 100
    assert result.report["roi_metrics"]["roi1"]["time_in_roi"] == 10


def test_analysis_result_large_trajectory():
    """Test AnalysisResult with large trajectory dataframe."""
    mock_behavioral_analyzer = MagicMock()

    # Create a large trajectory
    trajectory_df = pd.DataFrame(
        {
            "frame": list(range(10000)),
            "x": list(range(10000)),
            "y": list(range(10000)),
            "track_id": [1] * 10000,
        }
    )

    calibration_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    result = AnalysisResult(
        report={},
        behavioral_analyzer=mock_behavioral_analyzer,
        roi_analyzer=None,
        trajectory_df=trajectory_df,
        metadata={},
        calibration_params=calibration_params,
        rois=[],
        roi_colors={},
    )

    assert len(result.trajectory_df) == 10000


def test_calibration_params_different_pixel_ratios():
    """Test CalibrationParams with different X and Y pixel ratios."""
    params = CalibrationParams(
        pixelcm_x=10.0,
        pixelcm_y=12.0,  # Different ratio
        video_height_px=1080,
        arena_polygon_px=[],
        fps=30.0,
    )

    assert params.pixelcm_x == 10.0
    assert params.pixelcm_y == 12.0
    assert params.pixelcm_x != params.pixelcm_y


def test_calibration_params_polygon_formats():
    """Test CalibrationParams with different polygon formats."""
    # Rectangle
    rect_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        fps=30.0,
    )
    assert len(rect_params.arena_polygon_px) == 4

    # Triangle
    tri_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (100, 0), (50, 100)],
        fps=30.0,
    )
    assert len(tri_params.arena_polygon_px) == 3

    # Complex polygon
    complex_params = CalibrationParams(
        pixelcm_x=10.5,
        pixelcm_y=10.5,
        video_height_px=1080,
        arena_polygon_px=[(0, 0), (50, 0), (100, 50), (100, 100), (50, 100), (0, 50)],
        fps=30.0,
    )
    assert len(complex_params.arena_polygon_px) == 6
