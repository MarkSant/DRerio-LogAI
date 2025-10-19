from pathlib import Path

import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.settings import settings


@pytest.fixture
def trajectory_file(tmp_path: Path) -> Path:
    """Create a dummy trajectory file for testing."""
    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2],
            "frame": [0, 1, 2],
            "track_id": [1, 1, 1],
            "x1": [10, 11, 12],
            "y1": [20, 21, 22],
            "x2": [30, 31, 32],
            "y2": [40, 41, 42],
        }
    )
    file_path = tmp_path / "trajectory.parquet"
    df.to_parquet(file_path)
    return file_path


def test_load_trajectory_dataframe_success(trajectory_file: Path):
    """Test that the service can load a valid trajectory file."""
    service = AnalysisService()
    df = service.load_trajectory_dataframe(trajectory_file)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert "track_id" in df.columns


def test_load_trajectory_dataframe_not_found():
    """Test that the service raises an error if the file is not found."""
    service = AnalysisService()
    with pytest.raises(FileNotFoundError):
        service.load_trajectory_dataframe("non_existent_file.parquet")


def test_collect_analysis_parameters_defaults():
    """Test that the service returns default parameters when no project data is provided."""
    service = AnalysisService()
    params = service.collect_analysis_parameters()
    assert params["freezing_vel_threshold"] == settings.video_processing.freezing_velocity_threshold
    assert params["freezing_min_duration"] == settings.video_processing.freezing_min_duration_s
    assert params["smoothing_window_length"] == settings.trajectory_smoothing.window_length
    assert params["smoothing_polyorder"] == settings.trajectory_smoothing.polyorder


def test_collect_analysis_parameters_with_overrides():
    """Test that the service correctly applies project-specific overrides."""
    service = AnalysisService()
    project_data = {
        "analysis_parameters": {
            "freezing_vel_threshold": 0.5,
            "smoothing_window_length": 11,
        }
    }
    params = service.collect_analysis_parameters(project_data)
    assert params["freezing_vel_threshold"] == 0.5
    assert params["smoothing_window_length"] == 11
    # Ensure other params fall back to defaults
    assert params["freezing_min_duration"] == settings.video_processing.freezing_min_duration_s


def test_validate_trajectory_schema_success():
    """Test that the schema validation passes with a valid dataframe."""
    service = AnalysisService()
    df = pd.DataFrame(
        {
            "timestamp": [],
            "frame": [],
            "track_id": [],
            "x1": [],
            "y1": [],
            "x2": [],
            "y2": [],
        }
    )
    assert service.validate_trajectory_schema(df) is True


def test_validate_trajectory_schema_missing_columns():
    """Test that schema validation fails if columns are missing."""
    service = AnalysisService()
    df = pd.DataFrame({"timestamp": [], "frame": []})
    with pytest.raises(ValueError, match="missing required columns"):
        service.validate_trajectory_schema(df)
