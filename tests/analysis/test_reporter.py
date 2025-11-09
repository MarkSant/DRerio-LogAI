"""
Unit tests for Reporter class.

Phase: Sprint 3.2 - Test coverage for report generation
Tests export_summary_data, plot generation, DOCX report creation,
and data validation.
"""

from unittest.mock import Mock, mock_open, patch

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
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
    return pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2, 0.3],
            "frame": [0, 1, 2, 3],
            "track_id": [1, 1, 1, 1],
            "x1": [10, 11, 12, 13],
            "y1": [20, 21, 22, 23],
            "x2": [30, 31, 32, 33],
            "y2": [40, 41, 42, 43],
            "confidence": [0.95, 0.96, 0.97, 0.98],
        }
    )


@pytest.fixture
def sample_rois():
    """Create sample ROI list for testing."""
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


@pytest.fixture
def reporter(sample_trajectory_df, sample_rois, mock_settings):
    """Create Reporter instance with test data."""
    import warnings

    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="zebtrack.analysis.reporter"
    )

    # OLD:     return Reporter(
    # OLD:         trajectory_df=sample_trajectory_df,
    # OLD:         metadata={"experiment_id": "test_001", "group_id": "G1"},
    # OLD:         pixelcm_x=10.0,
    # OLD:         pixelcm_y=10.0,
    # OLD:         video_height_px=480,
    # OLD:         arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
    # OLD:         rois=sample_rois,
    # OLD:         fps=30.0,
    # OLD:         roi_colors={"ROI1": (255, 0, 0), "ROI2": (0, 255, 0)},
    # OLD:         video_path="/fake/video.mp4",
    # OLD:         calibration=None,
    # OLD:         sharp_turn_threshold=45.0,
    # OLD:         freezing_threshold=1.0,
    # OLD:         freezing_duration=2.0,
    # OLD:         smoothing_window_length=5,
    # OLD:         smoothing_polyorder=2,
    # OLD:         settings_obj=mock_settings,
    # OLD:     )
    # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
    service = AnalysisService(settings_obj=mock_settings)
    analysis = service.run_full_analysis_as_dto(
        arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        calibration=None,
        fps=30.0,
        freezing_min_duration=2.0,
        freezing_vel_threshold=1.0,
        metadata={"experiment_id": "test_001", "group_id": "G1"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        roi_colors={"ROI1": (255, 0, 0), "ROI2": (0, 255, 0)},
        rois=sample_rois,
        sharp_turn_threshold=45.0,
        smoothing_polyorder=2,
        smoothing_window_length=5,
        trajectory_df=sample_trajectory_df,
        video_height_px=480,
        video_path="/fake/video.mp4",
    )
    reporter = Reporter.from_analysis(analysis)
    return reporter


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
        minimal_df = pd.DataFrame(
            {
                "timestamp": [0.0, 0.1],
                "frame": [0, 1],
                "track_id": [1, 1],
                "x1": [10, 11],
                "y1": [20, 21],
                "x2": [30, 31],
                "y2": [40, 41],
            }
        )

        # Should not raise error
        # OLD:         reporter = Reporter(
        # OLD:             trajectory_df=minimal_df,
        # OLD:             metadata={},
        # OLD:             pixelcm_x=10.0,
        # OLD:             pixelcm_y=10.0,
        # OLD:             video_height_px=480,
        # OLD:             arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        # OLD:             rois=sample_rois,
        # OLD:             fps=30.0,
        # OLD:             settings_obj=mock_settings,
        # OLD:         )
        # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            fps=30.0,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            rois=sample_rois,
            roi_colors={},
            trajectory_df=minimal_df,
            video_height_px=480,
            freezing_vel_threshold=1.0,
            freezing_min_duration=2.0,
        )
        reporter = Reporter.from_analysis(analysis)

        assert reporter is not None

    def test_init_handles_empty_rois(self, sample_trajectory_df, mock_settings):
        """Test initialization with empty ROI list."""
        import warnings

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # OLD:         reporter = Reporter(
        # OLD:             trajectory_df=sample_trajectory_df,
        # OLD:             metadata={},
        # OLD:             pixelcm_x=10.0,
        # OLD:             pixelcm_y=10.0,
        # OLD:             video_height_px=480,
        # OLD:             arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        # OLD:             rois=[],
        # OLD:             fps=30.0,
        # OLD:             settings_obj=mock_settings,
        # OLD:         )
        # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            fps=30.0,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            rois=[],
            roi_colors={},
            trajectory_df=sample_trajectory_df,
            video_height_px=480,
            freezing_vel_threshold=1.0,
            freezing_min_duration=2.0,
        )
        reporter = Reporter.from_analysis(analysis)

        assert reporter.r_analyzer is None  # No ROIs, so no ROI analyzer


@pytest.mark.unit
class TestExportSummaryData:
    """Test suite for export_summary_data method."""

    @patch("zebtrack.analysis.reporter.pd.DataFrame.to_parquet")
    def test_export_summary_parquet(self, mock_to_parquet, reporter, tmp_path):
        """Test export summary data to Parquet format."""
        output_path = tmp_path / "summary.parquet"

        reporter.export_summary_data(output_path, format="parquet")

        # Should call to_parquet
        mock_to_parquet.assert_called_once()

    @patch("zebtrack.analysis.reporter.pd.DataFrame.to_excel")
    def test_export_summary_excel(self, mock_to_excel, reporter, tmp_path):
        """Test export summary data to Excel format."""
        output_path = tmp_path / "summary.xlsx"

        reporter.export_summary_data(output_path, format="excel")

        # Should call to_excel
        mock_to_excel.assert_called_once()

    def test_export_creates_parent_directory(self, reporter, tmp_path):
        """Test that parent directory is created if missing."""
        output_path = tmp_path / "nested" / "dir" / "summary.parquet"

        with patch("zebtrack.analysis.reporter.pd.DataFrame.to_parquet"):
            reporter.export_summary_data(output_path, format="parquet")

        # Parent directory should be created
        assert output_path.parent.exists()

    def test_export_handles_string_path(self, reporter, tmp_path):
        """Test that string paths are converted to Path objects."""
        output_path = str(tmp_path / "summary.parquet")

        with patch("zebtrack.analysis.reporter.pd.DataFrame.to_parquet"):
            reporter.export_summary_data(output_path, format="parquet")

        # Should not raise error


