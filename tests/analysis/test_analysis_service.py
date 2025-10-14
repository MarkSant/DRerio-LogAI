# -*- coding: utf-8 -*-
"""
Unit tests for AnalysisService.

Phase 2, Step 5: Comprehensive unit tests for analysis orchestration service.
Uses mocking to isolate the service from analyzers and filesystem dependencies.
"""

import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.roi import ROI


class TestAnalysisServiceInitialization(unittest.TestCase):
    """Test suite for AnalysisService initialization."""

    def test_service_initialization(self):
        """Test that service initializes correctly."""
        service = AnalysisService()

        assert service is not None
        assert hasattr(service, "log")


class TestAnalysisServiceFullAnalysis(unittest.TestCase):
    """Test suite for full analysis pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()
        
        # Create minimal trajectory dataframe
        self.trajectory_df = pd.DataFrame({
            "timestamp": [0.0, 0.033, 0.066, 0.099],
            "frame": [0, 1, 2, 3],
            "track_id": [1, 1, 1, 1],
            "x1": [100, 105, 110, 115],
            "y1": [200, 202, 204, 206],
            "x2": [120, 125, 130, 135],
            "y2": [220, 222, 224, 226],
            "confidence": [0.9, 0.9, 0.9, 0.9],
        })
        
        self.pixelcm_x = 10.0
        self.pixelcm_y = 10.0
        self.video_height_px = 480
        self.arena_polygon_px: list[tuple[float, float]] = [
            (0.0, 0.0), (640.0, 0.0), (640.0, 480.0), (0.0, 480.0)
        ]
        self.fps = 30.0
        self.freezing_vel_threshold = 2.0
        self.freezing_min_duration = 0.5

    def test_run_full_analysis_without_rois(self):
        """Test full analysis without ROIs."""
        report, b_analyzer, r_analyzer = self.service.run_full_analysis(
            trajectory_df=self.trajectory_df,
            pixelcm_x=self.pixelcm_x,
            pixelcm_y=self.pixelcm_y,
            video_height_px=self.video_height_px,
            arena_polygon_px=self.arena_polygon_px,
            rois=[],
            fps=self.fps,
            freezing_vel_threshold=self.freezing_vel_threshold,
            freezing_min_duration=self.freezing_min_duration,
        )

        # Verify report structure
        assert "comportamento_geral" in report
        assert "distancia_total_cm" in report["comportamento_geral"]
        assert "estatisticas_velocidade" in report["comportamento_geral"]
        assert "rajadas_velocidade" in report["comportamento_geral"]
        assert "episodios_congelamento" in report["comportamento_geral"]
        assert "tortuosidade" in report["comportamento_geral"]
        assert "periodos_inatividade" in report["comportamento_geral"]
        assert "curvas_acentuadas" in report["comportamento_geral"]

        # ROI analysis should be None
        assert r_analyzer is None
        assert "analise_roi" not in report

        # Behavioral analyzer should be instantiated
        assert b_analyzer is not None

    def test_run_full_analysis_with_rois(self):
        """Test full analysis with ROIs."""
        rois = [
            ROI(
                name="ROI_1",
                geometry=Polygon([(50, 50), (150, 50), (150, 150), (50, 150)]),
                coordinate_space="px",
            )
        ]

        report, b_analyzer, r_analyzer = self.service.run_full_analysis(
            trajectory_df=self.trajectory_df,
            pixelcm_x=self.pixelcm_x,
            pixelcm_y=self.pixelcm_y,
            video_height_px=self.video_height_px,
            arena_polygon_px=self.arena_polygon_px,
            rois=rois,
            fps=self.fps,
            freezing_vel_threshold=self.freezing_vel_threshold,
            freezing_min_duration=self.freezing_min_duration,
        )

        # Verify report includes ROI analysis
        assert "comportamento_geral" in report
        assert "analise_roi" in report
        assert "log_eventos" in report

        # Verify ROI sections
        assert "tempo_gasto_por_roi" in report["analise_roi"]
        assert "latencia_primeira_entrada" in report["analise_roi"]
        assert "contagem_entradas" in report["analise_roi"]
        assert "contagem_saidas" in report["analise_roi"]
        assert "distancia_por_roi" in report["analise_roi"]
        assert "estatisticas_velocidade_por_roi" in report["analise_roi"]
        assert "congelamento_por_roi" in report["analise_roi"]
        assert "transicoes_entre_rois" in report["analise_roi"]

        # Both analyzers should be instantiated
        assert b_analyzer is not None
        assert r_analyzer is not None

    def test_run_full_analysis_with_custom_smoothing(self):
        """Test full analysis with custom smoothing parameters."""
        report, b_analyzer, r_analyzer = self.service.run_full_analysis(
            trajectory_df=self.trajectory_df,
            pixelcm_x=self.pixelcm_x,
            pixelcm_y=self.pixelcm_y,
            video_height_px=self.video_height_px,
            arena_polygon_px=self.arena_polygon_px,
            rois=[],
            fps=self.fps,
            freezing_vel_threshold=self.freezing_vel_threshold,
            freezing_min_duration=self.freezing_min_duration,
            smoothing_window_length=7,
            smoothing_polyorder=2,
        )

        # Should complete successfully with custom params
        assert "comportamento_geral" in report
        assert b_analyzer is not None

    @patch("zebtrack.analysis.analysis_service.settings", None)
    def test_run_full_analysis_settings_not_loaded(self):
        """Test error when settings are not loaded."""
        with pytest.raises(RuntimeError, match="Application settings failed to load"):
            self.service.run_full_analysis(
                trajectory_df=self.trajectory_df,
                pixelcm_x=self.pixelcm_x,
                pixelcm_y=self.pixelcm_y,
                video_height_px=self.video_height_px,
                arena_polygon_px=self.arena_polygon_px,
                rois=[],
                fps=self.fps,
                freezing_vel_threshold=self.freezing_vel_threshold,
                freezing_min_duration=self.freezing_min_duration,
            )


class TestAnalysisServiceTrajectoryLoading(unittest.TestCase):
    """Test suite for trajectory loading operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()
        self.test_dir = Path("temp_test_analysis_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_trajectory_dataframe_success(self):
        """Test successful trajectory loading."""
        parquet_file = self.test_dir / "trajectory.parquet"
        df = pd.DataFrame({
            "timestamp": [0.0, 0.033],
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [100, 105],
            "y1": [200, 202],
            "x2": [120, 125],
            "y2": [220, 222],
            "confidence": [0.9, 0.9],
        })
        df.to_parquet(parquet_file)

        result = self.service.load_trajectory_dataframe(parquet_file)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert "timestamp" in result.columns
        assert "frame" in result.columns

    def test_load_trajectory_dataframe_not_found(self):
        """Test error when trajectory file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            self.service.load_trajectory_dataframe(
                self.test_dir / "nonexistent.parquet"
            )

    def test_load_trajectory_dataframe_invalid_format(self):
        """Test error when trajectory file is invalid."""
        invalid_file = self.test_dir / "invalid.parquet"
        invalid_file.write_text("not a parquet file")

        with pytest.raises(Exception):
            self.service.load_trajectory_dataframe(invalid_file)


class TestAnalysisServiceParameterCollection(unittest.TestCase):
    """Test suite for parameter collection operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()

    def test_collect_analysis_parameters_defaults(self):
        """Test collecting default analysis parameters."""
        params = self.service.collect_analysis_parameters()

        assert "freezing_vel_threshold" in params
        assert "freezing_min_duration" in params
        assert "smoothing_window_length" in params
        assert "smoothing_polyorder" in params

        # Values should come from settings
        assert isinstance(params["freezing_vel_threshold"], (int, float))
        assert isinstance(params["freezing_min_duration"], (int, float))
        assert isinstance(params["smoothing_window_length"], int)
        assert isinstance(params["smoothing_polyorder"], int)

    def test_collect_analysis_parameters_with_project_overrides(self):
        """Test collecting parameters with project overrides."""
        project_data = {
            "analysis_parameters": {
                "freezing_vel_threshold": 1.5,
                "freezing_min_duration": 0.8,
                "smoothing_window_length": 7,
                "smoothing_polyorder": 2,
            }
        }

        params = self.service.collect_analysis_parameters(project_data)

        assert params["freezing_vel_threshold"] == 1.5
        assert params["freezing_min_duration"] == 0.8
        assert params["smoothing_window_length"] == 7
        assert params["smoothing_polyorder"] == 2

    def test_collect_analysis_parameters_partial_overrides(self):
        """Test collecting parameters with partial project overrides."""
        project_data = {
            "analysis_parameters": {
                "freezing_vel_threshold": 3.0,
            }
        }

        params = self.service.collect_analysis_parameters(project_data)

        # Overridden parameter
        assert params["freezing_vel_threshold"] == 3.0

        # Default parameters should still be present
        assert "freezing_min_duration" in params
        assert "smoothing_window_length" in params


class TestAnalysisServiceReportGeneration(unittest.TestCase):
    """Test suite for report generation operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()
        self.test_dir = Path("temp_test_analysis_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch("zebtrack.analysis.reporter.Reporter")
    def test_generate_reports_success(self, mock_reporter_class):
        """Test successful report generation."""
        # Mock Reporter instance
        mock_reporter = MagicMock()
        mock_reporter_class.return_value = mock_reporter
        
        summary_path = self.test_dir / "summary.xlsx"
        report_path = self.test_dir / "report.docx"
        mock_reporter.export_summary_data.return_value = summary_path
        mock_reporter.export_individual_report_step_by_step.return_value = report_path

        report_data = {
            "comportamento_geral": {
                "distancia_total_cm": 100.5,
            }
        }

        result = self.service.generate_reports(
            report_data=report_data,
            output_directory=self.test_dir,
            video_name="test_video.mp4",
            metadata={"group": "control"},
        )

        # Verify Reporter was called
        assert mock_reporter.export_summary_data.called
        assert mock_reporter.export_individual_report_step_by_step.called

        # Verify return values
        assert "summary" in result
        assert "report" in result
        assert result["summary"] == summary_path
        assert result["report"] == report_path

    @patch("zebtrack.analysis.reporter.Reporter")
    def test_generate_reports_partial_success(self, mock_reporter_class):
        """Test report generation with partial success."""
        # Mock Reporter instance
        mock_reporter = MagicMock()
        mock_reporter_class.return_value = mock_reporter
        
        summary_path = self.test_dir / "summary.xlsx"
        mock_reporter.export_summary_data.return_value = summary_path
        mock_reporter.export_individual_report_step_by_step.return_value = None

        report_data = {"comportamento_geral": {}}

        result = self.service.generate_reports(
            report_data=report_data,
            output_directory=self.test_dir,
            video_name="test_video.mp4",
        )

        # Only summary should be in result
        assert "summary" in result
        assert "report" not in result

    @patch("zebtrack.analysis.reporter.Reporter")
    def test_generate_reports_failure(self, mock_reporter_class):
        """Test report generation failure."""
        # Mock Reporter to raise exception
        mock_reporter = MagicMock()
        mock_reporter_class.return_value = mock_reporter
        mock_reporter.export_summary_data.side_effect = Exception("Export failed")

        report_data = {"comportamento_geral": {}}

        with pytest.raises(Exception, match="Export failed"):
            self.service.generate_reports(
                report_data=report_data,
                output_directory=self.test_dir,
                video_name="test_video.mp4",
            )


class TestAnalysisServiceSchemaValidation(unittest.TestCase):
    """Test suite for trajectory schema validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()

    def test_validate_trajectory_schema_valid(self):
        """Test validation with valid schema."""
        df = pd.DataFrame({
            "timestamp": [0.0, 0.033],
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [100, 105],
            "y1": [200, 202],
            "x2": [120, 125],
            "y2": [220, 222],
            "confidence": [0.9, 0.9],
        })

        result = self.service.validate_trajectory_schema(df)

        assert result is True

    def test_validate_trajectory_schema_missing_columns(self):
        """Test validation with missing required columns."""
        df = pd.DataFrame({
            "timestamp": [0.0, 0.033],
            "frame": [0, 1],
            "x1": [100, 105],
            "y1": [200, 202],
            # Missing track_id, x2, y2
        })

        with pytest.raises(ValueError, match="missing required columns"):
            self.service.validate_trajectory_schema(df)

    def test_validate_trajectory_schema_with_optional_columns(self):
        """Test validation with optional calibration columns."""
        df = pd.DataFrame({
            "timestamp": [0.0, 0.033],
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [100, 105],
            "y1": [200, 202],
            "x2": [120, 125],
            "y2": [220, 222],
            "confidence": [0.9, 0.9],
            "x_center_px": [110, 115],
            "y_center_px": [210, 212],
            "x_cm": [11.0, 11.5],
            "y_cm": [21.0, 21.2],
        })

        result = self.service.validate_trajectory_schema(df)

        assert result is True


class TestAnalysisServiceProfileResolution(unittest.TestCase):
    """Test suite for analysis profile resolution."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()

    def test_resolve_analysis_profile_no_profiles(self):
        """Test profile resolution with no configured profiles."""
        result = self.service.resolve_analysis_profile(
            metadata=None,
            project_data=None,
        )

        # Should return default profile
        assert result["name"] == "default"
        assert "freezing_vel_threshold" in result
        assert "freezing_min_duration" in result

    def test_resolve_analysis_profile_no_metadata(self):
        """Test profile resolution with no metadata."""
        project_data = {
            "analysis_profiles": [
                {
                    "name": "profile1",
                    "freezing_vel_threshold": 2.5,
                    "criteria": {"group": "control"},
                }
            ]
        }

        result = self.service.resolve_analysis_profile(
            metadata=None,
            project_data=project_data,
        )

        # Should return first profile as default
        assert result["name"] == "profile1"

    def test_resolve_analysis_profile_matching_metadata(self):
        """Test profile resolution with matching metadata."""
        metadata = {"group": "treated", "day": "day_1"}
        project_data = {
            "analysis_profiles": [
                {
                    "name": "control_profile",
                    "freezing_vel_threshold": 2.0,
                    "criteria": {"group": "control"},
                },
                {
                    "name": "treated_profile",
                    "freezing_vel_threshold": 1.5,
                    "criteria": {"group": "treated"},
                },
            ]
        }

        result = self.service.resolve_analysis_profile(
            metadata=metadata,
            project_data=project_data,
        )

        # Should match treated profile
        assert result["name"] == "treated_profile"
        assert result["freezing_vel_threshold"] == 1.5

    def test_resolve_analysis_profile_partial_criteria_match(self):
        """Test profile resolution with partial criteria match."""
        metadata = {"group": "control", "day": "day_2"}
        project_data = {
            "analysis_profiles": [
                {
                    "name": "specific_profile",
                    "freezing_vel_threshold": 3.0,
                    "criteria": {"group": "control", "day": "day_1"},
                },
                {
                    "name": "general_profile",
                    "freezing_vel_threshold": 2.0,
                    "criteria": {"group": "control"},
                },
            ]
        }

        result = self.service.resolve_analysis_profile(
            metadata=metadata,
            project_data=project_data,
        )

        # Should match general profile (partial match)
        assert result["name"] == "general_profile"
        assert result["freezing_vel_threshold"] == 2.0

    def test_resolve_analysis_profile_no_match(self):
        """Test profile resolution when no profile matches."""
        metadata = {"group": "novel"}
        project_data = {
            "analysis_profiles": [
                {
                    "name": "control_profile",
                    "criteria": {"group": "control"},
                },
                {
                    "name": "treated_profile",
                    "criteria": {"group": "treated"},
                },
            ]
        }

        result = self.service.resolve_analysis_profile(
            metadata=metadata,
            project_data=project_data,
        )

        # Should return first profile as default
        assert result["name"] == "control_profile"


class TestAnalysisServiceIntegration(unittest.TestCase):
    """Integration tests for AnalysisService workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AnalysisService()
        self.test_dir = Path("temp_test_analysis_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_complete_analysis_workflow(self):
        """Test complete analysis workflow from load to report."""
        # Create trajectory file
        parquet_file = self.test_dir / "trajectory.parquet"
        df = pd.DataFrame({
            "timestamp": [0.0, 0.033, 0.066, 0.099, 0.132],
            "frame": [0, 1, 2, 3, 4],
            "track_id": [1, 1, 1, 1, 1],
            "x1": [100, 105, 110, 115, 120],
            "y1": [200, 202, 204, 206, 208],
            "x2": [120, 125, 130, 135, 140],
            "y2": [220, 222, 224, 226, 228],
            "confidence": [0.9, 0.9, 0.9, 0.9, 0.9],
        })
        df.to_parquet(parquet_file)

        # Load trajectory
        trajectory_df = self.service.load_trajectory_dataframe(parquet_file)
        assert len(trajectory_df) == 5

        # Validate schema
        is_valid = self.service.validate_trajectory_schema(trajectory_df)
        assert is_valid is True

        # Collect parameters
        params = self.service.collect_analysis_parameters()
        assert "freezing_vel_threshold" in params

        # Run analysis
        report, b_analyzer, r_analyzer = self.service.run_full_analysis(
            trajectory_df=trajectory_df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0.0, 0.0), (640.0, 0.0), (640.0, 480.0), (0.0, 480.0)],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=params["freezing_vel_threshold"],
            freezing_min_duration=params["freezing_min_duration"],
        )

        assert "comportamento_geral" in report
        assert b_analyzer is not None

    @patch("zebtrack.analysis.reporter.Reporter")
    def test_analysis_with_profile_and_report_generation(self, mock_reporter_class):
        """Test analysis with profile resolution and report generation."""
        # Mock Reporter
        mock_reporter = MagicMock()
        mock_reporter_class.return_value = mock_reporter
        mock_reporter.export_summary_data.return_value = self.test_dir / "summary.xlsx"
        mock_reporter.export_individual_report_step_by_step.return_value = (
            self.test_dir / "report.docx"
        )

        # Setup
        metadata = {"group": "control", "subject": "s01"}
        project_data = {
            "analysis_profiles": [
                {
                    "name": "control_profile",
                    "freezing_vel_threshold": 2.0,
                    "freezing_min_duration": 0.5,
                    "criteria": {"group": "control"},
                }
            ]
        }

        # Resolve profile
        profile = self.service.resolve_analysis_profile(metadata, project_data)
        assert profile["name"] == "control_profile"

        # Create minimal trajectory
        trajectory_df = pd.DataFrame({
            "timestamp": [0.0, 0.033],
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [100, 105],
            "y1": [200, 202],
            "x2": [120, 125],
            "y2": [220, 222],
            "confidence": [0.9, 0.9],
        })

        # Run analysis
        report, _, _ = self.service.run_full_analysis(
            trajectory_df=trajectory_df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=[(0.0, 0.0), (640.0, 0.0), (640.0, 480.0), (0.0, 480.0)],
            rois=[],
            fps=30.0,
            freezing_vel_threshold=profile["freezing_vel_threshold"],
            freezing_min_duration=profile["freezing_min_duration"],
        )

        # Generate reports
        generated_files = self.service.generate_reports(
            report_data=report,
            output_directory=self.test_dir,
            video_name="test_video.mp4",
            metadata=metadata,
        )

        assert "summary" in generated_files
        assert "report" in generated_files


if __name__ == "__main__":
    unittest.main()
