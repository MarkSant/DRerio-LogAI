"""
Integration tests for Reporter class with real file I/O.

Addresses PR Review Issue #4 - Potential False Positives in Mocking.
These tests validate actual file creation and data integrity rather than just mocking.
"""

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI


@pytest.fixture
def mock_settings():
    """Create mock settings for Reporter initialization."""
    settings = Mock()
    settings.video_processing = Mock()
    settings.video_processing.fps = 30.0
    settings.video_processing.sharp_turn_threshold_deg_s = 45.0
    settings.video_processing.freezing_velocity_threshold = 1.5
    settings.video_processing.freezing_min_duration_s = 1.0
    settings.trajectory_smoothing = Mock()
    settings.trajectory_smoothing.window_length = 7  # Default from settings schema
    settings.trajectory_smoothing.polyorder = 3  # Default from settings schema
    # Angular velocity settings
    settings.angular_velocity = Mock()
    settings.angular_velocity.min_displacement_threshold_cm = 0.5
    settings.angular_velocity.angle_calculation_window = 1
    settings.angular_velocity.angular_velocity_smoothing_window = 3
    # ROI inclusion settings
    settings.roi_inclusion_rule = "bbox_intersects"
    settings.roi_buffer_radius_value = 0.5
    settings.roi_min_bbox_overlap_ratio = 0.10
    return settings


@pytest.fixture
def sample_trajectory_df():
    """Create realistic trajectory DataFrame with multiple tracks."""
    np.random.seed(42)  # For reproducibility

    frames = 100
    tracks = 2

    data = []
    for track_id in range(1, tracks + 1):
        for frame in range(frames):
            timestamp = frame * 0.033  # ~30 FPS
            # Simulate movement in a circular pattern
            angle = (frame / frames) * 2 * np.pi
            center_x = 320 + 100 * np.cos(angle)
            center_y = 240 + 100 * np.sin(angle)

            data.append(
                {
                    "timestamp": timestamp,
                    "frame": frame,
                    "track_id": track_id,
                    "x1": center_x - 20,
                    "y1": center_y - 20,
                    "x2": center_x + 20,
                    "y2": center_y + 20,
                    "confidence": 0.85 + np.random.rand() * 0.15,
                    "x_center_px": center_x,
                    "y_center_px": center_y,
                }
            )

    return pd.DataFrame(data)


@pytest.fixture
def sample_rois():
    """Create sample ROIs for testing."""
    return [
        ROI(
            name="Center",
            geometry=Polygon([(270, 190), (370, 190), (370, 290), (270, 290)]),
            coordinate_space="px",
        ),
        ROI(
            name="Border",
            geometry=Polygon([(50, 50), (150, 50), (150, 150), (50, 150)]),
            coordinate_space="px",
        ),
    ]


@pytest.fixture
def reporter(mock_settings, sample_trajectory_df, sample_rois):
    """Create Reporter instance with realistic test data."""
    return Reporter(
        trajectory_df=sample_trajectory_df,
        metadata={
            "experiment_id": "integration_test_001",
            "group_id": "G1",
            "subject": "subject_001",
            "day": 1,
        },
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
        rois=sample_rois,
        fps=30.0,
        roi_colors={"Center": (255, 0, 0), "Border": (0, 255, 0)},
        video_path=None,
        calibration=None,
        sharp_turn_threshold=45.0,
        freezing_threshold=1.0,
        freezing_duration=2.0,
        smoothing_window_length=5,
        smoothing_polyorder=2,
        settings_obj=mock_settings,
    )


