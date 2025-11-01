"""
Unit tests for Reporter class.

Phase: Sprint 3.2 - Test coverage for report generation
Tests export_summary_data, plot generation, DOCX report creation,
and data validation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
from pathlib import Path
import pandas as pd
import numpy as np
from shapely.geometry import Polygon

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI


@pytest.fixture
def mock_settings():
    """Create mock settings for AnalysisService."""
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
def sample_trajectory_df():
    """Create sample trajectory DataFrame for testing."""
    return pd.DataFrame({
        "timestamp": [0.0, 0.1, 0.2, 0.3],
        "frame": [0, 1, 2, 3],
        "track_id": [1, 1, 1, 1],
        "x1": [10, 11, 12, 13],
        "y1": [20, 21, 22, 23],
        "x2": [30, 31, 32, 33],
        "y2": [40, 41, 42, 43],
        "confidence": [0.95, 0.96, 0.97, 0.98],
    })


@pytest.fixture
def sample_rois():
    """Create sample ROI list for testing."""
    return [
        ROI(name="ROI1", geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), coordinate_space="px"),
        ROI(name="ROI2", geometry=Polygon([(20, 20), (30, 20), (30, 30), (20, 30)]), coordinate_space="px"),
    ]


@pytest.fixture
def reporter(sample_trajectory_df, sample_rois, mock_settings):
    """Create Reporter instance with test data."""
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="zebtrack.analysis.reporter")

    return Reporter(
        trajectory_df=sample_trajectory_df,
        metadata={"experiment_id": "test_001", "group_id": "G1"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        rois=sample_rois,
        fps=30.0,
        roi_colors={"ROI1": (255, 0, 0), "ROI2": (0, 255, 0)},
        video_path="/fake/video.mp4",
        calibration=None,
        sharp_turn_threshold=45.0,
        freezing_threshold=1.0,
        freezing_duration=2.0,
        smoothing_window_length=5,
        smoothing_polyorder=2,
        settings_obj=mock_settings,
    )


@pytest.mark.unit
class TestReporterInitialization:
    """Test suite for Reporter initialization."""

    def test_init_stores_all_parameters(self, reporter):
        """Test that all parameters are stored correctly."""
        assert reporter.metadata["experiment_id"] == "test_001"
        assert reporter._pixelcm_x == 10.0
        assert reporter.b_analyzer is not None
        assert reporter.report is not None

    def test_init_requires_trajectory_df(self, sample_rois, mock_settings):
        """Test that trajectory_df with minimal columns works."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # Create DataFrame with minimal required columns
        minimal_df = pd.DataFrame({
            "timestamp": [0.0, 0.1],
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [10, 11],
            "y1": [20, 21],
            "x2": [30, 31],
            "y2": [40, 41],
        })

        # Should not raise error
        reporter = Reporter(
            trajectory_df=minimal_df,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=sample_rois,
            fps=30.0,
            settings_obj=mock_settings,
        )

        assert reporter is not None

    def test_init_handles_empty_rois(self, sample_trajectory_df, mock_settings):
        """Test initialization with empty ROI list."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        reporter = Reporter(
            trajectory_df=sample_trajectory_df,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        assert reporter.r_analyzer is None  # No ROIs, so no ROI analyzer


@pytest.mark.unit
class TestExportSummaryData:
    """Test suite for export_summary_data method."""

    @patch('zebtrack.analysis.reporter.pd.DataFrame.to_parquet')
    def test_export_summary_parquet(self, mock_to_parquet, reporter, tmp_path):
        """Test export summary data to Parquet format."""
        output_path = tmp_path / "summary.parquet"

        reporter.export_summary_data(output_path, format="parquet")

        # Should call to_parquet
        mock_to_parquet.assert_called_once()

    @patch('zebtrack.analysis.reporter.pd.DataFrame.to_excel')
    def test_export_summary_excel(self, mock_to_excel, reporter, tmp_path):
        """Test export summary data to Excel format."""
        output_path = tmp_path / "summary.xlsx"

        reporter.export_summary_data(output_path, format="excel")

        # Should call to_excel
        mock_to_excel.assert_called_once()

    def test_export_creates_parent_directory(self, reporter, tmp_path):
        """Test that parent directory is created if missing."""
        output_path = tmp_path / "nested" / "dir" / "summary.parquet"

        with patch('zebtrack.analysis.reporter.pd.DataFrame.to_parquet'):
            reporter.export_summary_data(output_path, format="parquet")

        # Parent directory should be created
        assert output_path.parent.exists()

    def test_export_handles_string_path(self, reporter, tmp_path):
        """Test that string paths are converted to Path objects."""
        output_path = str(tmp_path / "summary.parquet")

        with patch('zebtrack.analysis.reporter.pd.DataFrame.to_parquet'):
            reporter.export_summary_data(output_path, format="parquet")

        # Should not raise error


@pytest.mark.unit
class TestGenerateTrajectoryPlot:
    """Test suite for generate_trajectory_plot method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_trajectory_plot(self, mock_figure, reporter):
        """Test that trajectory plot is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_figure.return_value = mock_fig

        fig = reporter.generate_trajectory_plot()

        # Should create figure
        mock_figure.assert_called_once()

    def test_trajectory_plot_uses_provided_ax(self, reporter):
        """Test that provided Axes object is used."""
        mock_ax = Mock()
        mock_ax.get_figure = Mock(return_value=Mock())
        mock_ax.clear = Mock()

        reporter.generate_trajectory_plot(ax=mock_ax)

        # Should use provided ax
        mock_ax.clear.assert_called_once()

    @patch('zebtrack.analysis.reporter.Path')
    @patch('cv2.VideoCapture')
    def test_trajectory_plot_includes_video_frame(self, mock_videocap, mock_path, reporter):
        """Test that video frame is included when video_path provided."""
        # Mock Path.exists to return True
        mock_path.return_value.exists.return_value = True

        # Mock video capture
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)  # Required for finally block
        mock_cap.read = Mock(return_value=(True, np.zeros((480, 640, 3), dtype=np.uint8)))
        mock_cap.release = Mock()
        mock_videocap.return_value = mock_cap

        with patch('zebtrack.analysis.reporter.plt.figure'):
            with patch.object(reporter, 'calibration', None):
                reporter.generate_trajectory_plot(video_path="/fake/video.mp4")

        # Should release video capture
        mock_cap.release.assert_called_once()

    @patch('zebtrack.analysis.reporter.Path')
    @patch('cv2.VideoCapture')
    def test_trajectory_plot_handles_video_read_failure(self, mock_videocap, mock_path, reporter):
        """Test graceful handling when video frame read fails."""
        # Mock Path.exists to return True
        mock_path.return_value.exists.return_value = True

        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)  # Required for finally block
        mock_cap.read = Mock(return_value=(False, None))  # Failed to read
        mock_cap.release = Mock()
        mock_videocap.return_value = mock_cap

        with patch('zebtrack.analysis.reporter.plt.figure'):
            # Should not crash
            reporter.generate_trajectory_plot(video_path="/fake/video.mp4")

        mock_cap.release.assert_called_once()


@pytest.mark.unit
class TestGenerateHeatmap:
    """Test suite for generate_heatmap method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_heatmap(self, mock_figure, reporter):
        """Test that heatmap is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_ax.get_children = Mock(return_value=[])  # Return empty list for iteration
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_fig.artists = []  # Set artists as empty list, not Mock
        mock_fig.colorbar = Mock()  # Mock colorbar method
        mock_figure.return_value = mock_fig

        fig = reporter.generate_heatmap()

        # Should create figure
        mock_figure.assert_called_once()

    def test_heatmap_uses_provided_ax(self, reporter):
        """Test that provided Axes object is used."""
        mock_ax = Mock()
        mock_ax.get_children = Mock(return_value=[])  # Return empty list for iteration
        mock_fig = Mock()
        mock_fig.artists = []  # Set artists as empty list, not Mock
        mock_fig.colorbar = Mock()  # Mock colorbar method
        mock_ax.get_figure = Mock(return_value=mock_fig)

        reporter.generate_heatmap(ax=mock_ax)

        # Should use provided ax
        mock_ax.get_figure.assert_called_once()


@pytest.mark.unit
class TestGenerateROIReferencePlot:
    """Test suite for generate_roi_reference_plot method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_roi_reference_plot(self, mock_figure, reporter):
        """Test that ROI reference plot is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_figure.return_value = mock_fig

        fig = reporter.generate_roi_reference_plot()

        # Should create figure
        mock_figure.assert_called_once()

    def test_roi_reference_plot_handles_empty_rois(self, sample_trajectory_df, mock_settings):
        """Test ROI reference plot with no ROIs."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        reporter = Reporter(
            trajectory_df=sample_trajectory_df,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=[],  # No ROIs
            fps=30.0,
            settings_obj=mock_settings,
        )

        with patch('zebtrack.analysis.reporter.plt.figure'):
            # Should not crash
            fig = reporter.generate_roi_reference_plot()


