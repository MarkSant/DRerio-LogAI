"""
Tests for AnalysisService video processing orchestration.
Target: Increase coverage from 42% to 70% (200+ lines).
Focus: Lines 399-730 in analysis_service.py
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def sample_trajectory_parquet(tmp_path):
    """Create sample trajectory parquet file."""
    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2],
            "frame": [0, 1, 2],
            "track_id": [1, 1, 1],
            "x1": [100, 110, 120],
            "y1": [200, 210, 220],
            "x2": [150, 160, 170],
            "y2": [250, 260, 270],
            "confidence": [0.9, 0.9, 0.9],
        }
    )

    parquet_path = tmp_path / "trajectory.parquet"
    df.to_parquet(parquet_path)
    return parquet_path


class TestAnalysisServiceVideoProcessing:
    """Test video processing orchestration methods."""

    def test_load_trajectory_from_parquet_success(
        self, analysis_service, sample_trajectory_parquet
    ):
        """Test successful loading of trajectory from parquet."""
        df = analysis_service.load_trajectory_dataframe(sample_trajectory_parquet)

        assert df is not None
        assert len(df) == 3
        assert "x1" in df.columns
        assert "track_id" in df.columns

    def test_load_trajectory_from_parquet_file_not_found(self, analysis_service):
        """Test loading trajectory from non-existent file."""
        with pytest.raises(FileNotFoundError):
            analysis_service.load_trajectory_dataframe(Path("/nonexistent/file.parquet"))

    def test_load_trajectory_from_parquet_invalid_format(self, analysis_service, tmp_path):
        """Test loading trajectory from invalid parquet."""
        invalid_file = tmp_path / "invalid.parquet"
        invalid_file.write_text("not a parquet file")

        with pytest.raises((ValueError, OSError, Exception)):  # Should raise some exception
            analysis_service.load_trajectory_dataframe(invalid_file)

    def test_validate_trajectory_schema_valid(self, analysis_service):
        """Test schema validation with valid dataframe."""
        df = pd.DataFrame(
            {
                "timestamp": [0.0],
                "frame": [0],
                "track_id": [1],
                "x1": [100],
                "y1": [100],
                "x2": [150],
                "y2": [150],
            }
        )
        assert analysis_service.validate_trajectory_schema(df) is True

    def test_validate_trajectory_schema_missing_columns(self, analysis_service):
        """Test schema validation with missing columns."""
        df = pd.DataFrame({"timestamp": [0.0], "frame": [0], "x1": [100]})
        with pytest.raises(ValueError, match="missing required columns"):
            analysis_service.validate_trajectory_schema(df)

    @patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer")
    @patch("zebtrack.analysis.analysis_service.ROIAnalyzer")
    def test_run_analysis_pipeline_success(
        self, mock_roi_analyzer_class, mock_behavior_analyzer_class, analysis_service
    ):
        """Test complete analysis pipeline execution."""
        # Setup mocks
        mock_behavior = MagicMock()
        mock_behavior.calculate_total_distance.return_value = 100.0
        mock_behavior.get_velocity_stats.return_value = {"mean": 5.0}
        mock_behavior.calculate_speed_bursts.return_value = []
        mock_behavior.detect_freezing_episodes.return_value = []
        mock_behavior.get_tortuosity.return_value = 1.0
        mock_behavior.calculate_inactivity_periods.return_value = []
        mock_behavior.calculate_sharp_turns.return_value = []
        mock_behavior_analyzer_class.return_value = mock_behavior

        mock_roi = MagicMock()
        mock_roi.get_time_spent_in_rois.return_value = {}
        mock_roi.get_latency_to_first_entry.return_value = {}
        mock_roi.get_entry_counts.return_value = {}
        mock_roi.get_exit_counts.return_value = {}
        mock_roi.get_distance_in_rois.return_value = {}
        mock_roi.get_velocity_stats_in_rois.return_value = {}
        mock_roi.get_freezing_in_rois.return_value = {}
        mock_roi.get_roi_transitions.return_value = MagicMock(to_dict=lambda orient: {})
        mock_roi.get_event_log.return_value = MagicMock(to_dict=lambda orient: [])
        mock_roi_analyzer_class.return_value = mock_roi

        # Create sample data
        df = pd.DataFrame(
            {
                "x1": [100, 110],
                "y1": [100, 110],
                "x2": [150, 160],
                "y2": [150, 160],
                "frame": [0, 1],
                "track_id": [1, 1],
            }
        )

        result = analysis_service.run_full_analysis(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=1.0,
            freezing_min_duration=0.5,
        )

        assert result is not None
        assert len(result) == 3  # (report_dict, behavior_analyzer, roi_analyzer)
        report, _behavior_analyzer, roi_analyzer = result
        assert "comportamento_geral" in report
        assert roi_analyzer is None  # No ROIs provided

    def test_collect_analysis_parameters_from_project(self, analysis_service, mock_settings):
        """Test parameter collection from project config."""
        project_data = {
            "calibration": {
                "pixelcm_x": 10.0,
                "pixelcm_y": 10.0,
                "aquarium_width_cm": 30.0,
                "aquarium_height_cm": 20.0,
            },
            "video_info": {"fps": 30.0, "width": 640, "height": 480},
        }

        params = analysis_service.collect_analysis_parameters(project_data)

        assert "freezing_vel_threshold" in params
        assert "freezing_min_duration" in params
        assert params["smoothing_window_length"] == mock_settings.trajectory_smoothing.window_length

    def test_settings_not_injected_raises_runtime_error(self):
        """Test that AnalysisService raises error if settings not provided.

        This test validates the 'RuntimeError vs graceful fallback' pattern
        from DEPENDENCY_INJECTION_GUIDE.md - services should raise RuntimeError
        when required dependencies are not injected.
        """
        service = AnalysisService(settings_obj=None)

        with pytest.raises(RuntimeError, match="Settings not injected"):
            service.run_full_analysis(
                trajectory_df=pd.DataFrame(),
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=480,
                arena_polygon_px=[],
                rois=[],
                fps=30.0,
                freezing_vel_threshold=1.0,
                freezing_min_duration=0.5,
            )

    def test_resolve_analysis_profile_default(self, analysis_service, mock_settings):
        """Test resolving analysis profile returns defaults when no profiles exist."""
        project_data = {}
        metadata = {}

        profile = analysis_service.resolve_analysis_profile(metadata, project_data)

        assert profile is not None
        assert profile["name"] == "default"
        assert (
            profile["freezing_vel_threshold"]
            == mock_settings.video_processing.freezing_velocity_threshold
        )

    def test_resolve_analysis_profile_with_matching_criteria(self, analysis_service):
        """Test resolving analysis profile with matching metadata."""
        project_data = {
            "analysis_profiles": [
                {
                    "name": "profile_a",
                    "criteria": {"group": "control"},
                    "freezing_vel_threshold": 0.5,
                },
                {
                    "name": "profile_b",
                    "criteria": {"group": "treatment"},
                    "freezing_vel_threshold": 1.5,
                },
            ]
        }
        metadata = {"group": "treatment"}

        profile = analysis_service.resolve_analysis_profile(metadata, project_data)

        assert profile["name"] == "profile_b"
        assert profile["freezing_vel_threshold"] == 1.5

    def test_resolve_analysis_profile_no_match_returns_first(self, analysis_service):
        """Test resolving analysis profile returns first when no match."""
        project_data = {
            "analysis_profiles": [
                {
                    "name": "profile_a",
                    "criteria": {"group": "control"},
                    "freezing_vel_threshold": 0.5,
                }
            ]
        }
        metadata = {"group": "other"}

        profile = analysis_service.resolve_analysis_profile(metadata, project_data)

        assert profile["name"] == "profile_a"

    def test_profile_matches_exact_match(self, analysis_service):
        """Test profile matching with exact criteria match."""
        profile = {"criteria": {"group": "control", "subject": "fish_1"}}
        metadata = {"group": "control", "subject": "fish_1", "extra": "value"}

        assert analysis_service._profile_matches(profile, metadata) is True

    def test_profile_matches_partial_mismatch(self, analysis_service):
        """Test profile matching with partial mismatch."""
        profile = {"criteria": {"group": "control", "subject": "fish_1"}}
        metadata = {"group": "control", "subject": "fish_2"}

        assert analysis_service._profile_matches(profile, metadata) is False

    def test_default_analysis_profile(self, analysis_service, mock_settings):
        """Test default analysis profile generation."""
        profile = analysis_service._default_analysis_profile()

        assert profile["name"] == "default"
        assert (
            profile["freezing_vel_threshold"]
            == mock_settings.video_processing.freezing_velocity_threshold
        )
        assert (
            profile["smoothing_window_length"] == mock_settings.trajectory_smoothing.window_length
        )

    def test_determine_processing_intervals_single_video(self, analysis_service):
        """Test interval determination for single video mode."""
        single_video_config = {"analysis_interval_frames": 5, "display_interval_frames": 10}

        analysis_interval, display_interval = analysis_service.determine_processing_intervals(
            single_video_config, None
        )

        assert analysis_interval == 5
        assert display_interval == 10

    def test_determine_processing_intervals_project(self, analysis_service):
        """Test interval determination from project data."""
        project_data = {"analysis_interval_frames": 15, "display_interval_frames": 20}

        analysis_interval, display_interval = analysis_service.determine_processing_intervals(
            None, project_data
        )

        assert analysis_interval == 15
        assert display_interval == 20

    def test_determine_processing_intervals_defaults(self, analysis_service):
        """Test interval determination with defaults."""
        analysis_interval, display_interval = analysis_service.determine_processing_intervals(
            None, None
        )

        assert analysis_interval == 10
        assert display_interval == 10

    def test_build_metadata_context_single_video(self, analysis_service):
        """Test metadata context returns None for single video."""
        video_info = {"metadata": {"group": "control"}}
        single_video_config = {"some": "config"}

        metadata = analysis_service.build_metadata_context(
            video_info=video_info,
            single_video_config=single_video_config,
            experiment_id="exp_001",
            video_path="/path/to/video.mp4",
        )

        assert metadata is None

    def test_build_metadata_context_with_derive_callback(self, analysis_service):
        """Test metadata context with derive callback."""
        video_info = {"metadata": {"group": "control"}}

        def mock_derive(exp_id, video_path):
            return {"subject": "fish_1", "derived": True}

        metadata = analysis_service.build_metadata_context(
            video_info=video_info,
            single_video_config=None,
            experiment_id="exp_001",
            video_path="/path/to/video.mp4",
            derive_callback=mock_derive,
        )

        assert metadata is not None
        assert metadata["group"] == "control"
        assert metadata["subject"] == "fish_1"
        assert metadata["derived"] is True

    def test_build_metadata_context_derive_callback_fails(self, analysis_service):
        """Test metadata context when derive callback fails."""
        video_info = {"metadata": {"group": "control"}}

        def failing_derive(exp_id, video_path):
            raise ValueError("Derive failed")

        # Should handle exception gracefully
        metadata = analysis_service.build_metadata_context(
            video_info=video_info,
            single_video_config=None,
            experiment_id="exp_001",
            video_path="/path/to/video.mp4",
            derive_callback=failing_derive,
        )

        assert metadata is not None
        assert metadata["group"] == "control"
        # Derived data should not be present
        assert "subject" not in metadata
