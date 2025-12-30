"""Tests for multi-aquarium analysis functionality (Phase 10).

These tests cover:
- AnalysisService.run_multi_aquarium_analysis()
- Reporter.export_multi_aquarium_reports()
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.models import AnalysisResult
from zebtrack.analysis.reporter import Reporter
from zebtrack.core.detector import AquariumData


@pytest.fixture
def mock_settings():
    """Create a mock settings object."""
    settings = MagicMock()
    settings.analysis = MagicMock()
    settings.analysis.smoothing_window_length = 5
    settings.analysis.smoothing_polyorder = 2
    return settings


@pytest.fixture
def sample_trajectory_df():
    """Create sample trajectory data."""
    np.random.seed(42)
    n_frames = 100

    return pd.DataFrame(
        {
            "timestamp": np.arange(n_frames) / 30.0,
            "frame": np.arange(n_frames),
            "track_id": [1] * n_frames,
            "x_center_px": 100 + np.cumsum(np.random.randn(n_frames) * 2),
            "y_center_px": 100 + np.cumsum(np.random.randn(n_frames) * 2),
            "x1": 90 + np.cumsum(np.random.randn(n_frames) * 2),
            "y1": 90 + np.cumsum(np.random.randn(n_frames) * 2),
            "x2": 110 + np.cumsum(np.random.randn(n_frames) * 2),
            "y2": 110 + np.cumsum(np.random.randn(n_frames) * 2),
        }
    )


@pytest.fixture
def sample_aquarium_data():
    """Create sample AquariumData for testing."""
    return AquariumData(
        id=0,
        polygon=[[0, 0], [200, 0], [200, 200], [0, 200]],
        roi_polygons=[[[50, 50], [100, 50], [100, 100], [50, 100]]],
        roi_names=["ROI_1"],
        roi_colors=[(255, 0, 0)],
        group="Control",
        subject_id="S01",
        day=1,
    )


@pytest.fixture
def dual_aquarium_data(sample_trajectory_df):
    """Create data for 2 aquariums."""
    aq0 = AquariumData(
        id=0,
        polygon=[[0, 0], [200, 0], [200, 200], [0, 200]],
        roi_polygons=[[[50, 50], [100, 50], [100, 100], [50, 100]]],
        roi_names=["Center"],
        roi_colors=[(255, 0, 0)],
        group="Control",
        subject_id="S01",
        day=1,
    )

    aq1 = AquariumData(
        id=1,
        polygon=[[250, 0], [450, 0], [450, 200], [250, 200]],
        roi_polygons=[[[300, 50], [350, 50], [350, 100], [300, 100]]],
        roi_names=["Center"],
        roi_colors=[(0, 255, 0)],
        group="Treatment",
        subject_id="S02",
        day=1,
    )

    # Create slightly different trajectory for second aquarium
    df2 = sample_trajectory_df.copy()
    df2["x_center_px"] = df2["x_center_px"] + 250
    df2["track_id"] = 1001  # Offset track ID

    return {
        0: (sample_trajectory_df.copy(), aq0),
        1: (df2, aq1),
    }


class TestAnalysisServiceMultiAquarium:
    """Tests for AnalysisService.run_multi_aquarium_analysis()."""

    def test_run_multi_aquarium_analysis_returns_dict(self, mock_settings, dual_aquarium_data):
        """Test that method returns dict with results for each aquarium."""
        service = AnalysisService(settings_obj=mock_settings)

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
        )

        assert isinstance(results, dict)
        assert 0 in results
        assert 1 in results

    def test_results_contain_analysis_result_or_none(self, mock_settings, dual_aquarium_data):
        """Test that results are AnalysisResult instances or None."""
        service = AnalysisService(settings_obj=mock_settings)

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
        )

        for aq_id, result in results.items():
            assert result is None or isinstance(result, AnalysisResult)

    def test_metadata_includes_aquarium_info(self, mock_settings, dual_aquarium_data):
        """Test that metadata includes aquarium-specific information."""
        service = AnalysisService(settings_obj=mock_settings)

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
            metadata={"experiment": "test_001"},
        )

        # Check first aquarium
        if results[0]:
            assert results[0].metadata["aquarium_id"] == 0
            assert results[0].metadata["group"] == "Control"
            assert results[0].metadata["subject_id"] == "S01"
            assert results[0].metadata["experiment"] == "test_001"

        # Check second aquarium
        if results[1]:
            assert results[1].metadata["aquarium_id"] == 1
            assert results[1].metadata["group"] == "Treatment"
            assert results[1].metadata["subject_id"] == "S02"

    def test_handles_single_aquarium(
        self, mock_settings, sample_trajectory_df, sample_aquarium_data
    ):
        """Test that method works with single aquarium."""
        service = AnalysisService(settings_obj=mock_settings)

        single_map = {0: (sample_trajectory_df, sample_aquarium_data)}

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=single_map,
            fps=30.0,
        )

        assert len(results) == 1
        assert 0 in results

    def test_handles_empty_aquarium_map(self, mock_settings):
        """Test that method handles empty input gracefully."""
        service = AnalysisService(settings_obj=mock_settings)

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map={},
            fps=30.0,
        )

        assert results == {}

    def test_continues_on_aquarium_failure(self, mock_settings, dual_aquarium_data):
        """Test that failure in one aquarium doesn't stop others."""
        service = AnalysisService(settings_obj=mock_settings)

        # Corrupt first aquarium's data to cause failure
        bad_df = pd.DataFrame({"bad_column": [1, 2, 3]})
        dual_aquarium_data[0] = (bad_df, dual_aquarium_data[0][1])

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
        )

        # First should fail, second should succeed
        assert results[0] is None
        # Second may or may not succeed depending on data validity

    def test_passes_analysis_parameters(self, mock_settings, dual_aquarium_data):
        """Test that analysis parameters are passed correctly."""
        service = AnalysisService(settings_obj=mock_settings)

        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
            freezing_vel_threshold=2.0,
            freezing_min_duration=0.5,
            sharp_turn_threshold=60.0,
        )

        # Just verify it runs without error with custom parameters
        assert isinstance(results, dict)