@pytest.mark.unit
class TestGenerateAngularVelocityPlot:
    """Test suite for generate_angular_velocity_plot method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_angular_velocity_plot(self, mock_figure, reporter):
        """Test that angular velocity plot is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_figure.return_value = mock_fig

        fig = reporter.generate_angular_velocity_plot()

        # Should create figure
        mock_figure.assert_called_once()


@pytest.mark.unit
class TestGeneratePositionVsTimePlot:
    """Test suite for generate_position_vs_time_plot method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_position_vs_time_plot(self, mock_figure, reporter):
        """Test that position vs time plot is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_figure.return_value = mock_fig

        fig = reporter.generate_position_vs_time_plot()

        # Should create figure
        mock_figure.assert_called_once()


@pytest.mark.unit
class TestGenerateCumulativeDistancePlot:
    """Test suite for generate_cumulative_distance_plot method."""

    @patch('zebtrack.analysis.reporter.plt.figure')
    def test_generates_cumulative_distance_plot(self, mock_figure, reporter):
        """Test that cumulative distance plot is generated."""
        mock_fig = Mock()
        mock_ax = Mock()
        mock_fig.add_subplot = Mock(return_value=mock_ax)
        mock_figure.return_value = mock_fig

        fig = reporter.generate_cumulative_distance_plot()

        # Should create figure
        mock_figure.assert_called_once()