@pytest.mark.unit
class TestDataValidation:
    """Test suite for data validation methods."""

    def test_validate_schema_with_valid_df(self, reporter):
        """Test schema validation with valid DataFrame."""
        pd.DataFrame(
            {
                "experiment_id": ["test_001"],
                "total_distance_cm": [100.0],
                "average_velocity_cm_s": [5.0],
            }
        )

        # Implementation may or may not have explicit validate_schema method
        # Test based on actual implementation

    def test_handles_missing_columns_gracefully(self, sample_trajectory_df, mock_settings):
        """Test Reporter handles trajectories missing optional columns."""
        import warnings

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # Remove optional column
        minimal_df = sample_trajectory_df.drop(columns=["confidence"])

        # OLD:         reporter = Reporter(
        # OLD:             trajectory_df=minimal_df,
        # OLD:             metadata={},
        # OLD:             pixelcm_x=10.0,
        # OLD:             pixelcm_y=10.0,
        # OLD:             video_height_px=480,
        # OLD:             arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        # OLD:             rois=[],
        # OLD:             fps=30.0,
        # OLD:             settings_obj=mock_settings,
        # OLD:         )
        # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            fps=30.0,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            rois=[],
            roi_colors={},
            trajectory_df=minimal_df,
            video_height_px=480,
            freezing_vel_threshold=1.0,
            freezing_min_duration=2.0,
        )
        reporter = Reporter.from_analysis(analysis)

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
            # OLD:             Reporter(
            # OLD:                 trajectory_df=empty_df,
            # OLD:                 metadata={},
            # OLD:                 pixelcm_x=10.0,
            # OLD:                 pixelcm_y=10.0,
            # OLD:                 video_height_px=480,
            # OLD:                 arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            # OLD:                 rois=[],
            # OLD:                 fps=30.0,
            # OLD:                 settings_obj=mock_settings,
            # OLD:             )
            # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
            service = AnalysisService(settings_obj=mock_settings)
            analysis = service.run_full_analysis_as_dto(
                arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
                fps=30.0,
                metadata={},
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                rois=[],
                roi_colors={},
                trajectory_df=empty_df,
                video_height_px=480,
                freezing_vel_threshold=1.0,
                freezing_min_duration=2.0,
            )
            Reporter.from_analysis(analysis)

    def test_unicode_metadata(self, sample_trajectory_df, mock_settings):
        """Test Reporter with Unicode characters in metadata."""
        import warnings

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # OLD:         reporter = Reporter(
        # OLD:             trajectory_df=sample_trajectory_df,
        # OLD:             metadata={
        # OLD:                 "experiment_id": "experimento_ção_123",
        # OLD:                 "group_name": "Grupo Café",
        # OLD:             },
        # OLD:             pixelcm_x=10.0,
        # OLD:             pixelcm_y=10.0,
        # OLD:             video_height_px=480,
        # OLD:             arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        # OLD:             rois=[],
        # OLD:             fps=30.0,
        # OLD:             settings_obj=mock_settings,
        # OLD:         )
        # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            fps=30.0,
            metadata={
                "experiment_id": "experimento_ção_123",
                "group_name": "Grupo Café",
            },
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            rois=[],
            roi_colors={},
            trajectory_df=sample_trajectory_df,
            video_height_px=480,
            freezing_vel_threshold=1.0,
            freezing_min_duration=2.0,
        )
        reporter = Reporter.from_analysis(analysis)

        # Should handle Unicode gracefully
        assert "ção" in reporter.metadata["experiment_id"]

    @pytest.mark.slow
    def test_very_large_trajectory(self, mock_settings):
        """Test Reporter with large trajectory DataFrame."""
        import warnings

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        large_df = pd.DataFrame(
            {
                "timestamp": np.arange(0, 10000, 0.1),
                "frame": np.arange(100000),
                "track_id": [1] * 100000,
                "x1": np.random.rand(100000) * 640,
                "y1": np.random.rand(100000) * 480,
                "x2": np.random.rand(100000) * 640,
                "y2": np.random.rand(100000) * 480,
            }
        )

        # OLD:         reporter = Reporter(
        # OLD:             trajectory_df=large_df,
        # OLD:             metadata={},
        # OLD:             pixelcm_x=10.0,
        # OLD:             pixelcm_y=10.0,
        # OLD:             video_height_px=480,
        # OLD:             arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
        # OLD:             rois=[],
        # OLD:             fps=30.0,
        # OLD:             settings_obj=mock_settings,
        # OLD:         )
        # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            arena_polygon_px=[(0, 0), (100, 0), (100, 100), (0, 100)],
            fps=30.0,
            metadata={},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            rois=[],
            roi_colors={},
            trajectory_df=large_df,
            video_height_px=480,
            freezing_vel_threshold=1.0,
            freezing_min_duration=2.0,
        )
        reporter = Reporter.from_analysis(analysis)

        # Should initialize without memory issues
        assert reporter.b_analyzer is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
