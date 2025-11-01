"""
Compatibility tests for Reporter refactoring (Sprint 5).

Validates that all three construction paths produce equivalent results:
1. Legacy constructor (trajectory_df + params) - DEPRECATED
2. Modern constructor (analysis parameter)
3. Factory method Reporter.from_analysis()

These tests ensure zero breaking changes during the migration period.
"""

import warnings
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.models import AnalysisResult, CalibrationParams
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
    """Create realistic trajectory DataFrame."""
    np.random.seed(42)
    frames = 100
    data = []

    for frame in range(frames):
        timestamp = frame * 0.033  # ~30 FPS
        angle = (frame / frames) * 2 * np.pi
        center_x = 320 + 100 * np.cos(angle)
        center_y = 240 + 100 * np.sin(angle)

        data.append(
            {
                "timestamp": timestamp,
                "frame": frame,
                "track_id": 1,
                "x1": center_x - 20,
                "y1": center_y - 20,
                "x2": center_x + 20,
                "y2": center_y + 20,
                "confidence": 0.95,
                "x_center_px": center_x,
                "y_center_px": center_y,
            }
        )

    return pd.DataFrame(data)


@pytest.fixture
def sample_rois():
    """Create sample ROIs."""
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
def analysis_params(mock_settings):
    """Common analysis parameters."""
    return {
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 480,
        "arena_polygon_px": [(0, 0), (640, 0), (640, 480), (0, 480)],
        "fps": 30.0,
        "metadata": {
            "experiment_id": "compat_test_001",
            "group_id": "G1",
            "subject": "subject_001",
        },
        "roi_colors": {"Center": (255, 0, 0), "Border": (0, 255, 0)},
        "sharp_turn_threshold": 45.0,
        "freezing_threshold": 1.5,
        "freezing_duration": 1.0,
        "smoothing_window_length": 5,
        "smoothing_polyorder": 2,
        "settings_obj": mock_settings,
    }


@pytest.mark.unit
class TestReporterLegacyConstructor:
    """Test legacy Reporter constructor (DEPRECATED but still functional)."""

    def test_legacy_constructor_emits_deprecation_warning(
        self, sample_trajectory_df, sample_rois, analysis_params
    ):
        """Test that legacy constructor emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            Reporter(trajectory_df=sample_trajectory_df, rois=sample_rois, **analysis_params)

            # Verify warning was emitted
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "trajectory_df is DEPRECATED" in str(w[0].message)
            assert "Reporter.from_analysis" in str(w[0].message)
            assert "v3.0" in str(w[0].message)

    def test_legacy_constructor_creates_valid_reporter(
        self, sample_trajectory_df, sample_rois, analysis_params
    ):
        """Test that legacy constructor creates functional Reporter instance."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress deprecation warning

            reporter = Reporter(
                trajectory_df=sample_trajectory_df, rois=sample_rois, **analysis_params
            )

            # Verify reporter is created correctly
            assert reporter is not None
            assert hasattr(reporter, "report")
            assert hasattr(reporter, "b_analyzer")
            assert hasattr(reporter, "r_analyzer")
            assert hasattr(reporter, "tidy_data")

            # Verify tidy data is populated
            assert isinstance(reporter.tidy_data, pd.DataFrame)
            assert len(reporter.tidy_data) > 0

    def test_legacy_constructor_missing_trajectory_raises_error(self):
        """Test that missing trajectory_df raises ValueError."""
        with pytest.raises(
            ValueError, match="Either 'analysis' or 'trajectory_df' must be provided"
        ):
            Reporter()  # No parameters


