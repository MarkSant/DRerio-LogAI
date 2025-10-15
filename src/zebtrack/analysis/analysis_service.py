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
from pathlib import Path
from typing import Any, Callable

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
        arena_polygon_px: list[tuple[float, float]],
        rois: list[ROI],
        fps: float,
        # Analysis-specific parameters
        freezing_vel_threshold: float,
        freezing_min_duration: float,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
    ) -> tuple[dict[str, Any], ConcreteBehavioralAnalyzer, ROIAnalyzer | None]:
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
            "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,
            "freezing_min_duration": settings.video_processing.freezing_min_duration_s,
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
            "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,
            "freezing_min_duration": settings.video_processing.freezing_min_duration_s,
            "smoothing_window_length": settings.trajectory_smoothing.window_length,
            "smoothing_polyorder": settings.trajectory_smoothing.polyorder,
        }

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
        video_path: str,
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
            settings_success = controller.apply_project_settings_to_batch(videos_to_process)
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
                    lambda name=profile_name: controller.view.update_social_summary(
                        profile=name,
                        stats=None,
                        tracks=[],
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
        controller.refresh_project_views()
