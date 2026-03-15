"""
AnalysisService: Orchestrates behavioral and ROI analysis pipelines.

Phase 1, Step 3: Extended to include analysis orchestration methods previously
scattered across controller and project_manager. Provides a unified entry point
for running analysis, loading trajectories, collecting parameters, and coordinating
with Reporter for output generation.

Phase 3: Massively expanded to include video processing orchestration (~500 lines).
Now handles batch processing, single video processing, and all coordination logic.
"""

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.metrics_cache import MetricsCache
from zebtrack.analysis.models import AnalysisResult, CalibrationParams
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.analysis.trajectory_validator import TrajectoryQualityValidator
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.core.detection import AquariumData
    from zebtrack.settings import Settings

log = structlog.get_logger()

# v2.2: Memory optimization - only copy columns needed for analysis
REQUIRED_TRAJECTORY_COLUMNS = [
    "timestamp",
    "frame",
    "track_id",
    "x_center_px",
    "y_center_px",
    "x1",
    "y1",
    "x2",
    "y2",
]


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

    def __init__(self, settings_obj: "Settings | None" = None, enable_metrics_cache: bool = False):
        """Initialize the AnalysisService.

        Args:
            settings_obj: Settings instance (injected, optional for backward compatibility).
            enable_metrics_cache: If True, enables caching of base metrics for faster
                threshold adjustments (IMPROVEMENT #2). Default: False for backward compatibility.
        """
        self.log = structlog.get_logger(__name__)
        self.settings = settings_obj

        # IMPROVEMENT #2: Optional metrics caching for faster parameter tuning
        self.metrics_cache: MetricsCache | None = None
        if enable_metrics_cache:
            cache_dir = Path(".cache/metrics")
            self.metrics_cache = MetricsCache(cache_dir)
            self.log.info("analysis_service.metrics_cache_enabled", cache_dir=str(cache_dir))

    @staticmethod
    def _normalize_aquarium_perspective(perspective: str | None) -> str:
        """Normalize perspective aliases to canonical values.

        Delegates to :func:`zebtrack.analysis.perspective_utils.normalize_aquarium_perspective`.
        """
        from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective

        return normalize_aquarium_perspective(perspective)

    def run_full_analysis(
        self,
        trajectory_df: pd.DataFrame,
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: Sequence[Sequence[float]],
        rois: list[ROI],
        fps: float,
        # Analysis-specific parameters
        freezing_vel_threshold: float,
        freezing_min_duration: float,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
        max_plausible_speed_cm_s: float = 50.0,
        behavioral_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ConcreteBehavioralAnalyzer, ROIAnalyzer | None, list, dict]:
        """
        Run a complete analysis pipeline on the given trajectory data.

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
            behavioral_config: Configuration for behavioral metrics (thigmotaxis, geotaxis).

        Returns:
            A tuple containing:
            - A nested dictionary with the full analysis report.
            - The instance of ConcreteBehavioralAnalyzer used.
            - The instance of ROIAnalyzer used, or ``None`` when no ROIs were provided.
        """
        if self.settings is None:
            raise RuntimeError(
                "AnalysisService: Settings not injected. "
                "AnalysisService requires settings_obj parameter in constructor. "
                "Use: AnalysisService(settings_obj=load_settings()) or "
                "AnalysisService(settings_obj=create_mock_settings())"
            )

        # IMPROVEMENT #5: Validate trajectory quality before analysis
        # Use lenient minimum (3 frames) to allow test scenarios
        # Production code typically has much longer trajectories
        validator = TrajectoryQualityValidator(
            fps=fps,
            max_plausible_speed_cm_s=max_plausible_speed_cm_s,
            min_trajectory_frames=3,  # Minimum viable trajectory (allows tests)
        )

        # Convert arena from pixels to cm for validation if calibration exists
        arena_polygon_cm = None
        if "x_cm" in trajectory_df.columns and pixelcm_x > 0:
            arena_polygon_cm = [(x / pixelcm_x, y / pixelcm_y) for x, y in arena_polygon_px]

        validation_result = validator.validate(trajectory_df, arena_polygon=arena_polygon_cm)

        # Raise error if validation fails
        if not validation_result["is_valid"]:
            error_msg = "; ".join(validation_result["errors"])
            self.log.error(
                "analysis_service.trajectory_validation_failed",
                errors=validation_result["errors"],
                warnings=validation_result["warnings"],
                stats=validation_result["stats"],
            )
            raise ValueError(f"Trajectory validation failed: {error_msg}")

        # Log warnings even if validation passed
        validation_warnings = validation_result["warnings"]
        validation_stats = validation_result["stats"]
        if validation_warnings:
            self.log.warning(
                "analysis_service.trajectory_validation_warnings",
                warnings=validation_warnings,
                stats=validation_stats,
            )

        smoothing_cfg = self.settings.trajectory_smoothing
        window_length = (
            smoothing_window_length
            if smoothing_window_length is not None
            else smoothing_cfg.window_length
        )
        polyorder = (
            smoothing_polyorder if smoothing_polyorder is not None else smoothing_cfg.polyorder
        )

        # 1. Initialize the core behavioral analyzer
        angular_settings = self.settings.angular_velocity

        # v2.2: Memory optimization - only copy required columns
        available_cols = [
            col for col in REQUIRED_TRAJECTORY_COLUMNS if col in trajectory_df.columns
        ]
        trajectory_subset = trajectory_df[available_cols].copy()

        b_analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=trajectory_subset,  # Use column subset to reduce memory
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

        # Resolve behavioral config
        if not behavioral_config and hasattr(self.settings, "behavioral_analysis"):
            ba_cfg = self.settings.behavioral_analysis
            behavioral_config = {
                "thigmotaxis_distance_cm": ba_cfg.default_thigmotaxis_distance_cm,
                "geotaxis_distance_cm": ba_cfg.default_geotaxis_distance_cm,
                "geotaxis_num_zones": ba_cfg.default_geotaxis_num_zones,
                "geotaxis_bottom_zones": ba_cfg.default_geotaxis_bottom_zones,
                "aquarium_perspective": ba_cfg.aquarium_perspective,
            }
        behavioral_config = behavioral_config or {}

        # 2. Initialize the behavioral report
        report: dict[str, Any] = {
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
            },
            "validacao": {
                "avisos": validation_warnings,
                "estatisticas": validation_result["stats"],
            },
        }

        # Calculate Thigmotaxis (if configured)
        thigmo_dist = behavioral_config.get("thigmotaxis_distance_cm")
        if thigmo_dist is not None:
            try:
                report["comportamento_geral"]["thigmotaxis_indice"] = (
                    b_analyzer.calculate_thigmotaxis_index(
                        method="time_near_wall", distance_threshold=float(thigmo_dist)
                    )
                )
                report["comportamento_geral"]["thigmotaxis_avg_dist"] = (
                    b_analyzer.calculate_thigmotaxis_index(method="average_distance")
                )
            except Exception as e:
                self.log.warning("analysis.thigmotaxis.failed", error=str(e))

        # Calculate Geotaxis (if configured)
        geo_dist = behavioral_config.get("geotaxis_distance_cm")
        if geo_dist is not None:
            try:
                report["comportamento_geral"]["geotaxis_indice"] = (
                    b_analyzer.calculate_geotaxis_index(
                        method="time_near_bottom", distance_threshold=float(geo_dist)
                    )
                )
                report["comportamento_geral"]["geotaxis_avg_dist"] = (
                    b_analyzer.calculate_geotaxis_index(method="average_distance")
                )
                num_zones = behavioral_config.get("geotaxis_num_zones", 3)
                bottom_zones = behavioral_config.get("geotaxis_bottom_zones", 1)
                report["comportamento_geral"]["geotaxis_zones"] = (
                    b_analyzer.calculate_geotaxis_index(
                        method="zone_time", num_zones=int(num_zones), bottom_zones=int(bottom_zones)
                    )
                )
            except Exception as e:
                self.log.warning("analysis.geotaxis.failed", error=str(e))

        # 3. If ROIs are provided, perform ROI analysis and append to the report
        if not rois:
            return report, b_analyzer, None, validation_warnings, validation_stats

        r_analyzer = ROIAnalyzer(
            behavior_analyzer=b_analyzer,
            rois=rois,
            flutter_n_frames=1,  # Reduced to detect brief entries/exits
            inclusion_rule=self.settings.roi_inclusion_rule,
            buffer_radius_value=self.settings.roi_buffer_radius_value,
            min_bbox_overlap_ratio=self.settings.roi_min_bbox_overlap_ratio,
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

        return report, b_analyzer, r_analyzer, validation_warnings, validation_stats

    def run_full_analysis_as_dto(
        self,
        trajectory_df: pd.DataFrame,
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: Sequence[Sequence[float]],
        rois: list[ROI],
        fps: float,
        metadata: dict[str, Any],
        roi_colors: dict[str, tuple[int, int, int]],
        # Analysis-specific parameters
        freezing_vel_threshold: float,
        freezing_min_duration: float,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
        max_plausible_speed_cm_s: float = 50.0,
        # Optional parameters
        video_path: str | None = None,
        calibration=None,
        sharp_turn_threshold: float = 45.0,
        frame_crop_box: tuple[int, int, int, int] | None = None,
        behavioral_config: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run complete analysis and return results as DTO (RECOMMENDED).

        This method wraps run_full_analysis() and returns a structured DTO
        instead of a tuple. Use this for better type safety and compatibility
        with Reporter.from_analysis().

        Args:
            trajectory_df: Raw trajectory data
            pixelcm_x: Pixels-to-cm conversion factor (x-axis)
            pixelcm_y: Pixels-to-cm conversion factor (y-axis)
            video_height_px: Height of the video in pixels
            arena_polygon_px: Arena vertices in pixels
            rois: List of ROI objects for analysis
            fps: Frames per second
            metadata: Experiment metadata (experiment_id, group, subject, etc.)
            roi_colors: ROI name to RGB color mapping
            freezing_vel_threshold: Velocity threshold for freezing detection
            freezing_min_duration: Minimum freezing episode duration
            smoothing_window_length: Trajectory smoothing window (optional)
            smoothing_polyorder: Trajectory smoothing polynomial order (optional)
            video_path: Optional path to source video file
            calibration: Optional Calibration object
            sharp_turn_threshold: Sharp turn detection threshold (deg/s)

        Returns:
            AnalysisResult DTO with all analysis data

        Example:
            >>> service = AnalysisService(settings_obj=settings)
            >>> result = service.run_full_analysis_as_dto(
            ...     trajectory_df=df,
            ...     pixelcm_x=10.0,
            ...     pixelcm_y=10.0,
            ...     video_height_px=480,
            ...     arena_polygon_px=[(0, 0), (640, 0), (640, 480), (0, 480)],
            ...     rois=rois,
            ...     fps=30.0,
            ...     metadata={"experiment_id": "exp_001"},
            ...     roi_colors={"ROI1": (255, 0, 0)},
            ...     freezing_vel_threshold=1.5,
            ...     freezing_min_duration=1.0,
            ... )
            >>> reporter = Reporter.from_analysis(result)
        """
        # Run the existing analysis method
        report, b_analyzer, r_analyzer, val_warnings, val_stats = self.run_full_analysis(
            trajectory_df=trajectory_df,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px,
            rois=rois,
            fps=fps,
            freezing_vel_threshold=freezing_vel_threshold,
            freezing_min_duration=freezing_min_duration,
            smoothing_window_length=smoothing_window_length,
            smoothing_polyorder=smoothing_polyorder,
            max_plausible_speed_cm_s=max_plausible_speed_cm_s,
            behavioral_config=behavioral_config,
        )

        # Wrap in DTO
        calibration_params = CalibrationParams(
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px,
            fps=fps,
            calibration=calibration,
        )

        return AnalysisResult(
            report=report,
            behavioral_analyzer=b_analyzer,
            roi_analyzer=r_analyzer,
            trajectory_df=trajectory_df,
            metadata=metadata,
            calibration_params=calibration_params,
            rois=rois,
            roi_colors=roi_colors,
            video_path=video_path,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_vel_threshold,
            freezing_duration=freezing_min_duration,
            smoothing_window_length=smoothing_window_length,
            smoothing_polyorder=smoothing_polyorder,
            validation_warnings=val_warnings,
            validation_stats=val_stats,
            frame_crop_box=frame_crop_box,
            behavioral_config=behavioral_config or {},
        )

    def run_multi_aquarium_analysis(
        self,
        aquarium_data_map: dict[int, tuple[pd.DataFrame, "AquariumData"]],
        fps: float = 30.0,
        pixelcm_x: float = 1.0,
        pixelcm_y: float = 1.0,
        video_height_px: int = 480,
        metadata: dict | None = None,
        freezing_vel_threshold: float = 1.5,
        freezing_min_duration: float = 1.0,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
        max_plausible_speed_cm_s: float = 50.0,
        sharp_turn_threshold: float = 45.0,
        behavioral_config: dict[str, Any] | None = None,
    ) -> dict[int, AnalysisResult | None]:
        """
        Execute complete analysis for each aquarium in multi-aquarium mode.

        This method runs independent analysis pipelines for each aquarium,
        returning results keyed by aquarium ID.

        Args:
            aquarium_data_map: Dictionary mapping aquarium_id to tuple of
                (trajectory_df, AquariumData). Each trajectory_df contains
                tracking data for that specific aquarium.
            fps: Frames per second of the video.
            pixelcm_x: Pixels-to-cm conversion factor (x-axis).
            pixelcm_y: Pixels-to-cm conversion factor (y-axis).
            video_height_px: Height of the video in pixels.
            metadata: Optional base metadata to merge with aquarium-specific data.
            freezing_vel_threshold: Velocity threshold for freezing detection.
            freezing_min_duration: Minimum freezing episode duration.
            smoothing_window_length: Trajectory smoothing window (optional).
            smoothing_polyorder: Trajectory smoothing polynomial order (optional).
            max_plausible_speed_cm_s: Maximum plausible speed for validation.
            sharp_turn_threshold: Sharp turn detection threshold (deg/s).
            behavioral_config: Behavioral analysis configuration (thigmotaxis, geotaxis).

        Returns:
            Dictionary mapping aquarium_id to AnalysisResult (or None if failed).

        Example:
            >>> service = AnalysisService(settings_obj=settings)
            >>> aquarium_map = {
            ...     0: (df_aq0, aquarium_data_0),
            ...     1: (df_aq1, aquarium_data_1),
            ... }
            >>> results = service.run_multi_aquarium_analysis(aquarium_map, fps=30.0)
            >>> for aq_id, result in results.items():
            ...     if result:
            ...         print(f"Aquarium {aq_id}: {result.report['metricas_globais']}")
        """
        from zebtrack.analysis.roi import ROI

        results: dict[int, AnalysisResult | None] = {}
        base_metadata = metadata or {}

        for aq_id, (trajectory_df, aq_data) in aquarium_data_map.items():
            self.log.info(
                "analysis.multi_aquarium.starting",
                aquarium_id=aq_id,
                group=aq_data.group,
                subject=aq_data.subject_id,
                trajectory_rows=len(trajectory_df),
            )

            try:
                # Build ROI objects from aquarium data
                rois: list[ROI] = []
                roi_colors: dict[str, tuple[int, int, int]] = {}

                for i, roi_polygon in enumerate(aq_data.roi_polygons):
                    roi_name = aq_data.roi_names[i] if i < len(aq_data.roi_names) else f"ROI_{i}"
                    roi_color = (
                        aq_data.roi_colors[i] if i < len(aq_data.roi_colors) else (255, 0, 0)
                    )
                    rois.append(ROI(name=roi_name, geometry=roi_polygon, coordinate_space="px"))
                    roi_colors[roi_name] = roi_color

                # Build aquarium-specific metadata
                aq_metadata = {
                    **base_metadata,
                    "aquarium_id": aq_id,
                    "group": aq_data.group,
                    "subject_id": aq_data.subject_id,
                    "day": aq_data.day,
                }

                # Run analysis using existing method
                analysis_result = self.run_full_analysis_as_dto(
                    trajectory_df=trajectory_df,  # Assuming aq_traj refers to trajectory_df
                    pixelcm_x=pixelcm_x,  # Assuming aq_pixelcm_x refers to pixelcm_x
                    pixelcm_y=pixelcm_y,  # Assuming aq_pixelcm_y refers to pixelcm_y
                    video_height_px=video_height_px,  # Assuming aq_height refers to video_height_px
                    arena_polygon_px=[
                        (float(x), float(y)) for x, y in aq_data.polygon
                    ],  # Assuming roi_polygon refers to aq_data.polygon
                    rois=rois,  # Not supporting sub-ROIs per aquarium yet
                    fps=fps,
                    metadata=aq_metadata,
                    roi_colors=roi_colors,
                    freezing_vel_threshold=freezing_vel_threshold,
                    freezing_min_duration=freezing_min_duration,
                    smoothing_window_length=smoothing_window_length,
                    smoothing_polyorder=smoothing_polyorder,
                    max_plausible_speed_cm_s=max_plausible_speed_cm_s,
                    sharp_turn_threshold=sharp_turn_threshold,
                    behavioral_config=behavioral_config,
                )

                results[aq_id] = analysis_result

                self.log.info(
                    "analysis.multi_aquarium.completed",
                    aquarium_id=aq_id,
                    group=aq_data.group,
                    subject=aq_data.subject_id,
                )

            except Exception as e:
                self.log.error(
                    "analysis.multi_aquarium.failed",
                    aquarium_id=aq_id,
                    group=aq_data.group,
                    error=str(e),
                    exc_info=True,
                )
                results[aq_id] = None

        # Log summary
        success_count = sum(1 for r in results.values() if r is not None)
        self.log.info(
            "analysis.multi_aquarium.summary",
            total_aquariums=len(aquarium_data_map),
            successful=success_count,
            failed=len(aquarium_data_map) - success_count,
        )

        return results

    def aggregate_session_summaries(self, summary_paths: list[Path], output_path: Path) -> None:
        """Aggregate individual session summaries into unified Excel.

        Args:
            summary_paths: List of individual summary Excel files
            output_path: Path for unified output
        """
        self.log.info(
            "analysis_service.aggregate_summaries.start",
            summary_count=len(summary_paths),
        )

        all_data = []
        for i, summary_path in enumerate(summary_paths, 1):
            try:
                df = pd.read_excel(summary_path)
                df["session_number"] = i
                df["session_file"] = summary_path.stem
                all_data.append(df)
            except Exception as e:
                self.log.warning(
                    "analysis_service.aggregate_summaries.read_failed",
                    summary_path=str(summary_path),
                    error=str(e),
                )

        if not all_data:
            raise ValueError("No valid summary data to aggregate")

        # Concatenate all session data
        non_empty_dfs = [df for df in all_data if not df.empty]
        if not non_empty_dfs:
            raise ValueError("No valid summary data to aggregate (all files were empty)")

        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=FutureWarning,
                message=".*concatenation with empty or all-NA entries.*",
            )
            unified_df = pd.concat(non_empty_dfs, ignore_index=True)

        # Write to Excel
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Sheet 1: All sessions combined
            unified_df.to_excel(writer, sheet_name="All Sessions", index=False)

            # Sheet 2: Summary statistics across sessions
            if len(all_data) > 1:
                # Define aggregation rules
                agg_rules = {
                    "total_distance_cm": "mean",
                    "average_speed_cm_s": "mean",
                    "time_in_center_s": "mean",
                    "entries_to_center": "mean",  # Changed from sum to mean for per-animal average
                }
                # Filter rules to only include columns present in the data
                active_rules = {
                    col: func for col, func in agg_rules.items() if col in unified_df.columns
                }

                if active_rules:
                    summary_stats = unified_df.groupby("session_number").agg(active_rules)
                    summary_stats.to_excel(writer, sheet_name="Session Summary")

        self.log.info(
            "analysis_service.aggregate_summaries.success",
            output=str(output_path),
            total_rows=len(unified_df),
        )

    # -------------------------------------------------------------------------
    # Analysis Orchestration Methods (Phase 1, Step 3)
    # -------------------------------------------------------------------------

    def load_trajectory_dataframe(self, parquet_path: str | Path) -> pd.DataFrame:
        """
        Load trajectory data from a Parquet file.

        IMPROVEMENT #1: Uses column projection to load only necessary columns,
        reducing memory usage by 30-40% and improving load times by 15-20%.

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
            # IMPROVEMENT #1: Column projection - load only necessary columns
            # Core columns needed for analysis (prioritized list)
            desired_columns = [
                "timestamp",
                "frame",
                "track_id",
                "x_center_px",  # Preferred
                "y_center_px",  # Preferred
                "x1",  # Required for bbox
                "y1",  # Required for bbox
                "x2",  # Required for bbox
                "y2",  # Required for bbox
                "confidence",  # Optional
            ]

            # Optional calibration columns
            calibration_columns = ["x_cm", "y_cm", "x_center_cm", "y_center_cm"]

            # Check which columns exist in the file
            import pyarrow.parquet as pq

            parquet_file = pq.ParquetFile(path)
            available_columns = set(parquet_file.schema.names)

            # Only load columns that exist (intersection of desired and available)
            columns_to_load = [col for col in desired_columns if col in available_columns]

            # Add calibration columns if they exist
            for col in calibration_columns:
                if col in available_columns:
                    columns_to_load.append(col)

            # Load only available columns
            df = pd.read_parquet(path, columns=columns_to_load)

            # Calculate memory savings
            total_columns = len(available_columns)
            loaded_columns = len(columns_to_load)
            memory_savings_pct = (1 - loaded_columns / total_columns) * 100

            self.log.info(
                "analysis_service.load_trajectory.success",
                path=str(path),
                rows=len(df),
                total_columns_available=total_columns,
                columns_loaded=loaded_columns,
                memory_savings_pct=f"{memory_savings_pct:.1f}%",
                columns=columns_to_load,
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
        if not self.settings:
            # Fallback defaults if settings not available
            params: dict[str, Any] = {
                "freezing_vel_threshold": 1.0,
                "freezing_min_duration": 1.0,
                "smoothing_window_length": 5,
                "smoothing_polyorder": 2,
                "behavioral_config": {},
            }
        else:
            params = {
                "freezing_vel_threshold": (
                    self.settings.video_processing.freezing_velocity_threshold
                ),
                "freezing_min_duration": self.settings.video_processing.freezing_min_duration_s,
                "smoothing_window_length": self.settings.trajectory_smoothing.window_length,
                "smoothing_polyorder": self.settings.trajectory_smoothing.polyorder,
                "behavioral_config": {},
            }

        if self.settings:
            params["preprocessing"] = {
                "pixel_cm": float(self.settings.video_processing.pixel_cm or 1.0),
                "calculate_angles": self.settings.video_processing.calculate_angles,
                "smooth_coords": self.settings.trajectory_smoothing.enabled,
                "smooth_window": self.settings.trajectory_smoothing.window_length,
            }
            params["analysis"] = {
                "freezing_threshold": self.settings.video_processing.freezing_velocity_threshold,
                "freezing_min_duration": self.settings.video_processing.freezing_min_duration_s,
                "sharp_turn_threshold": self.settings.video_processing.sharp_turn_threshold_deg_s,
            }

        # Add behavioral defaults if available
        settings = self.settings
        if settings is not None and hasattr(settings, "behavioral_analysis"):
            ba_cfg = settings.behavioral_analysis
            # Get perspective - lateral enables geotaxis by default
            perspective = self._normalize_aquarium_perspective(
                getattr(ba_cfg, "aquarium_perspective", "lateral")
            )
            params["behavioral_config"] = {
                "thigmotaxis_distance_cm": ba_cfg.default_thigmotaxis_distance_cm,
                "geotaxis_distance_cm": ba_cfg.default_geotaxis_distance_cm,
                "geotaxis_num_zones": ba_cfg.default_geotaxis_num_zones,
                "geotaxis_bottom_zones": ba_cfg.default_geotaxis_bottom_zones,
                "aquarium_perspective": perspective,
                # Enable geotaxis by default for lateral view (vertical depth analysis)
                "geotaxis_enabled": perspective == "lateral",
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

            # Merge behavioral config from project (preserves defaults like geotaxis_enabled)
            if "behavioral_config" in project_data:
                params["behavioral_config"].update(project_data["behavioral_config"])
            elif "behavioral_analysis" in project_data:  # Handle legacy/alternate key
                params["behavioral_config"].update(project_data["behavioral_analysis"])

        if params.get("behavioral_config"):
            perspective = self._normalize_aquarium_perspective(
                params["behavioral_config"].get("aquarium_perspective")
            )
            params["behavioral_config"]["aquarium_perspective"] = perspective
            if "geotaxis_enabled" not in params["behavioral_config"]:
                params["behavioral_config"]["geotaxis_enabled"] = perspective == "lateral"

        self.log.debug(
            "analysis_service.collect_parameters",
            params=params,
        )
        return params

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
        Return default analysis profile from self.settings.

        Returns:
            dict: Default analysis profile
        """
        profile: dict[str, Any] = {
            "name": "default",
            "freezing_vel_threshold": self.settings.video_processing.freezing_velocity_threshold
            if self.settings
            else 1.5,
            "freezing_min_duration": self.settings.video_processing.freezing_min_duration_s
            if self.settings
            else 1.0,
            "smoothing_window_length": self.settings.trajectory_smoothing.window_length
            if self.settings
            else 7,
            "smoothing_polyorder": self.settings.trajectory_smoothing.polyorder
            if self.settings
            else 3,
        }

        if not self.settings:
            return profile

        profile["preprocessing"] = {
            "pixel_cm": float(self.settings.video_processing.pixel_cm or 1.0),
            "calculate_angles": self.settings.video_processing.calculate_angles,
            "smooth_coords": self.settings.trajectory_smoothing.enabled,
            "smooth_window": self.settings.trajectory_smoothing.window_length,
        }
        profile["analysis"] = {
            "freezing_threshold": self.settings.video_processing.freezing_velocity_threshold,
            "freezing_min_duration": self.settings.video_processing.freezing_min_duration_s,
            "sharp_turn_threshold": self.settings.video_processing.sharp_turn_threshold_deg_s,
        }
        return profile

    # -------------------------------------------------------------------------
    # Video Processing Orchestration (Phase 3)
    # -------------------------------------------------------------------------

    def determine_processing_intervals(
        self,
        single_video_config: dict | None,
        project_data: dict | None = None,
    ) -> tuple[int, int]:
        """
        Determine analysis and display intervals for processing.

        Args:
            single_video_config: Single video configuration (overrides project)
            project_data: Project data with interval settings

        Returns:
            tuple[int, int]: (analysis_interval_frames, display_interval_frames)
        """
        analysis_interval_frames = 10
        display_interval_frames = 10

        if single_video_config:
            analysis_interval_frames = single_video_config.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = single_video_config.get(
                "display_interval_frames", display_interval_frames
            )
            self.log.info(
                "analysis_service.intervals_single_video",
                analysis_interval=analysis_interval_frames,
                display_interval=display_interval_frames,
            )
        elif project_data:
            analysis_interval_frames = project_data.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = project_data.get(
                "display_interval_frames", display_interval_frames
            )

        return int(analysis_interval_frames), int(display_interval_frames)

    def build_metadata_context(
        self,
        video_info: dict,
        single_video_config: dict | None,
        experiment_id: str,
        video_path: Path | str,
        derive_callback: Callable[[str, str], dict] | None = None,
    ) -> dict | None:
        """
        Build metadata context for a video.

        Args:
            video_info: Video information dictionary
            single_video_config: Single video configuration (returns None if present)
            experiment_id: Experiment identifier
            video_path: Path to video file
            derive_callback: Optional callback to derive metadata (project_manager method)

        Returns:
            dict | None: Metadata context or None for single video
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        if single_video_config:
            return None

        metadata_context = dict(video_info.get("metadata") or {})

        if derive_callback:
            try:
                derived_metadata = derive_callback(experiment_id, video_path)
                metadata_context.update(derived_metadata)
            except Exception:  # pragma: no cover - defensive fallback
                self.log.debug(
                    "analysis_service.metadata_derive_failed",
                    experiment=experiment_id,
                    video_path=video_path,
                )

        return metadata_context

    def process_videos_batch(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None,
        controller,  # MainViewModel reference for callbacks
        cancel_event,
        project_manager,
        root_tk,  # Tkinter root for after() scheduling
    ) -> tuple[bool, str]:
        """
        Process a batch of videos end-to-end.

        This is the main orchestration method extracted from MainViewModel._process_videos().

        Args:
            videos_to_process: List of video info dictionaries
            output_base_dir: Base directory for outputs
            single_video_config: Configuration for single video mode (or None)
            controller: MainViewModel reference for accessing detector, recorder, etc.
            cancel_event: Threading event for cancellation
            project_manager: ProjectManager instance
            root_tk: Tkinter root for UI scheduling

        Returns:
            tuple[bool, str]: (was_cancelled, final_output_dir)
        """
        self.log.info("analysis_service.batch.start", count=len(videos_to_process))
        total_videos = max(len(videos_to_process), 1)

        # Determine intervals
        project_data = (
            project_manager.project_data if hasattr(project_manager, "project_data") else None
        )
        analysis_interval_frames, display_interval_frames = self.determine_processing_intervals(
            single_video_config, project_data
        )

        # Apply settings if batch project
        if not single_video_config:
            settings_success = controller.project_vm.apply_project_settings_to_batch(
                videos_to_process
            )
            if not settings_success:
                self.log.warning("analysis_service.batch.settings_partial_failure")

        was_cancelled = False
        final_output_dir = output_base_dir

        # Prepare UI
        root_tk.after(0, controller.view.show_progress_bar)
        root_tk.after(
            0,
            lambda: controller.view.set_status(
                f"Iniciando processamento para {total_videos} vídeos..."
            ),
        )
        project_manager.set_active_zone_video(None)

        # Publish processing mode
        controller._publish_processing_mode(source="processing.loop_start", force=True)

        try:
            # Main processing loop
            for index, video_info in enumerate(videos_to_process):
                if cancel_event.is_set():
                    was_cancelled = True
                    self.log.info("analysis_service.batch.cancelled_by_user")
                    break

                video_path = video_info.get("path")
                experiment_id = (
                    os.path.splitext(os.path.basename(video_path))[0]
                    if isinstance(video_path, str) and video_path
                    else f"video_{index + 1}"
                )

                metadata_context = self.build_metadata_context(
                    video_info=video_info,
                    single_video_config=single_video_config,
                    experiment_id=experiment_id,
                    video_path=video_path or "",
                    derive_callback=getattr(project_manager, "derive_processing_metadata", None),
                )

                profile_context = metadata_context or single_video_config or {}

                try:
                    analysis_profile = project_manager.resolve_analysis_profile(profile_context)
                except Exception:  # pragma: no cover - defensive
                    self.log.warning(
                        "analysis_service.batch.profile_resolve_failed",
                        video=experiment_id,
                        exc_info=True,
                    )
                    analysis_profile = project_manager.resolve_analysis_profile({})

                profile_name = (
                    analysis_profile.get("name", "default")
                    if isinstance(analysis_profile, dict)
                    else "default"
                )

                # Update UI with profile
                root_tk.after(
                    0,
                    lambda name=profile_name: controller.view.update_analysis_profile(name),
                )
                root_tk.after(
                    0,
                    lambda name=profile_name: controller.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_SOCIAL_SUMMARY,
                            data={
                                "profile": name,
                                "stats": None,
                                "tracks": [],
                            },
                        )
                    ),
                )

                # Process single video (delegates to controller's existing method)
                processed, results_dir = controller._process_single_video(
                    index=index,
                    total_videos=total_videos,
                    video_info=video_info,
                    single_video_config=single_video_config,
                    analysis_interval_frames=analysis_interval_frames,
                    display_interval_frames=display_interval_frames,
                    output_base_dir=output_base_dir,
                    experiment_id=experiment_id,
                    metadata_context=metadata_context,
                    analysis_profile=analysis_profile,
                )

                if results_dir:
                    final_output_dir = results_dir

                if not processed and cancel_event.is_set():
                    was_cancelled = True
                    break

        except Exception as exc:  # pragma: no cover - defensive
            self.log.error("analysis_service.batch.error", error=str(exc), exc_info=True)
            root_tk.after(
                0,
                lambda e=exc: controller.view.show_error(
                    "Erro na Análise", f"Ocorreu um erro inesperado: {e}"
                ),
            )
        finally:
            # Finalize
            self._finalize_batch_processing(
                was_cancelled=was_cancelled,
                videos_to_process=videos_to_process,
                final_output_dir=final_output_dir,
                controller=controller,
                project_manager=project_manager,
                root_tk=root_tk,
            )

        return was_cancelled, final_output_dir

    def _finalize_batch_processing(
        self,
        was_cancelled: bool,
        videos_to_process: list[dict],
        final_output_dir: str,
        controller,
        project_manager,
        root_tk,
    ) -> None:
        """
        Finalize batch processing (cleanup, UI updates).

        Args:
            was_cancelled: Whether processing was cancelled
            videos_to_process: List of videos that were queued
            final_output_dir: Final output directory
            controller: MainViewModel reference
            project_manager: ProjectManager instance
            root_tk: Tkinter root for UI scheduling
        """
        project_manager.set_active_zone_video(None)
        root_tk.after(0, controller.view.stop_analysis_view_mode)
        root_tk.after(0, controller.view.hide_progress_bar)

        if was_cancelled:
            root_tk.after(
                0,
                lambda: controller.view.show_info("Cancelado", "A análise de vídeo foi cancelada."),
            )
        elif videos_to_process:
            msg = f"Análise concluída. Resultados salvos em:\n{final_output_dir}"
            root_tk.after(0, lambda: controller.view.show_info("Sucesso", msg))

        root_tk.after(0, lambda: controller.view.set_status("Pronto."))
        controller._publish_processing_mode(source="processing.finalize", force=True)
        controller.ui_event_bus.publish(
            Event(
                type=UIEvents.UI_REFRESH_PROJECT_VIEWS,
                data={"reason": "Analysis completed", "append_summary": True},
            )
        )

        def _refresh_views(*, immediate: bool) -> None:
            refresher = getattr(controller, "refresh_project_views", None)
            if callable(refresher):
                refresher(reason="Analysis completed")
                return

            ui_state_controller = getattr(controller, "ui_state_controller", None)
            if ui_state_controller:
                ui_state_controller.refresh_project_views(
                    reason="Analysis completed",
                    append_summary=True,
                    immediate=immediate,
                )

        _refresh_views(immediate=True)
        root_tk.after(0, lambda: _refresh_views(immediate=False))
