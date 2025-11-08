"""Analysis and reporting coordination service for ZebTrack-AI.

Extracted from MainViewModel (Task 2.2: REFACTOR-VIEWMODEL-001).
Handles analysis pipeline orchestration, report generation, and summary generation.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.gui import ApplicationGUI

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.core.calibration import Calibration
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

log = structlog.get_logger()


class AnalysisCoordinator:
    """
    Coordinates analysis and reporting workflows.

    Responsibilities:
    - Report generation from processed videos
    - Parquet summary generation
    - Analysis pipeline orchestration
    - Result aggregation and export

    Phase: Task 2.2 (REFACTOR-VIEWMODEL-001)
    Extracted from: MainViewModel (analysis and reporting methods, ~600 lines)
    """

    def __init__(
        self,
        root,
        view: ApplicationGUI,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        video_processing_service: VideoProcessingService,
    ):
        """Initialize AnalysisCoordinator with dependency injection.

        Args:
            root: Tkinter root window
            view: Application GUI instance
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            analysis_service: Analysis service
            video_processing_service: Video processing service
        """
        self.root = root
        self.view = view
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.video_processing_service = video_processing_service

        # Callback for refreshing project views (set by MainViewModel)
        self._refresh_project_views_callback = None

    # =============================================================================
    # REPORT GENERATION
    # =============================================================================

    def generate_report(self, videos: list[dict], report_type: str = "unified") -> None:
        """Generate aggregated report from processed videos.

        Loads summary parquet files from each video, aggregates them,
        and exports to Excel/CSV/Parquet format with optional Word report.

        Args:
            videos: List of video info dicts with paths and metadata
            report_type: Type of report (e.g., "unified", "individual")
        """
        log.info("analysis_coordinator.generate_report.start", count=len(videos), type=report_type)

        if not videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {"title": "Nenhum Vídeo", "message": "Nenhum vídeo selecionado para o relatório."},
            )
            return

        # Load summary data from each video
        all_tidy_data = []
        for video_info in videos:
            video_path = video_info.get("path")
            if not isinstance(video_path, str) or not video_path:
                log.warning(
                    "analysis_coordinator.report.invalid_path",
                    video_info=video_info,
                )
                continue

            experiment_id = os.path.splitext(os.path.basename(video_path))[0]
            metadata_hint = dict(video_info.get("metadata") or {})
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_hint,
            )
            summary_path = results_path / f"{experiment_id}_summary.parquet"

            if summary_path.exists():
                try:
                    df = pd.read_parquet(summary_path)
                    all_tidy_data.append(df)
                except Exception as e:
                    log.warning("analysis_coordinator.report.load_error", path=str(summary_path), error=e)
            else:
                log.warning("analysis_coordinator.report.not_found", path=str(summary_path))

        if not all_tidy_data:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro no Relatório",
                    "message": "Não foi possível encontrar dados de resumo para os vídeos selecionados.",
                },
            )
            return

        # Aggregate all data
        aggregated_df = pd.concat(all_tidy_data, ignore_index=True)

        # Ask user for save location
        save_path = self.view.ask_save_filename(
            title=f"Salvar Relatório {report_type.capitalize()}",
            defaultextension=".xlsx",
            initialfile=f"{report_type}_report.xlsx",
            filetypes=[
                ("Pasta de Trabalho do Excel", "*.xlsx"),
                ("Arquivo CSV", "*.csv"),
                ("Arquivo Parquet", "*.parquet"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not save_path:
            return

        # Export data based on file extension
        file_extension = os.path.splitext(save_path)[1].lower()
        if file_extension == ".xlsx":
            aggregated_df.to_excel(save_path, index=False)
        elif file_extension == ".csv":
            aggregated_df.to_csv(save_path, index=False)
        elif file_extension == ".parquet":
            aggregated_df.to_parquet(save_path, index=False)
        else:
            # Default to Excel if extension is unknown or missing
            if not file_extension:
                save_path += ".xlsx"
            aggregated_df.to_excel(save_path, index=False)

        # Generate visual .docx report (except for parquet)
        if file_extension != ".parquet":
            docx_path = os.path.splitext(save_path)[0] + "_report.docx"
            Reporter.export_project_report(aggregated_df, docx_path)

        # Notify user
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {"title": "Relatório Gerado", "message": f"Relatório salvo em:\n{save_path}"},
            )

        log.info("analysis_coordinator.generate_report.success", path=save_path)

    # =============================================================================
    # PARQUET SUMMARY GENERATION
    # =============================================================================

    def generate_parquet_summaries(self, video_paths: list[str], processing_thread_ref=None) -> None:
        """Regenerate Parquet summary files for selected videos.

        Args:
            video_paths: List of video file paths to generate summaries for
            processing_thread_ref: Reference to processing thread to check if active
        """
        log.info(
            "analysis_coordinator.summaries.generate_requested",
            requested=len(video_paths or []),
        )

        # Check if processing is already running
        if processing_thread_ref and processing_thread_ref.is_alive():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Processamento em andamento",
                    "message": "Aguarde a conclusão do processamento atual antes de gerar os sumários.",
                },
            )
            return

        if not video_paths:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum vídeo selecionado para geração de sumários.",
                },
            )
            return

        if not self.project_manager.project_path:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Projeto ausente",
                    "message": "Abra um projeto antes de gerar sumários parquet.",
                },
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum vídeo cadastrado no projeto atualmente.",
                },
            )
            return

        # Normalize paths and find selected videos
        normalized_targets: set[str] = set()
        raw_lookup: dict[str, str] = {}
        for raw_path in video_paths:
            if not isinstance(raw_path, str) or not raw_path:
                continue
            norm_path = os.path.normpath(raw_path)
            normalized_targets.add(norm_path)
            raw_lookup.setdefault(norm_path, raw_path)

        if not normalized_targets:
            self.view.show_info(
                "Sumários",
                "Nenhum vídeo selecionado para geração de sumários.",
            )
            return

        videos_by_norm = {
            os.path.normpath(video.get("path") or ""): video
            for video in all_videos
            if isinstance(video.get("path"), str) and video.get("path")
        }

        selected_videos = [
            videos_by_norm[norm_path]
            for norm_path in normalized_targets
            if norm_path in videos_by_norm
        ]

        missing_targets = [
            norm_path for norm_path in normalized_targets if norm_path not in videos_by_norm
        ]
        if missing_targets:
            sample = [os.path.basename(raw_lookup[norm]) for norm in list(missing_targets)[:5]]
            if len(missing_targets) > 5:
                sample.append(f"... (+{len(missing_targets) - 5})")
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos fora do projeto",
                    "message": "Alguns itens selecionados não pertencem ao projeto atual:\n"
                    + "\n".join(sample),
                },
            )

        if not selected_videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                },
            )
            return

        # Filter videos with trajectory data
        eligible_videos = [video for video in selected_videos if video.get("has_trajectory")]
        if not eligible_videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum dos vídeos selecionados possui trajetória gerada.",
                },
            )
            return

        # Launch summary generation in worker thread
        log.info(
            "analysis_coordinator.summaries.launching_worker",
            count=len(eligible_videos),
        )

        worker_thread = threading.Thread(
            target=self._generate_parquet_summaries_worker,
            args=(eligible_videos, self.settings),
            daemon=True,
        )
        worker_thread.start()

    # =============================================================================
    # ANALYSIS PIPELINE ORCHESTRATION
    # =============================================================================

    def run_analysis_pipeline(
        self,
        *,
        experiment_id: str,
        video_path: str,
        results_dir: str,
        arena_polygon_px: list | None,
        metadata_context: dict | None,
        single_video_config: dict | None,
        progress_callback,
        analysis_profile: dict | None,
        detector,
        refresh_callback,
    ) -> bool:
        """Run analysis pipeline for a single video.

        Delegates to VideoProcessingService but handles detector injection
        and post-analysis view refresh.

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to video file
            results_dir: Directory for results output
            arena_polygon_px: Arena polygon in pixel coordinates
            metadata_context: Metadata for the video
            single_video_config: Single video configuration
            progress_callback: Callback for progress updates
            analysis_profile: Analysis configuration profile
            detector: Current detector instance
            refresh_callback: Callback to refresh views after analysis

        Returns:
            True if analysis succeeded, False otherwise
        """
        # Inject current detector state into service
        self.video_processing_service.detector = detector

        success = self.video_processing_service._run_analysis_pipeline(
            experiment_id=experiment_id,
            video_path=video_path,
            results_dir=results_dir,
            arena_polygon_px=arena_polygon_px,
            metadata_context=metadata_context,
            single_video_config=single_video_config,
            progress_callback=progress_callback,
            analysis_profile=analysis_profile,
        )

        # After analysis, refresh project views
        if success and refresh_callback:
            refresh_callback(
                reason="processing_progress",
                append_summary=True,
            )

        return success

    # =============================================================================
    # HELPER METHODS (Parquet Summary Generation)
    # =============================================================================

    def set_refresh_callback(self, callback):
        """Set callback for refreshing project views.

        Args:
            callback: Function to call for refreshing project views
        """
        self._refresh_project_views_callback = callback

    def _generate_parquet_summaries_worker(self, target_videos: list[dict], settings_obj) -> None:
        """Worker method to generate parquet summaries for a list of videos.

        Runs in background thread. Separated to reduce complexity in the public API method.

        Args:
            target_videos: List of video dicts to process
            settings_obj: Settings instance
        """
        completed: list[str] = []
        skipped: list[str] = []
        details: list[str] = []
        data_changed = False

        for video in target_videos:
            # Process each video
            state = None
            try:
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                )
            except Exception as exc:  # pragma: no cover - defensive
                state, info_msg, _ppath, changed = "failed", str(exc), None, False

            if state == "completed":
                completed.append(info_msg or "(desconhecido)")
                data_changed = data_changed or bool(changed)
            else:
                skipped.append(info_msg.split(":")[0] if info_msg else "(desconhecido)")
                details.append(f"• {info_msg}")

        if data_changed:
            self.project_manager.save_project()

        def finalize() -> None:
            if completed:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Sumários Gerados",
                        "message": "Sumários parquet atualizados para "
                        f"{len(completed)} vídeo(s).\n"
                        + "\n".join(f"• {item}" for item in completed),
                    },
                )
                status_msg = f"Σ Sumários atualizados: {len(completed)} vídeo(s)."
            else:
                status_msg = "Nenhum sumário foi atualizado."

            if details:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Vídeos ignorados",
                        "message": "Alguns sumários não puderam ser gerados:\n"
                        + "\n".join(details),
                    },
                )

            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": status_msg})

            # Call refresh callback if set
            if self._refresh_project_views_callback:
                self._refresh_project_views_callback(reason=status_msg, append_summary=True)

        self.root.after(0, finalize)

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation.

        Args:
            video: Video dict with path and metadata
            settings_obj: Settings instance

        Returns:
            Tuple of (state, info_msg, parquet_path, data_changed)
        """
        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]
        metadata_hint = dict(video.get("metadata") or {})
        results_path = self.project_manager.resolve_results_directory(
            experiment_id, video_path=path, metadata=metadata_hint
        )
        results_dir = str(results_path)

        # Find trajectory parquet file
        parquet_info = video.get("parquet_files") or {}
        trajectory_path = parquet_info.get("trajectory")
        if trajectory_path and not os.path.exists(trajectory_path):
            trajectory_path = None

        if not trajectory_path:
            candidates = [
                os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet"),
                os.path.join(os.path.dirname(path), f"3_CoordMovimento_{experiment_id}.parquet"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    trajectory_path = candidate
                    break

        if not trajectory_path:
            return (
                "skipped",
                f"{experiment_id}: arquivo de trajetória ausente.",
                None,
                False,
            )

        # Load trajectory data
        try:
            trajectory_df = pd.read_parquet(trajectory_path)
        except Exception as exc:  # pragma: no cover - I/O defensive
            return (
                "skipped",
                f"{experiment_id}: falha ao ler trajetória ({exc}).",
                None,
                False,
            )

        if trajectory_df.empty:
            return (
                "skipped",
                f"{experiment_id}: trajetória vazia, sumário não gerado.",
                None,
                False,
            )

        # Load zone data and calibration
        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)

            arena_polygon_px = list(zone_data.polygon or [])

            # Create default arena if not defined
            if not arena_polygon_px:
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    return (
                        "skipped",
                        f"{experiment_id}: não foi possível abrir o vídeo.",
                        None,
                        False,
                    )
                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                arena_polygon_px = [
                    [0, 0],
                    [frame_width, 0],
                    [frame_width, frame_height],
                    [0, frame_height],
                ]

            # Get calibration data
            calib_data = self.project_manager.project_data.get("calibration", {})
            width_cm = calib_data.get("aquarium_width_cm")
            height_cm = calib_data.get("aquarium_height_cm")
            if not width_cm or not height_cm:
                return "skipped", f"{experiment_id}: calibração incompleta (px/cm).", None, False

            # Create calibration object
            cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
            video_width_px, video_height_px = cal.target_dims_px
            pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
            arena_polygon_warped = cal.transform_points(arena_polygon_px)

            # Load ROIs
            roi_polygons = list(zone_data.roi_polygons or [])
            roi_names = list(zone_data.roi_names or [])
            roi_colors_list = list(zone_data.roi_colors or [])

            rois: list[ROI] = []
            for idx, roi_points in enumerate(roi_polygons):
                warped_points = cal.transform_points(roi_points)
                roi_polygon_px = [(float(x), float(y)) for x, y in warped_points]
                roi_name = roi_names[idx] if idx < len(roi_names) else f"ROI {idx + 1}"
                rois.append(
                    ROI(
                        name=roi_name,
                        geometry=Polygon(roi_polygon_px),
                        coordinate_space="px",
                    )
                )

            roi_colors = {
                (roi_names[i] if i < len(roi_names) else f"ROI {i + 1}"): roi_colors_list[i]
                for i in range(len(roi_colors_list))
            }

            # Get metadata
            metadata = self.project_manager.get_metadata_for_experiment(experiment_id) or {
                "experiment_id": experiment_id,
                "video_name": experiment_id,
            }

            # Create reporter and generate summary
            reporter = Reporter(
                trajectory_df=trajectory_df,
                metadata=metadata,
                pixelcm_x=pixelcm_x,
                pixelcm_y=pixelcm_y,
                video_height_px=video_height_px,
                arena_polygon_px=arena_polygon_warped,
                rois=rois,
                fps=settings_obj.video_processing.fps,
                roi_colors=roi_colors,
                video_path=path,
                calibration=cal,
                sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
                freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
                freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
                smoothing_window_length=settings_obj.trajectory_smoothing.window_length,
                smoothing_polyorder=settings_obj.trajectory_smoothing.polyorder,
            )

            os.makedirs(results_dir, exist_ok=True)
            parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
            reporter.export_summary_data(parquet_path, format="parquet")

            video.setdefault("parquet_files", {})["summary"] = parquet_path
            video["has_complete_data"] = True
            return "completed", experiment_id, parquet_path, True
        except Exception as exc:  # pragma: no cover - defensive
            return "failed", f"{experiment_id}: erro inesperado ({exc}).", None, False
        finally:
            # Reset active zone video
            self.project_manager.set_active_zone_video(None)