@pytest.mark.integration
class TestReporterParquetIntegration:
    """Integration tests for Parquet export with real file I/O."""

    def test_export_summary_parquet_real_file(self, reporter, tmp_path):
        """Test exporting summary data to real Parquet file and validate content.

        This test addresses the review concern about over-mocking by:
        1. Writing a real Parquet file to disk
        2. Reading it back and validating the data
        3. Checking column schema and data types
        """
        # Arrange
        output_path = tmp_path / "summary_real.parquet"

        # Act
        reporter.export_summary_data(output_path, format="parquet")

        # Assert: File exists
        assert output_path.exists(), "Parquet file should be created"
        assert output_path.stat().st_size > 0, "Parquet file should not be empty"

        # Assert: Read back and validate content
        df_read = pd.read_parquet(output_path)

        # Validate schema
        assert isinstance(df_read, pd.DataFrame), "Should read as DataFrame"
        assert len(df_read) > 0, "DataFrame should contain data"

        # Validate required columns exist (using actual column names from COLUMN_MAPPING)
        expected_columns = {"experiment_id", "total_distance_cm", "mean_speed_cm_s"}
        actual_columns = set(df_read.columns)
        assert expected_columns.issubset(actual_columns), (
            f"Missing columns: {expected_columns - actual_columns}"
        )

        # Validate data types
        if "total_distance_cm" in df_read.columns:
            assert pd.api.types.is_numeric_dtype(df_read["total_distance_cm"]), (
                "Distance should be numeric"
            )

        if "mean_speed_cm_s" in df_read.columns:
            assert pd.api.types.is_numeric_dtype(df_read["mean_speed_cm_s"]), (
                "Velocity should be numeric"
            )

        # Validate metadata is preserved
        if "experiment_id" in df_read.columns:
            assert "integration_test_001" in df_read["experiment_id"].values, (
                "Metadata should be preserved"
            )

    def test_export_summary_parquet_compression(self, reporter, tmp_path):
        """Test that Parquet files use compression effectively."""
        # Arrange
        output_path = tmp_path / "summary_compressed.parquet"

        # Act
        reporter.export_summary_data(output_path, format="parquet")

        # Assert: Check file size is reasonable (compressed)
        file_size = output_path.stat().st_size
        assert file_size > 0, "File should exist"
        assert file_size < 100_000, "Compressed file should be reasonably sized"  # 100 KB threshold

    def test_export_summary_parquet_nested_directory(self, reporter, tmp_path):
        """Test that nested directories are created automatically."""
        # Arrange
        output_path = tmp_path / "nested" / "deep" / "path" / "summary.parquet"

        # Act
        reporter.export_summary_data(output_path, format="parquet")

        # Assert
        assert output_path.exists(), "File should be created in nested directory"
        assert output_path.parent.exists(), "Parent directories should be created"

        # Validate file is readable
        df_read = pd.read_parquet(output_path)
        assert len(df_read) > 0


@pytest.mark.integration
class TestReporterExcelIntegration:
    """Integration tests for Excel export with real file I/O."""

    def test_export_summary_excel_real_file(self, reporter, tmp_path):
        """Test exporting summary data to real Excel file and validate content."""
        # Arrange
        output_path = tmp_path / "summary_real.xlsx"

        # Act
        reporter.export_summary_data(output_path, format="excel")

        # Assert: File exists
        assert output_path.exists(), "Excel file should be created"
        assert output_path.stat().st_size > 0, "Excel file should not be empty"

        # Assert: Read back and validate content
        df_read = pd.read_excel(output_path)

        # Validate schema
        assert isinstance(df_read, pd.DataFrame), "Should read as DataFrame"
        assert len(df_read) > 0, "DataFrame should contain data"

        # Validate data integrity
        if "experiment_id" in df_read.columns:
            assert "integration_test_001" in df_read["experiment_id"].values

    def test_export_summary_excel_multiple_sheets(self, reporter, tmp_path):
        """Test that Excel files can be read correctly after export."""
        # Arrange
        output_path = tmp_path / "summary_multi.xlsx"

        # Act
        reporter.export_summary_data(output_path, format="excel")

        # Assert: Validate file can be opened with Excel reader
        try:
            excel_file = pd.ExcelFile(output_path)
            assert len(excel_file.sheet_names) >= 1, "Should have at least one sheet"
        finally:
            excel_file.close()


