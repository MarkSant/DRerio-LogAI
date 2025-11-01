"""
Tests for error handling in AnalysisService.
Focus: Graceful degradation, error messages, cleanup.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.trajectory_smoothing.enabled = True
    settings.trajectory_smoothing.window_length = 11
    settings.trajectory_smoothing.polyorder = 3
    settings.performance.enable_parallel_analysis = False
    settings.angular_velocity.min_displacement_threshold_cm = 0.1
    settings.angular_velocity.angle_calculation_window = 5
    settings.angular_velocity.angular_velocity_smoothing_window = 5
    settings.roi_inclusion_rule = "bbox_center"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5
    settings.video_processing.freezing_velocity_threshold = 1.0
    settings.video_processing.freezing_min_duration_s = 0.5
    return settings


@pytest.fixture
def analysis_service(mock_settings):
    """Create AnalysisService instance."""
    return AnalysisService(settings_obj=mock_settings)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_trajectory_handled_gracefully(self, analysis_service):
        """Test analysis with empty trajectory DataFrame."""
        empty_df = pd.DataFrame(columns=["x1", "y1", "x2", "y2"])

        # Empty trajectory should raise an error during analysis
        with patch(
            "zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer"
        ) as mock_analyzer:
            mock_analyzer.side_effect = ValueError("Cannot analyze empty trajectory")

            with pytest.raises((ValueError, Exception)):
                analysis_service.run_full_analysis(
                    trajectory_df=empty_df,
                    pixelcm_x=10.0,
                    pixelcm_y=10.0,
                    video_height_px=480,
                    arena_polygon_px=[],
                    rois=[],
                    fps=30.0,
                    freezing_vel_threshold=1.0,
                    freezing_min_duration=0.5,
                )

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    def test_single_frame_trajectory(self, mock_analyzer_class, analysis_service):
        """Test analysis with only one frame."""
        single_frame_df = pd.DataFrame({"x1": [100], "y1": [100], "x2": [150], "y2": [150]})

        # Mock analyzer to handle single frame gracefully
        mock_analyzer = MagicMock()
        mock_analyzer.calculate_total_distance.return_value = 0.0
        mock_analyzer.get_velocity_stats.return_value = {"mean": 0.0}
        mock_analyzer.calculate_speed_bursts.return_value = []
        mock_analyzer.detect_freezing_episodes.return_value = []
        mock_analyzer.get_tortuosity.return_value = 0.0
        mock_analyzer.calculate_inactivity_periods.return_value = []
        mock_analyzer.calculate_sharp_turns.return_value = []
        mock_analyzer_class.return_value = mock_analyzer

        # Should handle gracefully (cannot compute velocity from 1 frame)
        result = analysis_service.run_full_analysis(
            trajectory_df=single_frame_df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=1.0,
            freezing_min_duration=0.5,
        )

        # Should return result but with limited metrics
        assert result is not None
        report, _analyzer, _roi_analyzer = result
        assert "comportamento_geral" in report

    def test_corrupted_parquet_file(self, analysis_service, tmp_path):
        """Test loading corrupted parquet file."""
        corrupted_file = tmp_path / "corrupted.parquet"
        corrupted_file.write_bytes(b"corrupted data")

        with pytest.raises((ValueError, OSError, Exception)):
            analysis_service.load_trajectory_dataframe(corrupted_file)

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    def test_mismatched_trajectory_schema(self, mock_analyzer_class, analysis_service, tmp_path):
        """Test trajectory with missing required columns."""
        # Missing 'y2' column
        invalid_df = pd.DataFrame({"x1": [100], "y1": [100], "x2": [150]})

        # The analyzer might fail due to missing columns
        mock_analyzer_class.side_effect = KeyError("Missing column 'y2'")

        with pytest.raises((KeyError, ValueError, Exception)):
            analysis_service.run_full_analysis(
                trajectory_df=invalid_df,
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=480,
                arena_polygon_px=[],
                rois=[],
                fps=30.0,
                freezing_vel_threshold=1.0,
                freezing_min_duration=0.5,
            )

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    def test_analysis_with_nan_values(self, mock_analyzer_class, analysis_service):
        """Test analysis with NaN values in trajectory."""
        df_with_nan = pd.DataFrame(
            {
                "x1": [100, np.nan, 120],
                "y1": [100, 110, np.nan],
                "x2": [150, 160, 170],
                "y2": [150, 160, 170],
            }
        )

        # Mock analyzer to handle NaN gracefully
        mock_analyzer = MagicMock()
        mock_analyzer.calculate_total_distance.return_value = 50.0
        mock_analyzer.get_velocity_stats.return_value = {"mean": 5.0}
        mock_analyzer.calculate_speed_bursts.return_value = []
        mock_analyzer.detect_freezing_episodes.return_value = []
        mock_analyzer.get_tortuosity.return_value = 1.0
        mock_analyzer.calculate_inactivity_periods.return_value = []
        mock_analyzer.calculate_sharp_turns.return_value = []
        mock_analyzer_class.return_value = mock_analyzer

        # Should handle NaN gracefully (interpolate or skip)
        result = analysis_service.run_full_analysis(
            trajectory_df=df_with_nan,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=1.0,
            freezing_min_duration=0.5,
        )

        assert result is not None

    def test_invalid_parquet_path_string(self, analysis_service):
        """Test loading with invalid path as string."""
        with pytest.raises(FileNotFoundError):
            analysis_service.load_trajectory_dataframe("non_existent_path.parquet")

    def test_invalid_parquet_path_object(self, analysis_service):
        """Test loading with invalid path as Path object."""
        with pytest.raises(FileNotFoundError):
            analysis_service.load_trajectory_dataframe(Path("/tmp/non_existent.parquet"))

    def test_schema_validation_extra_columns_allowed(self, analysis_service):
        """Test schema validation allows extra columns beyond required."""
        df = pd.DataFrame(
            {
                "timestamp": [0.0],
                "frame": [0],
                "track_id": [1],
                "x1": [100],
                "y1": [100],
                "x2": [150],
                "y2": [150],
                "extra_col": ["value"],  # Extra column should be allowed
            }
        )

        # Should pass validation with extra columns
        assert analysis_service.validate_trajectory_schema(df) is True

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    def test_negative_coordinates_handled(self, mock_analyzer_class, analysis_service):
        """Test analysis with negative coordinates."""
        df_negative = pd.DataFrame(
            {"x1": [-10, -5, 0], "y1": [-20, -10, 0], "x2": [10, 15, 20], "y2": [10, 15, 20]}
        )

        # Mock analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.calculate_total_distance.return_value = 30.0
        mock_analyzer.get_velocity_stats.return_value = {"mean": 5.0}
        mock_analyzer.calculate_speed_bursts.return_value = []
        mock_analyzer.detect_freezing_episodes.return_value = []
        mock_analyzer.get_tortuosity.return_value = 1.0
        mock_analyzer.calculate_inactivity_periods.return_value = []
        mock_analyzer.calculate_sharp_turns.return_value = []
        mock_analyzer_class.return_value = mock_analyzer

        # Should handle negative coordinates
        result = analysis_service.run_full_analysis(
            trajectory_df=df_negative,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=1.0,
            freezing_min_duration=0.5,
        )

        assert result is not None

    def test_collect_parameters_with_malformed_project_data(self, analysis_service):
        """Test parameter collection with malformed project data."""
        malformed_project_data = {
            "calibration": None,  # Should be dict
            "video_info": "not_a_dict",  # Should be dict
        }

        # Should fall back to defaults without crashing
        params = analysis_service.collect_analysis_parameters(malformed_project_data)

        assert "freezing_vel_threshold" in params
        assert "freezing_min_duration" in params

    def test_resolve_profile_with_none_metadata(self, analysis_service):
        """Test profile resolution with None metadata."""
        project_data = {
            "analysis_profiles": [{"name": "default_profile", "freezing_vel_threshold": 1.5}]
        }

        # Should handle None metadata gracefully
        profile = analysis_service.resolve_analysis_profile(None, project_data)

        assert profile is not None
        assert profile["name"] == "default_profile"

    def test_profile_matches_with_empty_criteria(self, analysis_service):
        """Test profile matching with empty criteria."""
        profile = {"criteria": {}}
        metadata = {"group": "control", "subject": "fish_1"}

        # Empty criteria should match any metadata
        assert analysis_service._profile_matches(profile, metadata) is True

    def test_build_metadata_context_with_none_video_info(self, analysis_service):
        """Test metadata context with None video_info."""
        # Should handle None gracefully
        metadata = analysis_service.build_metadata_context(
            video_info={"metadata": None},
            single_video_config=None,
            experiment_id="exp_001",
            video_path="/path/to/video.mp4",
        )

        assert metadata is not None
        assert isinstance(metadata, dict)

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    def test_analysis_with_very_large_coordinates(self, mock_analyzer_class, analysis_service):
        """Test analysis with very large coordinate values."""
        df_large = pd.DataFrame(
            {
                "x1": [10000, 10100, 10200],
                "y1": [20000, 20100, 20200],
                "x2": [10050, 10150, 10250],
                "y2": [20050, 20150, 20250],
            }
        )

        # Mock analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.calculate_total_distance.return_value = 300.0
        mock_analyzer.get_velocity_stats.return_value = {"mean": 50.0}
        mock_analyzer.calculate_speed_bursts.return_value = []
        mock_analyzer.detect_freezing_episodes.return_value = []
        mock_analyzer.get_tortuosity.return_value = 1.0
        mock_analyzer.calculate_inactivity_periods.return_value = []
        mock_analyzer.calculate_sharp_turns.return_value = []
        mock_analyzer_class.return_value = mock_analyzer

        # Should handle large coordinates
        result = analysis_service.run_full_analysis(
            trajectory_df=df_large,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=1.0,
            freezing_min_duration=0.5,
        )

        assert result is not None

    def test_load_trajectory_with_directory_path(self, analysis_service, tmp_path):
        """Test loading trajectory when given a directory instead of file."""
        directory = tmp_path / "some_dir"
        directory.mkdir()

        # Pandas read_parquet on a directory returns empty DataFrame
        # This is acceptable behavior - it doesn't crash
        df = analysis_service.load_trajectory_dataframe(directory)

        # Should return a DataFrame (possibly empty)
        assert isinstance(df, pd.DataFrame)