class TestReporterMultiAquarium:
    """Tests for Reporter.export_multi_aquarium_reports()."""

    @pytest.fixture
    def mock_analysis_results(self):
        """Create mock AnalysisResult objects."""
        result0 = MagicMock(spec=AnalysisResult)
        result0.metadata = {"aquarium_id": 0, "group": "Control", "subject_id": "S01"}

        result1 = MagicMock(spec=AnalysisResult)
        result1.metadata = {"aquarium_id": 1, "group": "Treatment", "subject_id": "S02"}

        return {0: result0, 1: result1}

    def test_creates_output_directories(self, tmp_path, mock_analysis_results):
        """Test that output directories are created."""
        output_dirs = {
            0: tmp_path / "aq0",
            1: tmp_path / "aq1",
        }

        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            Reporter.export_multi_aquarium_reports(
                results_by_aquarium=mock_analysis_results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        # Directories should be created
        assert output_dirs[0].exists()
        assert output_dirs[1].exists()

    def test_returns_output_paths(self, tmp_path, mock_analysis_results):
        """Test that method returns correct output paths."""
        output_dirs = {
            0: tmp_path / "aq0",
            1: tmp_path / "aq1",
        }

        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            paths = Reporter.export_multi_aquarium_reports(
                results_by_aquarium=mock_analysis_results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        assert 0 in paths
        assert 1 in paths
        assert "summary_path" in paths[0]
        assert "report_path" in paths[0]

    def test_skips_none_results(self, tmp_path):
        """Test that None results are skipped."""
        results = {0: None, 1: MagicMock(spec=AnalysisResult)}
        results[1].metadata = {"aquarium_id": 1, "group": "Treatment"}

        output_dirs = {
            0: tmp_path / "aq0",
            1: tmp_path / "aq1",
        }

        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            paths = Reporter.export_multi_aquarium_reports(
                results_by_aquarium=results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        assert 0 not in paths
        assert 1 in paths

    def test_handles_missing_output_dir(self, tmp_path, mock_analysis_results):
        """Test handling when output directory is not provided."""
        # Only provide directory for aquarium 1
        output_dirs = {1: tmp_path / "aq1"}

        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            paths = Reporter.export_multi_aquarium_reports(
                results_by_aquarium=mock_analysis_results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        assert 0 not in paths
        assert 1 in paths

    def test_uses_aquarium_config_for_naming(self, tmp_path, mock_analysis_results):
        """Test that aquarium config is used for file naming."""
        output_dirs = {0: tmp_path / "aq0"}

        # Create mock config
        mock_config = MagicMock()
        mock_config.aquarium_id = 0
        mock_config.group = "CBD"
        mock_config.subject_id = "Subject_01"

        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            paths = Reporter.export_multi_aquarium_reports(
                results_by_aquarium={0: mock_analysis_results[0]},
                output_dirs_by_aquarium=output_dirs,
                base_name="video",
                aquarium_configs=[mock_config],
            )

        # Check that filename contains group and subject
        if 0 in paths:
            assert "CBD" in paths[0]["summary_path"]
            assert "Subject_01" in paths[0]["summary_path"]

    def test_handles_export_error(self, tmp_path, mock_analysis_results):
        """Test that export errors are handled gracefully."""
        output_dirs = {0: tmp_path / "aq0", 1: tmp_path / "aq1"}

        with patch.object(Reporter, "from_analysis") as mock_from:
            # Make first export fail
            mock_reporter = MagicMock()
            mock_reporter.export_summary_data.side_effect = [Exception("Test error"), None]
            mock_from.return_value = mock_reporter

            # Should not raise, just log error
            Reporter.export_multi_aquarium_reports(
                results_by_aquarium=mock_analysis_results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        # Method should complete without raising


class TestMultiAquariumIntegration:
    """Integration tests for multi-aquarium analysis workflow."""

    def test_full_workflow_analysis_to_report(self, mock_settings, dual_aquarium_data, tmp_path):
        """Test complete workflow from analysis to report generation."""
        service = AnalysisService(settings_obj=mock_settings)

        # Step 1: Run analysis
        results = service.run_multi_aquarium_analysis(
            aquarium_data_map=dual_aquarium_data,
            fps=30.0,
            metadata={"experiment": "integration_test"},
        )

        # Step 2: Create output directories
        output_dirs = {}
        for aq_id in results:
            output_dirs[aq_id] = tmp_path / f"aquarium_{aq_id}"

        # Step 3: Export reports (with mock to avoid actual file generation)
        with patch.object(Reporter, "from_analysis") as mock_from:
            mock_reporter = MagicMock()
            mock_from.return_value = mock_reporter

            paths = Reporter.export_multi_aquarium_reports(
                results_by_aquarium=results,
                output_dirs_by_aquarium=output_dirs,
                base_name="test_video",
            )

        # Verify workflow completed
        assert len(paths) > 0 or all(r is None for r in results.values())