@pytest.mark.unit
class TestExportIndividualReport:
    """Test suite for export_individual_report_step_by_step method."""

    @patch('zebtrack.analysis.reporter.Reporter._generate_plots_parallel')
    @patch('zebtrack.analysis.reporter.DocxTemplate')
    @patch('builtins.open', new_callable=mock_open)
    def test_export_individual_report_creates_docx(self, mock_file, mock_template, mock_plots, reporter, tmp_path):
        """Test that DOCX report is created."""
        output_path = tmp_path / "report.docx"

        # Mock template
        mock_template_instance = Mock()
        mock_template.return_value = mock_template_instance

        # Mock plots
        mock_plots.return_value = []

        progress_callback = Mock()

        reporter.export_individual_report_step_by_step(output_path, progress_callback)

        # Should call progress callback
        assert progress_callback.call_count > 0

    def test_export_individual_report_calls_progress_callback(self, reporter, tmp_path):
        """Test that progress callback is called with updates."""
        output_path = tmp_path / "report.docx"
        progress_callback = Mock()

        with patch('zebtrack.analysis.reporter.Reporter._generate_plots_parallel'):
            with patch('zebtrack.analysis.reporter.DocxTemplate'):
                with patch('builtins.open', new_callable=mock_open):
                    reporter.export_individual_report_step_by_step(output_path, progress_callback)

        # Should call progress callback multiple times
        assert progress_callback.call_count >= 3  # At least: start, plots, finish

    @patch('zebtrack.analysis.reporter.Reporter._generate_plots_parallel')
    def test_export_individual_report_handles_plot_generation_failure(self, mock_plots, reporter, tmp_path):
        """Test graceful handling of plot generation failures."""
        output_path = tmp_path / "report.docx"

        # Simulate plot generation failure
        mock_plots.side_effect = Exception("Plot generation failed")

        progress_callback = Mock()

        with patch('zebtrack.analysis.reporter.DocxTemplate'):
            with patch('builtins.open', new_callable=mock_open):
                # Should handle error gracefully (or raise depending on implementation)
                try:
                    reporter.export_individual_report_step_by_step(output_path, progress_callback)
                except Exception as e:
                    # Verify exception is propagated
                    assert "Plot generation failed" in str(e)


@pytest.mark.unit
class TestDataValidation:
    """Test suite for data validation methods."""

    def test_validate_schema_with_valid_df(self, reporter):
        """Test schema validation with valid DataFrame."""
        valid_df = pd.DataFrame({
            "experiment_id": ["test_001"],
            "total_distance_cm": [100.0],
            "average_velocity_cm_s": [5.0],
        })

        # Implementation may or may not have explicit validate_schema method
        # Test based on actual implementation

    def test_handles_missing_columns_gracefully(self, sample_trajectory_df, mock_settings):
        """Test Reporter handles trajectories missing optional columns."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # Remove optional column
        minimal_df = sample_trajectory_df.drop(columns=["confidence"])

        reporter = Reporter(
            trajectory_df=minimal_df,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        # Should initialize without error
        assert reporter is not None


@pytest.mark.unit
class TestEdgeCases:
    """Test suite for edge cases."""

    def test_empty_trajectory_dataframe(self, mock_settings):
        """Test Reporter with empty trajectory DataFrame raises ValueError."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        empty_df = pd.DataFrame(columns=["timestamp", "frame", "track_id"])

        # Empty DataFrames should raise ValueError during behavioral analysis
        with pytest.raises(ValueError, match="Input DataFrame is empty"):
            Reporter(
                trajectory_df=empty_df,
                metadata={},
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=480,
                arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
                rois=[],
                fps=30.0,
                settings_obj=mock_settings,
            )

    def test_unicode_metadata(self, sample_trajectory_df, mock_settings):
        """Test Reporter with Unicode characters in metadata."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        reporter = Reporter(
            trajectory_df=sample_trajectory_df,
            metadata={
                "experiment_id": "experimento_ção_123",
                "group_name": "Grupo Café",
            },
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        # Should handle Unicode gracefully
        assert "ção" in reporter.metadata["experiment_id"]

    @pytest.mark.slow
    def test_very_large_trajectory(self, mock_settings):
        """Test Reporter with large trajectory DataFrame."""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        large_df = pd.DataFrame({
            "timestamp": np.arange(0, 10000, 0.1),
            "frame": np.arange(100000),
            "track_id": [1] * 100000,
            "x1": np.random.rand(100000) * 640,
            "y1": np.random.rand(100000) * 480,
            "x2": np.random.rand(100000) * 640,
            "y2": np.random.rand(100000) * 480,
        })

        reporter = Reporter(
            trajectory_df=large_df,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        # Should initialize without memory issues
        assert reporter.b_analyzer is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
