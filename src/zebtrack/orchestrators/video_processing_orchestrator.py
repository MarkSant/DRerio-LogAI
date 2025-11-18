"""Video Processing Orchestrator.

Sprint 24 - Extraction from MainViewModel.
Orchestrates video processing workflows including single video analysis,
project-based processing, and pending video processing.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import structlog

from zebtrack.core.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.core.project_manager import ProjectManager
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.detector import ZoneData
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class VideoProcessingOrchestrator:
    """Orchestrates video processing workflows.

    Extracted from MainViewModel in Sprint 24 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Single video processing workflow
    - Project-based video processing workflow
    - Pending video processing
    - Video selection and validation
    - Processing callbacks and context creation
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation.
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.state_manager = main_view_model.state_manager
        self.ui_coordinator = main_view_model.ui_coordinator
        self.project_manager = main_view_model.project_manager
        self.view = main_view_model.view
        self.ui_event_bus = main_view_model.ui_event_bus
        self.cancel_event = main_view_model.cancel_event
        self.detector = main_view_model.detector
        self.root = main_view_model.root
        self.processing_coordinator = main_view_model.processing_coordinator
        self.video_selection_service = main_view_model.video_selection_service
        self.video_validation_service = main_view_model.video_validation_service
        self.video_classification_service = main_view_model.video_classification_service

    def register_event_handlers(self) -> None:
        """Subscribe to video processing events.

        Phase 2.3: Orchestrators now subscribe directly to their events
        instead of MainViewModel acting as a central dispatcher.
        """
        if not self.ui_event_bus:
            return

        bus = self.ui_event_bus
        log.info("video_processing_orchestrator.register_handlers.start")

        # Video processing events
        bus.subscribe(
            Events.VIDEO_ANALYZE_SINGLE,
            lambda data: self.main_view_model.start_single_video_workflow(
                data.get("video_path"), data.get("config")
            ),
        )
        bus.subscribe(
            Events.VIDEO_START_SINGLE_PROCESSING,
            lambda data: self.start_single_video_processing(
                data.get("video_path"), data.get("config"), data.get("zone_data")
            ),
        )
        bus.subscribe(
            Events.VIDEO_CANCEL_ANALYSIS,
            lambda data: self.main_view_model.cancel_current_analysis(),
        )

        # Project video processing events
        bus.subscribe(
            Events.PROJECT_PROCESS_VIDEOS,
            lambda data: self.process_pending_project_videos(data.get("video_paths")),
        )

        log.info("video_processing_orchestrator.register_handlers.complete", count=4)

    def select_eligible_videos(
        self,
        skip_dialog: bool,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> list[dict] | None:
        """Select eligible videos for processing (either skip dialog or show it).

        Extracted from MainViewModel._select_eligible_videos in Sprint 24.

        Returns list of eligible videos or None if user cancelled.
        """
        eligible_videos: list[dict] = []

        if skip_dialog:
            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)

            if arena_only:
                skipped_names = [
                    os.path.basename(info.get("path", "")) or "(desconhecido)"
                    for info in arena_only[:5]
                ]
                if len(arena_only) > 5:
                    skipped_names.append(f"... (+{len(arena_only) - 5})")
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Processamento",
                        "message": "Alguns vídeos selecionados foram ignorados porque não "
                        "possuem ROIs desenhadas:\n"
                        + "\n".join(f"• {name}" for name in skipped_names),
                    },
                )

            if not eligible_videos:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Processamento",
                            "message": "Nenhum dos vídeos selecionados contém arena e ROIs "
                            "suficientes para gerar trajetórias.",
                        },
                    )
                return None
        else:
            dialog_result = self.view.show_pending_videos_dialog(
                ready_with_trajectory=ready_with_trajectory,
                ready_with_zones=ready_with_zones,
                arena_only=arena_only,
                without_arena=without_arena,
            )

            if not dialog_result or not dialog_result.get("confirmed"):
                log.info("workflow.project_processing.resume_cancelled_by_user")
                return None

            include_arena_only = bool(dialog_result.get("include_arena_only"))

            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)
            if include_arena_only:
                eligible_videos.extend(arena_only)
            elif arena_only:
                log.info(
                    "workflow.project_processing.skip_arena_only",
                    skipped=len(arena_only),
                )

            if not eligible_videos:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo foi selecionado para processamento neste momento.",
                    },
                )
                return None

        return eligible_videos

    def create_processing_context(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ) -> ProcessingContext:
        """Create the processing context with all necessary configuration.

        Extracted from MainViewModel._create_processing_context in Sprint 24.
        """
        return ProcessingContext(
            videos_to_process=videos_to_process,
            output_base_dir=output_base_dir,
            cancel_event=self.cancel_event,
            single_video_config=single_video_config,
            analysis_interval_frames=10,  # Will be updated by worker
            display_interval_frames=10,  # Will be updated by worker
            process_single_video_func=self.main_view_model._process_single_video,
            apply_project_settings_func=self.main_view_model.apply_project_settings_to_batch,
            determine_intervals_func=self.main_view_model._determine_processing_intervals,
            retry_strategy=self.main_view_model.settings.video_processing.batch_retry_strategy,
        )

    def create_processing_callbacks(self, videos_to_process: list[dict]) -> ProcessingCallbacks:
        """Create thread-safe callbacks for the processing worker.

        Extracted from MainViewModel._create_processing_callbacks in Sprint 24.

        All callbacks schedule UI updates via root.after() to ensure thread safety.
        """

        def on_started():
            """Call when processing starts."""
            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.show_progress_bar(self.view)
            self.ui_coordinator.set_status(
                self.view,
                f"Iniciando processamento para {len(videos_to_process)} vídeos...",
            )
            self.project_manager.set_active_zone_video(None)
            self.main_view_model._publish_processing_mode(source="worker.started", force=True)

        def on_progress(fraction: float, message: str, stats: dict | None):
            """Call with progress updates."""
            if self.cancel_event.is_set():
                return

            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.set_status(self.view, message)
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, message
            )

            if stats:
                # Update processing state in StateManager
                self.state_manager.update_processing_state(
                    source="controller.processing_progress",
                    current_frame=stats.get("current_frame", 0),
                    total_frames=stats.get("total_frames", 0),
                )

                self.ui_event_bus.publish_event(Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats})

        def on_frame_processed(frame, detections, processing_info):
            """Call when a frame is ready for display."""
            if frame is not None:
                # Phase 4: Use UICoordinator for frame display
                self.ui_event_bus.publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

            if detections is not None and processing_info:
                self.ui_event_bus.publish_event(
                    Events.UI_UPDATE_DETECTION_OVERLAY,
                    {"detections": detections, "report": processing_info},
                )

        def on_video_completed(index: int, total: int, experiment_id: str, success: bool):
            """Call when a single video completes."""
            log.info(
                "controller.video_completed",
                index=index,
                total=total,
                experiment_id=experiment_id,
                success=success,
            )

        def on_error(error: Exception, context: str):
            """Call when an error occurs."""
            log.error("controller.processing.worker_error", context=context, error=str(error))
            self.root.after(
                0,
                lambda: self.view.show_error("Erro na Análise", f"{context}: {error}"),
            )

        def _on_processing_fatal_error(exc, context, recovery_info):
            log.error(
                "controller.processing.fatal_error",
                context=context,
                error=str(exc),
                affected_videos=len(recovery_info["affected_videos"]),
            )
            self.ui_coordinator.schedule(
                lambda: self.view.show_error(
                    "Erro Crítico de Processamento",
                    f"{context}\n\nErro: {exc}\n\n"
                    f"Vídeos afetados: {len(recovery_info['affected_videos'])}\n"
                    f"Verifique os logs para detalhes.",
                )
            )
            self.state_manager.update_processing_state(
                source="worker.fatal_error", is_processing=False, error=str(exc)
            )
            self.ui_coordinator.set_status(self.view, "Processamento falhou")

        def on_completed(was_cancelled: bool, output_dir: str, summary: dict | None = None):
            """Call when all processing completes."""
            # Phase 4: Use UICoordinator for UI updates
            self.project_manager.set_active_zone_video(None)
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)

            # Update processing state in StateManager
            self.state_manager.update_processing_state(
                source="controller.processing_completed",
                is_processing=False,
                cancel_requested=was_cancelled,
                current_video=None,
            )

            if was_cancelled:
                if self.main_view_model._cancel_feedback_displayed:
                    self.main_view_model._cancel_feedback_displayed = False
                else:
                    self.ui_coordinator.show_info(
                        self.view, "Cancelado", "A análise de vídeo foi cancelada."
                    )
            elif videos_to_process:
                msg = f"Análise concluída. Resultados salvos em:\n{output_dir}"
                self.ui_coordinator.show_info(self.view, "Sucesso", msg)
                self.main_view_model._cancel_feedback_displayed = False
            else:
                self.main_view_model._cancel_feedback_displayed = False

            self.ui_coordinator.set_status(self.view, "Pronto.")
            self.main_view_model._publish_processing_mode(source="worker.completed", force=True)
            self.main_view_model.refresh_project_views()

        return ProcessingCallbacks(
            on_started=on_started,
            on_progress=on_progress,
            on_frame_processed=on_frame_processed,
            on_video_completed=on_video_completed,
            on_error=on_error,
            on_completed=on_completed,
            on_fatal_error=_on_processing_fatal_error,
        )

    def make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
    ):
        """Create a progress callback for a specific video.

        Extracted from MainViewModel._make_progress_callback in Sprint 24.
        """

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"
            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, progress_fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", progress_fraction, step_status
            )
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {
                    "payload": {
                        "index": index,
                        "total": total_videos,
                        "experiment_id": experiment_id,
                        "step": status_message,
                    }
                },
            )

            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats}
                    )

            processing_report = self.main_view_model._publish_processing_mode(
                source="analysis_progress",
                force=False,
            )

            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_DETECTION_OVERLAY,
                        {"detections": detections, "report": processing_report},
                    )

            # Publish frame for display in analysis view
            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_FRAME,
                        {"frame": frame},
                    )

            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

        return progress_callback

    def start_single_video_processing(
        self, video_path: Path | str, config: dict, zone_data: ZoneData
    ):
        """Start the actual processing for a single video after zone setup.

        Extracted from MainViewModel.start_single_video_processing in Sprint 24.

        Sprint 11: Added validation check for processing already active.
        Sprint 13: Simplified using _handle_validation_error().
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=video_path)

        # Sprint 11: Validate processing can start (basic check only)
        # Sprint 13: Use consolidated error handling
        validation_result = self.processing_coordinator.validate_can_start_processing(
            check_project_loaded=False,  # Not required for single video
            check_zones=False,  # Already handled by caller
            check_videos_exist=False,  # Not required for single video
        )

        if not self.main_view_model._handle_validation_error(validation_result):
            return

        self.project_manager.set_active_zone_video(video_path)

        # Register the single video in project_manager for display in UI
        # This allows the video to appear in Main Control and Reports tabs
        video_entry = self.project_manager.find_video_entry(path=video_path)
        if not video_entry:
            log.info("workflow.single_video.registering_video", video=video_path)

            # Prepare metadata for single video - use config if available
            metadata = {}
            if config:
                # Extract metadata from config if provided
                for key in ["group", "group_display_name", "day", "subject"]:
                    if key in config:
                        metadata[key] = config[key]

            # Set defaults for missing metadata to ensure proper tree display
            if "group" not in metadata:
                metadata["group"] = "single_video"
            if "group_display_name" not in metadata:
                metadata["group_display_name"] = "Vídeo Único"
            if "day" not in metadata:
                metadata["day"] = "1"
            if "subject" not in metadata:
                metadata["subject"] = "1"

            # Include zone information in the video entry
            video_data = {
                "path": video_path,
                "status": "processing",
                "has_arena": bool(zone_data and zone_data.polygon),
                "has_rois": bool(zone_data and zone_data.roi_polygons),
            }
            if metadata:
                video_data["metadata"] = metadata

            self.project_manager.add_video_batch(
                [video_data],
                save_project=False,  # Don't save to disk for single video workflow
            )

        # Save the zone data for this video so it can be retrieved later
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "workflow.single_video.saving_zones",
                video=video_path,
                has_arena=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )
            self.project_manager.save_zone_data(zone_data, video_path)

        # Refresh views so the video appears in Main Control and Reports tabs
        # Ensures the user sees the registered video before processing starts
        self.main_view_model.refresh_project_views(reason="Single video registered", immediate=True)

        # 1. Update the detector with the newly created zone data
        # We need to know the video dimensions to set up the zones correctly
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": f"Não foi possível abrir o vídeo: {video_path}"},
            )
            return
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.detector.set_zones(zone_data, width, height)
        log.info(
            "controller.single_video.zones_set",
            count=len(zone_data.roi_polygons) + (1 if zone_data.polygon else 0),
        )

        # Inform detector that aquarium region is defined
        if self.detector:
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.single_video.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
            )

        # 2. Prepare the environment for _process_videos
        scanned_files = ProjectManager.scan_input_paths([video_path])
        if not scanned_files:
            self.view.show_error("Erro", "Não foi possível identificar um arquivo de vídeo válido.")
            return
        video_to_process = scanned_files[0]

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_results")
        self.main_view_model._prepare_results_directory(output_dir)

        # 3. Create and start the processing worker
        self.cancel_event.clear()

        callbacks = self.create_processing_callbacks([video_to_process])
        context = self.create_processing_context(
            [video_to_process], output_dir, single_video_config=config
        )

        self.main_view_model._cancel_feedback_displayed = False
        self.main_view_model.processing_worker = ProcessingWorker(context, callbacks)
        self.main_view_model.processing_thread = (
            self.main_view_model.processing_worker.start_in_thread()
        )

        # Update processing state in StateManager
        self.state_manager.update_processing_state(
            source="controller.start_single_video_analysis",
            is_processing=True,
            current_video=os.path.basename(video_path),
            processing_start_time=datetime.now(),
        )

        # 4. Switch to analysis view mode immediately
        self.main_view_model._activate_analysis_view_mode()

        # Permanecer na tela principal para exibir a barra de progresso
        # self.view._create_welcome_frame()
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Análise Iniciada",
                    "message": "A análise do vídeo foi iniciada em segundo plano.\n"
                    "Você será notificado quando terminar. Os resultados serão salvos em:\n"
                    f"{output_dir}",
                },
            )

    def start_project_processing_workflow(self):
        """Adiciona vídeos com validação robusta de zonas.

        Extracted from MainViewModel.start_project_processing_workflow in Sprint 24.

        Sprint 11: Basic validations delegated to ProcessingCoordinator.
        Complex UI interactions (zone setup dialogs) remain in ViewModel.
        """
        log.info("workflow.project_processing.start")

        # Sprint 11: Delegate basic validations to ProcessingCoordinator
        # Sprint 13: Use consolidated error handling
        validation_result = self.processing_coordinator.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,  # Zone validation is complex with UI, handled below
            check_videos_exist=False,
        )

        if not self.main_view_model._handle_validation_error(validation_result):
            return

        # Sprint 13: Validate zones with UI interaction
        if not self.main_view_model._validate_zones_with_ui():
            return

        # 1. Ask user to select files or folders
        paths = self.view.ask_open_filenames(
            "Selecione Vídeos ou Pastas para Adicionar ao Projeto",
            [
                ("Todos os arquivos", "*.*"),
                ("Arquivos de vídeo", "*.mp4 *.avi *.mov"),
                ("Pastas", "*/"),
            ],
        )
        if not paths:
            return

        # 2. Scan the inputs
        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Vídeo Encontrado",
                    "message": "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados.",  # noqa: E501
                },
            )
            return

        # 3. Sprint 13: Handle mixed data scenario
        videos_to_process = self.main_view_model._handle_mixed_data_scenario(scanned_videos)
        if videos_to_process is None:
            return  # User cancelled or videos already added

        if not videos_to_process:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento Concluído",
                    "message": "Nenhum novo vídeo para processar.",
                },
            )
            return

        # 4. Add the batch to the project
        self.project_manager.add_video_batch(scanned_videos)

        # 5. Process the videos that need it using worker
        self.cancel_event.clear()

        callbacks = self.create_processing_callbacks(videos_to_process)
        context = self.create_processing_context(
            videos_to_process, self.project_manager.project_path
        )

        self.main_view_model._cancel_feedback_displayed = False
        self.main_view_model.processing_worker = ProcessingWorker(context, callbacks)
        self.main_view_model.processing_thread = (
            self.main_view_model.processing_worker.start_in_thread()
        )

        self.main_view_model._activate_analysis_view_mode()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Sucesso",
                "message": f"{len(videos_to_process)} vídeo(s) foram processados e adicionados ao projeto.",  # noqa: E501
            },
        )

    def _handle_targeted_selection_errors(
        self, selection_result, video_paths: list[str] | None
    ) -> bool:
        """Handle UI feedback for targeted selection mode errors.

        Returns:
            False if processing should stop, True otherwise.
        """
        # UI: Show info if no valid targets provided
        if not video_paths:  # Should not happen but defensive
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo selecionado para processamento.",
                },
            )
            return False

        # UI: Show warning if targets are missing from project
        if selection_result.has_missing:
            sample = [os.path.basename(path) for path in selection_result.missing_targets[:5]]
            if len(selection_result.missing_targets) > 5:
                sample.append(f"... (+{len(selection_result.missing_targets) - 5})")
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos fora do projeto",
                    "message": "Alguns itens selecionados não pertencem ao projeto atual:\n"
                    + "\n".join(sample),
                },
            )

        # UI: Show info if no candidates found
        if selection_result.candidate_count == 0:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                },
            )
            return False

        return True

    def _handle_pending_selection_errors(self, selection_result) -> bool:
        """Handle UI feedback for pending selection mode errors.

        Returns:
            False if processing should stop, True otherwise.
        """
        # UI: Show info if no pending videos
        if selection_result.candidate_count == 0:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo pendente para ser processado.",
                },
            )
            return False
        return True

    def _extract_and_validate_candidate_paths(self, candidate_entries) -> list[str] | None:
        """Extract and validate video paths from candidate entries.

        Returns:
            List of valid paths, or None if error occurred.
        """
        # Extract paths from candidate entries
        candidate_paths = [
            video.get("path")
            for video in candidate_entries
            if isinstance(video.get("path"), str) and video.get("path")
        ]

        # UI: Show error if no valid paths
        if not candidate_paths:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro",
                    "message": (
                        "Não foi possível localizar caminhos válidos "
                        "para os vídeos selecionados."
                    ),
                },
            )
            return None

        return candidate_paths

    def _handle_missing_files_warning(self, scan_result) -> None:
        """Show warning UI if scanned files are missing."""
        if scan_result.has_missing:
            sample_names = [os.path.basename(path) for path in scan_result.missing_files[:5]]
            if len(scan_result.missing_files) > 5:
                sample_names.append(f"... (+{len(scan_result.missing_files) - 5})")
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos Não Encontrados",
                    "message": "Alguns vídeos foram ignorados porque não foram localizados:\n"
                    + "\n".join(sample_names),
                },
            )
            log.warning(
                "workflow.project_processing.missing_sources",
                missing=len(scan_result.missing_files),
            )

    def _load_zones_for_eligible_videos(self, eligible_videos: list) -> None:
        """Load zone data from parquet files for eligible videos."""
        zones_updated = False
        for video_info in eligible_videos:
            if video_info.get("has_arena") or video_info.get("has_rois"):
                try:
                    zone_data = ProjectManager.load_zones_from_parquet(video_info)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "workflow.project_processing.zone_load_failed",
                        video=os.path.basename(video_info.get("path", "")),
                        error=str(exc),
                    )
                    zone_data = None

                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True

        if zones_updated:
            self.project_manager.save_project()

    def process_pending_project_videos(
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """Processa vídeos já adicionados ao projeto que possuem dados pendentes.

        Extracted from MainViewModel.process_pending_project_videos in Sprint 24.
        Sprint 11: Basic validations delegated to ProcessingCoordinator.
        Phase 2: Complexity reduced by extracting helper methods.
        """
        log.info(
            "workflow.project_processing.resume_requested",
            targeted=len(video_paths or []),
        )

        # Validate preconditions
        validation_result = self.processing_coordinator.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,
            check_videos_exist=True,
        )
        if not self.main_view_model._handle_validation_error(validation_result):
            return

        # Get all videos and prepare selection
        all_videos = self.project_manager.get_all_videos() or []
        skip_dialog = bool(video_paths)

        # Delegate selection logic to VideoSelectionService
        selection_result = self.video_selection_service.select_candidates(
            all_videos=all_videos,
            target_paths=video_paths,
        )

        # Handle selection mode specific errors
        if selection_result.selection_mode == "targeted":
            if not self._handle_targeted_selection_errors(selection_result, video_paths):
                return
        else:  # pending mode
            if not self._handle_pending_selection_errors(selection_result):
                return

        # Extract and validate paths
        candidate_paths = self._extract_and_validate_candidate_paths(
            selection_result.candidate_entries
        )
        if candidate_paths is None:
            return

        # Scan and validate file existence
        scan_result = self.video_validation_service.scan_and_validate_paths(
            candidate_paths, self.project_manager
        )
        self._handle_missing_files_warning(scan_result)

        # Extract results from service
        info_by_norm = scan_result.info_by_norm

        # Sprint 12: Use VideoClassificationService for classification
        classification_result = self.video_classification_service.classify_videos(
            selection_result.candidate_entries, info_by_norm
        )
        ready_with_trajectory = classification_result.ready_with_trajectory
        ready_with_zones = classification_result.ready_with_zones
        arena_only = classification_result.arena_only
        without_arena = classification_result.without_arena
        data_changed = classification_result.data_changed

        if data_changed:
            self.project_manager.save_project()

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo elegível foi encontrado com dados suficientes para análise.",  # noqa: E501
                },
            )
            return

        eligible_videos = self.select_eligible_videos(
            skip_dialog, ready_with_trajectory, ready_with_zones, arena_only, without_arena
        )
        if eligible_videos is None:
            return

        # Load zone data for eligible videos
        self._load_zones_for_eligible_videos(eligible_videos)

        self.cancel_event.clear()

        # For project-based processing, single_video_config must be None
        # to ensure hierarchical directory structure (group/day/subject)
        # is used instead of single video fallback path
        callbacks = self.create_processing_callbacks(eligible_videos)
        context = self.create_processing_context(
            eligible_videos,
            self.project_manager.project_path,
            single_video_config=None,  # None = project mode, uses metadata for paths
        )

        self.main_view_model._cancel_feedback_displayed = False
        self.main_view_model.processing_worker = ProcessingWorker(context, callbacks)
        self.main_view_model.processing_thread = (
            self.main_view_model.processing_worker.start_in_thread()
        )

        self.main_view_model._activate_analysis_view_mode()

        for video_info in eligible_videos:
            path_value = video_info.get("path")
            if path_value:
                self.project_manager.update_video_status(path_value, "complete")

        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Processando {len(eligible_videos)} vídeo(s) com dados existentes..."},
        )
        display_names = [
            os.path.basename(video_info.get("path", "")) or "(arquivo desconhecido)"
            for video_info in eligible_videos
        ]
        preview_lines = [f"• {name}" for name in display_names[:5]]
        if len(display_names) > 5:
            preview_lines.append(f"• ... (+{len(display_names) - 5} restante(s))")

        message = (
            f"O processamento de {len(eligible_videos)} vídeo(s) foi iniciado em segundo plano."
        )
        if preview_lines:
            message += "\n\nFila:\n" + "\n".join(preview_lines)

        self.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO, {"title": "Processamento Iniciado", "message": message}
        )

        log.info(
            "workflow.project_processing.resume_started",
            total=len(eligible_videos),
            with_trajectory=len(ready_with_trajectory),
            with_zones=len(ready_with_zones),
            targeted=bool(video_paths),
        )
