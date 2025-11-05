"""Analysis and reporting coordination service for ZebTrack-AI.

Extracted from MainViewModel (Task 2.2: REFACTOR-VIEWMODEL-001).
Handles analysis pipeline orchestration, report generation, and summary generation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.gui import ApplicationGUI

import pandas as pd
import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
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
        view: ApplicationGUI,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        video_processing_service: VideoProcessingService,
    ):
        """Initialize AnalysisCoordinator with dependency injection.

        Args:
            view: Application GUI instance
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            analysis_service: Analysis service
            video_processing_service: Video processing service
        """
        self.view = view
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.video_processing_service = video_processing_service

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

        # Launch summary generation in worker thread
        # TODO: Implement worker thread for summary generation
        # For now, just log and notify
        log.info(
            "analysis_coordinator.summaries.launching_worker",
            count=len(selected_videos),
        )

        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Gerando sumários para {len(selected_videos)} vídeo(s)..."},
        )

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