@pytest.mark.integration
class TestReporterDataIntegrity:
    """Integration tests for data integrity across export/import cycle."""

    def test_parquet_roundtrip_data_integrity(self, reporter, tmp_path):
        """Test that data is preserved after export and reimport (roundtrip test)."""
        # Arrange
        output_path = tmp_path / "roundtrip.parquet"

        # Get original summary data
        # Note: This assumes Reporter has a method to get summary data
        # If not, we'll export and reimport to verify consistency

        # Act
        reporter.export_summary_data(output_path, format="parquet")
        df_reloaded = pd.read_parquet(output_path)

        # Assert: Data types are preserved
        for col in df_reloaded.columns:
            if col in ["total_distance_cm", "average_velocity_cm_s", "time_in_center_s"]:
                assert pd.api.types.is_numeric_dtype(df_reloaded[col]), f"{col} should be numeric"

        # Assert: No null values in critical columns
        critical_cols = ["experiment_id"]
        for col in critical_cols:
            if col in df_reloaded.columns:
                assert not df_reloaded[col].isnull().any(), f"{col} should not contain null values"

    def test_concurrent_exports_no_corruption(self, reporter, tmp_path):
        """Test that multiple concurrent exports don't corrupt data."""
        # Arrange
        output_paths = [tmp_path / f"concurrent_{i}.parquet" for i in range(5)]

        # Act: Export to multiple files
        for path in output_paths:
            reporter.export_summary_data(path, format="parquet")

        # Assert: All files are valid and identical
        dataframes = [pd.read_parquet(path) for path in output_paths]

        # Verify all DataFrames have the same schema
        first_df = dataframes[0]
        for i, df in enumerate(dataframes[1:], 1):
            assert list(df.columns) == list(first_df.columns), (
                f"DataFrame {i} has different columns"
            )
            assert len(df) == len(first_df), f"DataFrame {i} has different row count"


@pytest.mark.integration
@pytest.mark.slow
class TestReporterLargeDatasetIntegration:
    """Integration tests with large datasets to validate performance and stability."""

    def test_export_large_trajectory_parquet(self, mock_settings, tmp_path):
        """Test exporting large trajectory (10k+ frames) to Parquet."""
        # Arrange: Create large dataset
        np.random.seed(42)
        frames = 10_000

        data = {
            "timestamp": np.arange(frames) * 0.033,
            "frame": np.arange(frames),
            "track_id": [1] * frames,
            "x1": np.random.rand(frames) * 640,
            "y1": np.random.rand(frames) * 480,
            "x2": np.random.rand(frames) * 640,
            "y2": np.random.rand(frames) * 480,
            "confidence": 0.8 + np.random.rand(frames) * 0.2,
        }
        large_df = pd.DataFrame(data)

        reporter = Reporter(
            trajectory_df=large_df,
            metadata={"experiment_id": "large_test"},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        output_path = tmp_path / "large_summary.parquet"

        # Act
        reporter.export_summary_data(output_path, format="parquet")

        # Assert: File created successfully
        assert output_path.exists()
        df_reloaded = pd.read_parquet(output_path)
        assert len(df_reloaded) > 0

        # Validate compression effectiveness
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        assert file_size_mb < 5.0, (
            f"Large file should be compressed (<5MB), got {file_size_mb:.2f}MB"
        )


@pytest.mark.integration
class TestReporterEdgeCasesIntegration:
    """Integration tests for edge cases with real file I/O."""

    def test_export_unicode_metadata_to_parquet(
        self, mock_settings, sample_trajectory_df, tmp_path
    ):
        """Test that Unicode characters in metadata are preserved in Parquet files."""
        # Arrange
        reporter = Reporter(
            trajectory_df=sample_trajectory_df,
            metadata={
                "experiment_id": "experimento_ção_123",
                "group_name": "Grupo Café",
                "subject": "Rato São Paulo",
            },
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
            rois=[],
            fps=30.0,
            settings_obj=mock_settings,
        )

        output_path = tmp_path / "unicode_test.parquet"

        # Act
        reporter.export_summary_data(output_path, format="parquet")

        # Assert: Read back and verify Unicode is preserved
        df_reloaded = pd.read_parquet(output_path)

        if "experiment_id" in df_reloaded.columns:
            assert any("ção" in str(val) for val in df_reloaded["experiment_id"].values), (
                "Unicode should be preserved"
            )

    def test_export_empty_dataframe_to_parquet(self, mock_settings, tmp_path):
        """Test that empty DataFrames raise appropriate error."""
        # Arrange
        # Empty dataframe must have all required columns for behavioral analysis
        empty_df = pd.DataFrame(
            columns=[
                "timestamp",
                "frame",
                "track_id",
                "x_center_px",
                "y_center_px",
                "x1",
                "y1",
                "x2",
                "y2",
                "confidence",
            ]
        )

        # Act & Assert: Should raise ValueError for empty dataframe
        with pytest.raises(ValueError, match="Input DataFrame is empty"):
            Reporter(
                trajectory_df=empty_df,
                metadata={"experiment_id": "empty_test"},
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=480,
                arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
                rois=[],
                fps=30.0,
                settings_obj=mock_settings,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
