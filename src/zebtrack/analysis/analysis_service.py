# -*- coding: utf-8 -*-
"""
AnalysisService: Orchestrates behavioral and ROI analysis pipelines.

Phase 1, Step 3: Extended to include analysis orchestration methods previously
scattered across controller and project_manager. Provides a unified entry point
for running analysis, loading trajectories, collecting parameters, and coordinating
with Reporter for output generation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import structlog

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.settings import settings

log = structlog.get_logger()


class AnalysisService:
    """
    A unified service layer that orchestrates behavioral and ROI analysis.

    Phase 1, Step 3: Extended to include analysis orchestration responsibilities.

    This service acts as a single entry point for:
    - Running complete analysis pipelines
    - Loading and validating trajectory data
    - Collecting analysis parameters
    - Generating reports via Reporter
    - Coordinating BehavioralAnalyzer and ROIAnalyzer
    """

    def __init__(self):
        """Initialize the AnalysisService."""
        self.log = structlog.get_logger(__name__)

    def run_full_analysis(
        self,
        trajectory_df: pd.DataFrame,
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: List[tuple[float, float]],
        rois: List[ROI],
        fps: float,
        # Analysis-specific parameters
        freezing_vel_threshold: float,
        freezing_min_duration: float,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
    ) -> Tuple[Dict[str, Any], ConcreteBehavioralAnalyzer, Optional[ROIAnalyzer]]:
        """
        Runs a complete analysis pipeline on the given trajectory data.

        This method instantiates the necessary analyzers, runs all relevant
        metric calculations, and compiles them into a single, structured report.

        Returns:
            trajectory_df: Raw trajectory data.
            pixelcm_x: Pixels-to-cm conversion factor for the x-axis.
            pixelcm_y: Pixels-to-cm conversion factor for the y-axis.
            video_height_px: Height of the video in pixels.
            arena_polygon_px: Vertices of the arena in pixels.
            rois: A list of ROI objects for analysis.
            fps: Frames per second of the video.
            freezing_vel_threshold: Velocity threshold for detecting freezing.
            freezing_min_duration: Minimum duration for a freezing episode.

        Returns:
            A tuple containing:
            - A nested dictionary with the full analysis report.
            - The instance of ConcreteBehavioralAnalyzer used.
            - The instance of ROIAnalyzer used, or ``None`` when no ROIs were provided.
        """
        if settings is None:
            raise RuntimeError("Application settings failed to load.")

        smoothing_cfg = settings.trajectory_smoothing
        window_length = (
            smoothing_window_length
            if smoothing_window_length is not None
            else smoothing_cfg.window_length
        )
        polyorder = (
            smoothing_polyorder if smoothing_polyorder is not None else smoothing_cfg.polyorder
        )

        # 1. Initialize the core behavioral analyzer
        angular_settings = settings.angular_velocity
        b_analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=trajectory_df.copy(),  # Use a copy to prevent side effects
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px,
            fps=fps,
            window_length=window_length,
            polyorder=polyorder,
            min_displacement_threshold_cm=angular_settings.min_displacement_threshold_cm,
            angle_calculation_window=angular_settings.angle_calculation_window,
            angular_velocity_smoothing_window=angular_settings.angular_velocity_smoothing_window,
        )

        # 2. Initialize the behavioral report
        report: Dict[str, Any] = {
            "comportamento_geral": {
                "distancia_total_cm": b_analyzer.calculate_total_distance(),
                "estatisticas_velocidade": b_analyzer.get_velocity_stats(),
                "rajadas_velocidade": b_analyzer.calculate_speed_bursts(),
                "episodios_congelamento": b_analyzer.detect_freezing_episodes(
                    vel_threshold=freezing_vel_threshold,
                    min_duration=freezing_min_duration,
                ),
                "tortuosidade": b_analyzer.get_tortuosity(),
                "periodos_inatividade": b_analyzer.calculate_inactivity_periods(),
                "curvas_acentuadas": b_analyzer.calculate_sharp_turns(
                    90.0
                ),  # Assuming 90 as default
            }
        }

        # 3. If ROIs are provided, perform ROI analysis and append to the report
        if not rois:
            return report, b_analyzer, None

        r_analyzer = ROIAnalyzer(
            behavior_analyzer=b_analyzer,
            rois=rois,
            flutter_n_frames=1,  # Reduced to detect brief entries/exits
            inclusion_rule=settings.roi_inclusion_rule,
            buffer_radius_value=settings.roi_buffer_radius_value,
            min_bbox_overlap_ratio=settings.roi_min_bbox_overlap_ratio,
        )
        report["analise_roi"] = {
            "tempo_gasto_por_roi": r_analyzer.get_time_spent_in_rois(),
            "latencia_primeira_entrada": r_analyzer.get_latency_to_first_entry(),
            "contagem_entradas": r_analyzer.get_entry_counts(),
            "contagem_saidas": r_analyzer.get_exit_counts(),
            "distancia_por_roi": r_analyzer.get_distance_in_rois(),
            "estatisticas_velocidade_por_roi": (r_analyzer.get_velocity_stats_in_rois()),
            "congelamento_por_roi": r_analyzer.get_freezing_in_rois(
                vel_threshold=freezing_vel_threshold,
                min_duration=freezing_min_duration,
            ),
            "transicoes_entre_rois": r_analyzer.get_roi_transitions().to_dict("index"),
        }
        report["log_eventos"] = r_analyzer.get_event_log().to_dict("records")

        return report, b_analyzer, r_analyzer

    # -------------------------------------------------------------------------
    # Analysis Orchestration Methods (Phase 1, Step 3)
    # -------------------------------------------------------------------------

    def load_trajectory_dataframe(self, parquet_path: str | Path) -> pd.DataFrame:
        """
        Load trajectory data from a Parquet file.

        Args:
            parquet_path: Path to the trajectory Parquet file

        Returns:
            pd.DataFrame: Trajectory dataframe

        Raises:
            FileNotFoundError: If parquet file doesn't exist
            Exception: If parquet reading fails
        """
        path = Path(parquet_path)

        if not path.exists():
            raise FileNotFoundError(f"Trajectory file not found: {path}")

        try:
            df = pd.read_parquet(path)
            self.log.info(
                "analysis_service.load_trajectory.success",
                path=str(path),
                rows=len(df),
            )
            return df
        except Exception as e:
            self.log.error(
                "analysis_service.load_trajectory.failed",
                path=str(path),
                error=str(e),
            )
            raise

    def collect_analysis_parameters(
        self,
        project_data: dict | None = None,
    ) -> dict:
        """
        Collect analysis parameters from settings and project overrides.

        Args:
            project_data: Optional project data with parameter overrides

        Returns:
            dict: Analysis parameters including thresholds, smoothing, etc.
        """
        # Start with settings defaults
        params = {
            "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,  # noqa: E501
            "freezing_min_duration": settings.video_processing.freezing_min_duration_s,  # noqa: E501
            "smoothing_window_length": settings.trajectory_smoothing.window_length,
            "smoothing_polyorder": settings.trajectory_smoothing.polyorder,
        }

        # Override with project-specific values if available
        if project_data:
            analysis_params = project_data.get("analysis_parameters", {})
            if "freezing_vel_threshold" in analysis_params:
                params["freezing_vel_threshold"] = analysis_params["freezing_vel_threshold"]
            if "freezing_min_duration" in analysis_params:
                params["freezing_min_duration"] = analysis_params["freezing_min_duration"]
            if "smoothing_window_length" in analysis_params:
                params["smoothing_window_length"] = analysis_params["smoothing_window_length"]
            if "smoothing_polyorder" in analysis_params:
                params["smoothing_polyorder"] = analysis_params["smoothing_polyorder"]

        self.log.debug(
            "analysis_service.collect_parameters",
            params=params,
        )
        return params

    def generate_reports(
        self,
        report_data: dict,
        output_directory: str | Path,
        video_name: str,
        metadata: dict | None = None,
    ) -> dict[str, Path]:
        """
        Generate analysis reports using Reporter.

        Args:
            report_data: Analysis report dictionary
            output_directory: Directory to save reports
            video_name: Name of the video being analyzed
            metadata: Optional metadata for report enrichment

        Returns:
            dict[str, Path]: Dictionary mapping report type to file path
        """
        # Lazy import to avoid circular dependency
        from zebtrack.analysis.reporter import Reporter

        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        reporter = Reporter()
        generated_files = {}

        try:
            # Export summary data (Excel/CSV)
            summary_path = reporter.export_summary_data(
                report_data=report_data,
                output_dir=output_dir,
                video_name=video_name,
                metadata=metadata,
            )
            if summary_path:
                generated_files["summary"] = summary_path

            # Export individual report (Word document)
            report_path = reporter.export_individual_report_step_by_step(
                report_data=report_data,
                output_dir=output_dir,
                video_name=video_name,
                metadata=metadata,
            )
            if report_path:
                generated_files["report"] = report_path

            self.log.info(
                "analysis_service.generate_reports.success",
                output_dir=str(output_dir),
                files_generated=len(generated_files),
            )

        except Exception as e:
            self.log.error(
                "analysis_service.generate_reports.failed",
                output_dir=str(output_dir),
                error=str(e),
            )
            raise

        return generated_files

    def validate_trajectory_schema(self, df: pd.DataFrame) -> bool:
        """
        Validate that trajectory dataframe has required columns.

        Args:
            df: Trajectory dataframe to validate

        Returns:
            bool: True if schema is valid

        Raises:
            ValueError: If required columns are missing
        """
        required_columns = {"timestamp", "frame", "track_id", "x1", "y1", "x2", "y2"}
        missing_columns = required_columns - set(df.columns)

        if missing_columns:
            raise ValueError(f"Trajectory dataframe missing required columns: {missing_columns}")

        self.log.debug(
            "analysis_service.validate_schema.success",
            rows=len(df),
            columns=list(df.columns),
        )
        return True

    def resolve_analysis_profile(
        self,
        metadata: dict | None,
        project_data: dict | None = None,
    ) -> dict:
        """
        Resolve analysis profile based on metadata and project configuration.

        Args:
            metadata: Video metadata (group, day, subject)
            project_data: Project configuration with analysis profiles

        Returns:
            dict: Resolved analysis profile with parameters
        """
        if not project_data or "analysis_profiles" not in project_data:
            return self._default_analysis_profile()

        profiles = project_data.get("analysis_profiles", [])

        # Try to match metadata to a profile
        if metadata:
            for profile in profiles:
                if self._profile_matches(profile, metadata):
                    self.log.info(
                        "analysis_service.resolve_profile.matched",
                        profile_name=profile.get("name", "unnamed"),
                    )
                    return profile

        # Return first profile as default, or defaults
        if profiles:
            return profiles[0]
        return self._default_analysis_profile()

    def _profile_matches(self, profile: dict, metadata: dict) -> bool:
        """
        Check if profile matches metadata criteria.

        Args:
            profile: Analysis profile dictionary
            metadata: Metadata dictionary

        Returns:
            bool: True if profile matches
        """
        criteria = profile.get("criteria", {})

        for key, value in criteria.items():
            if key in metadata:
                if metadata[key] != value:
                    return False

        return True

    def _default_analysis_profile(self) -> dict:
        """
        Return default analysis profile from settings.

        Returns:
            dict: Default analysis profile
        """
        return {
            "name": "default",
            "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,  # noqa: E501
            "freezing_min_duration": settings.video_processing.freezing_min_duration_s,  # noqa: E501
            "smoothing_window_length": settings.trajectory_smoothing.window_length,
            "smoothing_polyorder": settings.trajectory_smoothing.polyorder,
        }
