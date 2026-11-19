"""
Tests for batch video processing in AnalysisService.
Focus: Batch coordination, progress tracking, error handling.
"""

from unittest.mock import MagicMock

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
    settings.video_processing.freezing_velocity_threshold = 1.0
    settings.video_processing.freezing_min_duration_s = 0.5
    return settings


@pytest.fixture
def analysis_service(mock_settings):
    """Create AnalysisService instance."""
    return AnalysisService(settings_obj=mock_settings)


class TestBatchProcessing:
    """Test batch video processing functionality."""

    def test_determine_intervals_precedence(self, analysis_service):
        """Single-video config wins over project data — and display follows analysis.

        The stored ``display_interval_frames`` (14 here) is deliberately ignored:
        the preview redraws on the frames that were analysed, so there is one
        number, not two. A separate display interval let the overlay repaint on
        frames carrying no fresh detection.
        """
        single_video_config = {"analysis_interval_frames": 7, "display_interval_frames": 14}
        project_data = {"analysis_interval_frames": 20, "display_interval_frames": 30}

        analysis_interval, display_interval = analysis_service.determine_processing_intervals(
            single_video_config, project_data
        )

        # Single video config should take precedence
        assert analysis_interval == 7
        assert display_interval == 7