@pytest.mark.unit
class TestReporterFactoryMethod:
    """Test Reporter.from_analysis() factory method (RECOMMENDED)."""

    def test_factory_method_creates_reporter_from_dto(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test factory method creates Reporter from AnalysisResult DTO."""
        # Arrange: Create AnalysisResult DTO
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        # Act: Create Reporter using factory method
        reporter = Reporter.from_analysis(analysis)

        # Assert: Reporter is valid
        assert reporter is not None
        assert hasattr(reporter, "report")
        assert hasattr(reporter, "b_analyzer")
        assert hasattr(reporter, "r_analyzer")
        assert hasattr(reporter, "tidy_data")
        assert isinstance(reporter.tidy_data, pd.DataFrame)
        assert len(reporter.tidy_data) > 0

    def test_factory_method_no_deprecation_warning(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test that factory method does NOT emit deprecation warning."""
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            Reporter.from_analysis(analysis)

            # No warnings should be emitted
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0


@pytest.mark.unit
class TestReporterModernConstructor:
    """Test modern Reporter constructor using analysis parameter."""

    def test_modern_constructor_accepts_analysis_dto(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test modern constructor accepts AnalysisResult via analysis parameter."""
        # Arrange: Create AnalysisResult DTO
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        # Act: Use modern constructor path
        reporter = Reporter(analysis=analysis)

        # Assert: Reporter is valid
        assert reporter is not None
        assert hasattr(reporter, "report")
        assert isinstance(reporter.tidy_data, pd.DataFrame)

    def test_modern_constructor_no_deprecation_warning(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test that modern constructor does NOT emit deprecation warning."""
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            Reporter(analysis=analysis)

            # No deprecation warnings
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0


@pytest.mark.unit
class TestReporterEquivalence:
    """Test that all construction paths produce equivalent results."""

    def test_all_paths_produce_same_tidy_data_structure(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test all paths produce DataFrames with same columns."""
        # Path 1: Legacy constructor
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reporter_legacy = Reporter(
                trajectory_df=sample_trajectory_df.copy(), rois=sample_rois, **analysis_params
            )

        # Path 2: Modern constructor
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df.copy(),
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )
        reporter_modern = Reporter(analysis=analysis)

        # Path 3: Factory method
        reporter_factory = Reporter.from_analysis(analysis)

        # Verify all have same tidy data structure
        assert set(reporter_legacy.tidy_data.columns) == set(reporter_modern.tidy_data.columns)
        assert set(reporter_legacy.tidy_data.columns) == set(reporter_factory.tidy_data.columns)
        assert len(reporter_legacy.tidy_data) == len(reporter_modern.tidy_data)
        assert len(reporter_legacy.tidy_data) == len(reporter_factory.tidy_data)

    def test_all_paths_have_same_report_keys(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test all paths produce reports with same top-level keys."""
        # Legacy path
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reporter_legacy = Reporter(
                trajectory_df=sample_trajectory_df.copy(), rois=sample_rois, **analysis_params
            )

        # Modern paths
        service = AnalysisService(settings_obj=mock_settings)
        analysis = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df.copy(),
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )
        reporter_modern = Reporter(analysis=analysis)

        # Verify report structure is identical
        assert set(reporter_legacy.report.keys()) == set(reporter_modern.report.keys())
        assert "comportamento_geral" in reporter_legacy.report
        assert "analise_roi" in reporter_legacy.report


@pytest.mark.unit
class TestAnalysisServiceDTO:
    """Test AnalysisService.run_full_analysis_as_dto() method."""

    def test_dto_method_returns_analysis_result(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test DTO method returns AnalysisResult instance."""
        service = AnalysisService(settings_obj=mock_settings)

        result = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        assert isinstance(result, AnalysisResult)
        assert result.report is not None
        assert result.behavioral_analyzer is not None
        assert result.roi_analyzer is not None  # ROIs provided
        assert isinstance(result.trajectory_df, pd.DataFrame)
        assert isinstance(result.calibration_params, CalibrationParams)

    def test_dto_contains_all_required_fields(
        self, sample_trajectory_df, sample_rois, analysis_params, mock_settings
    ):
        """Test AnalysisResult DTO contains all required fields."""
        service = AnalysisService(settings_obj=mock_settings)

        result = service.run_full_analysis_as_dto(
            trajectory_df=sample_trajectory_df,
            rois=sample_rois,
            freezing_vel_threshold=analysis_params["freezing_threshold"],
            freezing_min_duration=analysis_params["freezing_duration"],
            **{
                k: v
                for k, v in analysis_params.items()
                if k
                in [
                    "pixelcm_x",
                    "pixelcm_y",
                    "video_height_px",
                    "arena_polygon_px",
                    "fps",
                    "metadata",
                    "roi_colors",
                ]
            },
        )

        # Verify all required fields
        assert hasattr(result, "report")
        assert hasattr(result, "behavioral_analyzer")
        assert hasattr(result, "roi_analyzer")
        assert hasattr(result, "trajectory_df")
        assert hasattr(result, "metadata")
        assert hasattr(result, "calibration_params")
        assert hasattr(result, "rois")
        assert hasattr(result, "roi_colors")

        # Verify calibration params
        assert result.calibration_params.pixelcm_x == 10.0
        assert result.calibration_params.pixelcm_y == 10.0
        assert result.calibration_params.fps == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
