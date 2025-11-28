"""Processing Coordinator - Phase 3 Super Coordinator.

Consolidates ALL video processing, analysis, zone management, and configuration.
This is one of the 4 super coordinators created in Phase 3 of MainViewModel refactoring.

Consolidates (PHASE 3 - COMPLETE):
- ProcessingCoordinator (Sprint 6 & 11) - 731 lines - Base validation logic
- VideoProcessingOrchestrator (Sprint 24) - 952 lines - Video workflows
- AnalysisOrchestrator (Sprint 25) - 378 lines - Analysis workflows
- ZoneArenaOrchestrator (Sprint 30) - 229 lines - Zone/arena management
- ProcessingConfigOrchestrator (Sprint 31) - 301 lines - Processing modes

CRITICAL: Zero dependency on MainViewModel. Pure dependency injection.
Total: ~2600 lines consolidated → ~1400 lines (smart delegation to services)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.core.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.core.project_manager import ProjectManager
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video_classification_service import VideoClassificationService
    from zebtrack.core.video_selection_service import VideoSelectionService
    from zebtrack.core.video_validation_service import VideoValidationService
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.settings import Settings
    from zebtrack.ui.components.ui_coordinator import UICoordinator
    from zebtrack.ui.components.ui_state_controller import UIStateController
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


# ============================================================================
# Value Objects and Exceptions
# ============================================================================


@dataclass
class ValidationResult:
    """Result of processing validation check.

    Sprint 11: Value object for validation results to separate validation logic from UI.
    """

    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None
    context: dict[str, Any] | None = None

    @classmethod
    def success(cls) -> ValidationResult:
        """Create a successful validation result."""
        return cls(is_valid=True)

    @classmethod
    def failure(
        cls,
        error_code: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            error_code=error_code,
            error_message=error_message,
            context=context or {},
        )


class ProcessingCoordinatorError(Exception):
    """Base exception for ProcessingCoordinator errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.context = context or {}


# ============================================================================
# Main Coordinator Class
# ============================================================================


class ProcessingCoordinator(BaseCoordinator):
    """Super coordinator for complete video processing workflows.

    Phase 3 Consolidation - ALL processing responsibilities:
    - Video processing (single, batch, project-level)
    - Analysis workflows (aquarium detection, summaries, reports)
    - Zone and arena management (polygon configuration, validation)
    - Processing configuration (modes, intervals, context management)
    - Processing state management and cancellation
    - Progress tracking and event publishing

    Example:
        coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            detector_service=detector_service,
            weight_manager=weight_manager,
            settings_obj=settings,
            ui_coordinator=ui_coordinator,
            ui_state_controller=ui_state_controller,
            cancel_event=cancel_event,
            event_bus=event_bus,
            # Services
            video_selection_service=video_selection_service,
            video_validation_service=video_validation_service,
            video_classification_service=video_classification_service,
            analysis_service=analysis_service,
        )
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        weight_manager: WeightManager,
        settings_obj: Settings,
        ui_coordinator: UICoordinator,
        ui_state_controller: UIStateController,
        cancel_event: Event,
        # Services
        video_selection_service: VideoSelectionService,
        video_validation_service: VideoValidationService,
        video_classification_service: VideoClassificationService,
        analysis_service: AnalysisService | None = None,
        recorder_factory: RecorderFactory | None = None,
        event_bus: EventBus | None = None,
        # UI components (for callbacks)
        view: Any = None,
        root: Any = None,
        detector: Any = None,
    ):
        """Initialize ProcessingCoordinator with dependency injection.

        Args:
            state_manager: StateManager for state updates
            project_manager: ProjectManager for project operations
            detector_service: DetectorService for detector operations
            weight_manager: WeightManager for model weights
            settings_obj: Settings instance
            ui_coordinator: UICoordinator for UI updates
            ui_state_controller: UIStateController for UI state
            cancel_event: Threading event for cancellation
            video_selection_service: Service for video selection
            video_validation_service: Service for video validation
            video_classification_service: Service for video classification
            analysis_service: Optional AnalysisService
            recorder_factory: Optional RecorderFactory
            event_bus: Optional EventBus for publishing events
            view: Optional GUI view reference (for UI callbacks)
            root: Optional Tkinter root (for threading)
            detector: Optional detector instance (for zone setup)

        Note:
            NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.weight_manager = weight_manager
        self.settings = settings_obj
        self.ui_coordinator = ui_coordinator
        self.ui_state_controller = ui_state_controller
        self.cancel_event = cancel_event
        self.recorder_factory = recorder_factory

        # Services
        self.video_selection_service = video_selection_service
        self.video_validation_service = video_validation_service
        self.video_classification_service = video_classification_service
        self.analysis_service = analysis_service

        # UI components (for callbacks, gradually being removed)
        self.view = view
        self.root = root
        self.detector = detector

        # Internal state (migrated from orchestrators)
        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self.processing_worker: ProcessingWorker | None = None
        self.processing_thread: Any = None

        log.info("processing_coordinator.initialized.phase3")

    # ========================================================================
    # Group A: Video Processing Workflows (VideoProcessingOrchestrator)
    # ========================================================================

    def register_event_handlers(self) -> None:
        """Subscribe to video processing events.

        Phase 3: Consolidated from VideoProcessingOrchestrator.register_event_handlers
        """
        if not self.event_bus:
            return

        bus = self.event_bus
        log.info("processing_coordinator.register_handlers.start")

        # Video processing events
        bus.subscribe(
            Events.VIDEO_START_SINGLE_PROCESSING,
            lambda data: self.start_single_video_processing(
                data.get("video_path"), data.get("config"), data.get("zone_data")
            ),
        )
        bus.subscribe(
            Events.PROJECT_PROCESS_VIDEOS,
            lambda data: self.process_pending_project_videos(data.get("video_paths")),
        )
        # Auto-detect aquarium event
        bus.subscribe(
            Events.ZONE_AUTO_DETECT,
            lambda data: self.run_aquarium_detection(
                video_path=data.get("video_path"),
                stabilization_frames=int(data.get("stabilization_frames", 10)),
            ),
        )

        log.info("processing_coordinator.register_handlers.complete", count=3)

    def select_eligible_videos(
        self,
        skip_dialog: bool,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> list[dict] | None:
        """Select eligible videos for processing.

        Phase 3: Consolidated from VideoProcessingOrchestrator.select_eligible_videos
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
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Processamento",
                        "message": "Alguns vídeos selecionados foram ignorados porque não "
                        "possuem ROIs desenhadas:\n"
                        + "\n".join(f"• {name}" for name in skipped_names),
                    },
                )

            if not eligible_videos:
                self._publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum dos vídeos selecionados contém arena e ROIs "
                        "suficientes para gerar trajetórias.",
                    },
                )
                return None
        else:
            if not self.view:
                log.error("processing_coordinator.select_videos.no_view")
                return None

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
                self._publish_event(
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
        zone_data: Any = None,
        process_single_video_func: Callable | None = None,
        apply_project_settings_func: Callable | None = None,
    ) -> ProcessingContext:
        """Create the processing context with all necessary configuration.

        Phase 3: Consolidated from VideoProcessingOrchestrator.create_processing_context
        """
        return ProcessingContext(
            videos_to_process=videos_to_process,
            output_base_dir=output_base_dir,
            cancel_event=self.cancel_event,
            settings=self.settings,
            single_video_config=single_video_config,
            zone_data=zone_data,
            analysis_interval_frames=10,  # Will be updated by worker
            display_interval_frames=10,  # Will be updated by worker
            process_single_video_func=process_single_video_func,
            apply_project_settings_func=apply_project_settings_func,
            determine_intervals_func=self._determine_processing_intervals,
            retry_strategy=self.settings.video_processing.batch_retry_strategy,
        )

    def create_processing_callbacks(
        self,
        videos_to_process: list[dict],
        on_completed_callback: Callable | None = None,
    ) -> ProcessingCallbacks:
        """Create thread-safe callbacks for the processing worker.

        Phase 3: Consolidated from VideoProcessingOrchestrator.create_processing_callbacks
        """

        def on_started():
            """Call when processing starts."""
            if not self.view or not self.root:
                return

            self.ui_coordinator.show_progress_bar(self.view)
            self.ui_coordinator.set_status(
                self.view,
                f"Iniciando processamento para {len(videos_to_process)} vídeos...",
            )
            self.project_manager.set_active_zone_video(None)
            self._publish_processing_mode(source="worker.started", force=True)

        def on_progress(fraction: float, message: str, stats: dict | None):
            """Call with progress updates."""
            if self.cancel_event.is_set() or not self.view:
                return

            self.ui_coordinator.set_status(self.view, message)
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, message
            )

            if stats:
                self.state_manager.update_processing_state(
                    source="controller.processing_progress",
                    current_frame=stats.get("current_frame", 0),
                    total_frames=stats.get("total_frames", 0),
                )
                self._publish_event(Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats})

        def on_frame_processed(frame, detections, processing_info):
            """Call when a frame is ready for display."""
            if frame is not None:
                self._publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

            if detections is not None and processing_info:
                self._publish_event(
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
            if self.root and self.view:
                self.root.after(
                    0,
                    lambda: self.view.show_error("Erro na Análise", f"{context}: {error}"),
                )

        def on_fatal_error(exc, context, recovery_info):
            log.error(
                "controller.processing.fatal_error",
                context=context,
                error=str(exc),
                affected_videos=len(recovery_info["affected_videos"]),
            )
            if self.view:
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
            if self.view:
                self.ui_coordinator.set_status(self.view, "Processamento falhou")

        def on_completed(was_cancelled: bool, output_dir: str, summary: dict | None = None):
            """Call when all processing completes."""
            if not self.view:
                return

            self.project_manager.set_active_zone_video(None)
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)

            self.state_manager.update_processing_state(
                source="controller.processing_completed",
                is_processing=False,
                cancel_requested=was_cancelled,
                current_video=None,
            )

            if was_cancelled:
                self.ui_coordinator.show_info(
                    self.view, "Cancelado", "A análise de vídeo foi cancelada."
                )
            elif videos_to_process:
                msg = f"Análise concluída. Resultados salvos em:\n{output_dir}"
                self.ui_coordinator.show_info(self.view, "Sucesso", msg)

            self.ui_coordinator.set_status(self.view, "Pronto.")
            self._publish_processing_mode(source="worker.completed", force=True)

            if on_completed_callback:
                on_completed_callback()

        return ProcessingCallbacks(
            on_started=on_started,
            on_progress=on_progress,
            on_frame_processed=on_frame_processed,
            on_video_completed=on_video_completed,
            on_error=on_error,
            on_completed=on_completed,
            on_fatal_error=on_fatal_error,
        )

    def make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
    ):
        """Create a progress callback for a specific video.

        Phase 3: Consolidated from VideoProcessingOrchestrator.make_progress_callback
        """

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set() or not self.view:
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, progress_fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", progress_fraction, step_status
            )
            self._publish_event(
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
                self._publish_event(Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats})

            processing_report = self._publish_processing_mode(
                source="analysis_progress",
                force=False,
            )

            if detections is not None:
                self._publish_event(
                    Events.UI_UPDATE_DETECTION_OVERLAY,
                    {"detections": detections, "report": processing_report},
                )

            if frame is not None:
                self._publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

        return progress_callback

    def start_single_video_processing(
        self,
        video_path: Path | str,
        config: dict,
        zone_data: ZoneData,
    ):
        """Start the actual processing for a single video after zone setup.

        Phase 3: Consolidated from VideoProcessingOrchestrator.start_single_video_processing
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=str(video_path))

        # Validate processing can start
        validation_result = self.validate_can_start_processing(
            check_project_loaded=False,
            check_zones=False,
            check_videos_exist=False,
        )

        if not validation_result.is_valid:
            log.warning(
                "workflow.single_video.validation_failed", code=validation_result.error_code
            )
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Validação Falhou",
                    "message": validation_result.error_message,
                },
            )
            return

        self.project_manager.set_active_zone_video(video_path)

        # Register the single video in project_manager
        video_entry = self.project_manager.find_video_entry(path=video_path)
        if not video_entry:
            log.info("workflow.single_video.registering_video", video=str(video_path))

            metadata = self._extract_metadata_from_config(config)
            video_data = {
                "path": str(video_path),
                "status": "processing",
                "has_arena": bool(zone_data and zone_data.polygon),
                "has_rois": bool(zone_data and zone_data.roi_polygons),
            }
            if metadata:
                video_data["metadata"] = metadata

            self.project_manager.add_video_batch(
                [video_data],
                save_project=False,
            )

        # Save the zone data for this video
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "workflow.single_video.saving_zones",
                video=str(video_path),
                has_arena=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )
            self.project_manager.save_zone_data(
                zone_data,
                video_path,
                persist=bool(self.project_manager.project_path),
            )

        # Update detector with zones
        if self.detector:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                self._publish_event(
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
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.single_video.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
            )

        # Prepare processing environment
        scanned_files = ProjectManager.scan_input_paths([str(video_path)])
        if not scanned_files:
            if self.view:
                self.view.show_error(
                    "Erro", "Não foi possível identificar um arquivo de vídeo válido."
                )
            return
        video_to_process = scanned_files[0]

        video_name = os.path.splitext(os.path.basename(str(video_path)))[0]
        output_dir = os.path.join(os.path.dirname(str(video_path)), f"{video_name}_results")
        os.makedirs(output_dir, exist_ok=True)

        # Create and start processing worker
        self.cancel_event.clear()

        callbacks = self.create_processing_callbacks([video_to_process])
        context = self.create_processing_context(
            [video_to_process],
            output_dir,
            single_video_config=config,
            zone_data=zone_data,
        )

        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        # Update processing state
        self.state_manager.update_processing_state(
            source="controller.start_single_video_analysis",
            is_processing=True,
            current_video=os.path.basename(str(video_path)),
            processing_start_time=datetime.now(),
        )

        # Publish notification
        self._publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Análise Iniciada",
                "message": "A análise do vídeo foi iniciada em segundo plano.\n"
                "Você será notificado quando terminar. Os resultados serão salvos em:\n"
                f"{output_dir}",
            },
        )

    def process_pending_project_videos(
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """Process pending videos already added to the project.

        Phase 3: Consolidated from VideoProcessingOrchestrator.process_pending_project_videos
        """
        log.info(
            "workflow.project_processing.resume_requested",
            targeted=len(video_paths or []),
        )

        # Validate preconditions
        validation_result = self.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,
            check_videos_exist=True,
        )
        if not validation_result.is_valid:
            log.warning(
                "workflow.pending_videos.validation_failed", code=validation_result.error_code
            )
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Validação Falhou",
                    "message": validation_result.error_message,
                },
            )
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
        else:
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

        info_by_norm = scan_result.info_by_norm

        # Classify videos
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
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": (
                        "Nenhum vídeo elegível foi encontrado com dados suficientes para análise."
                    ),
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

        # Create and start processing worker
        callbacks = self.create_processing_callbacks(eligible_videos)
        context = self.create_processing_context(
            eligible_videos,
            self.project_manager.project_path,
            single_video_config=None,
        )

        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        for video_info in eligible_videos:
            path_value = video_info.get("path")
            if path_value:
                self.project_manager.update_video_status(path_value, "complete")

        self._publish_event(
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

        self._publish_event(
            Events.UI_SHOW_INFO, {"title": "Processamento Iniciado", "message": message}
        )

        log.info(
            "workflow.project_processing.resume_started",
            total=len(eligible_videos),
            with_trajectory=len(ready_with_trajectory),
            with_zones=len(ready_with_zones),
            targeted=bool(video_paths),
        )

    # ========================================================================
    # Group B: Analysis Workflows (AnalysisOrchestrator)
    # ========================================================================

    def run_aquarium_detection(
        self,
        video_path: Path | str | None = None,
        stabilization_frames: int = 10,
        temp_aquarium_method: str | None = None,
    ):
        """Run the aquarium detection model on specified or first project video.

        Phase 3: Consolidated from AnalysisOrchestrator.run_aquarium_detection
        """
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("controller.aquarium_detection.start")

        self._publish_event(
            Events.UI_SET_STATUS,
            {"message": "Detectando aquário, por favor aguarde..."},
        )
        self._publish_processing_mode(
            source="calibration.aquarium.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )

        try:
            if video_path is None:
                video_path = self.project_manager.get_next_video()

            if not video_path:
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Aviso",
                        "message": "Nenhum vídeo foi encontrado para a detecção.",
                    },
                )
                return

            self.project_manager.set_active_zone_video(video_path)

            # Display first frame
            self._publish_event(Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": str(video_path)})

            # Get detection method and model
            aquarium_method = temp_aquarium_method or self.settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self._publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível encontrar um modelo {aquarium_method} para "
                        "detecção do aquário.",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(
                str(video_path), stabilization_frames=stabilization_frames
            )

            if not polygons:
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Automática Falhou",
                        "message": "Não foi possível identificar uma área de aquário estável "
                        "no vídeo. Isso pode ocorrer devido a reflexos, pouca luz ou "
                        "movimento excessivo da câmera.\n\nPor favor, defina a área "
                        "do aquário manualmente utilizando a ferramenta 'Desenhar "
                        "Polígono Principal'.",
                    },
                )
                return

            main_polygon = polygons[0]
            log.info(
                "controller.aquarium_detection.success",
                polygon_points=len(main_polygon),
            )
            self._publish_event(Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon})

        except Exception as e:
            log.error("controller.aquarium_detection.error", exc_info=True)
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Detecção",
                    "message": f"Ocorreu um erro ao detectar o aquário: {e}",
                },
            )
        finally:
            self._publish_processing_mode(
                source="calibration.aquarium.complete",
                force=True,
            )
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def generate_parquet_summaries(
        self,
        target_videos: list[dict],
        settings_obj: Any,
        on_complete: Callable | None = None,
    ) -> None:
        """Generate parquet summaries for a list of videos.

        Phase 3: Consolidated from AnalysisOrchestrator._generate_parquet_summaries_worker
        """
        completed: list[str] = []
        skipped: list[str] = []
        details: list[str] = []
        data_changed = False

        for video in target_videos:
            state = None
            try:
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                )
            except Exception as exc:
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
                self._publish_event(
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
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Vídeos ignorados",
                        "message": "Alguns sumários não puderam ser gerados:\n"
                        + "\n".join(details),
                    },
                )

            self._publish_event(Events.UI_SET_STATUS, {"message": status_msg})

            if on_complete:
                on_complete(status_msg)

        if self.root:
            self.root.after(0, finalize)
        else:
            finalize()

    # ========================================================================
    # Group C: Zone and Arena Management (ZoneArenaOrchestrator)
    # ========================================================================

    def set_main_arena_polygon(self, points: list) -> bool:
        """Save polygon with robust validations.

        Phase 3: Consolidated from ZoneArenaOrchestrator.set_main_arena_polygon
        """
        try:
            # Validation 1: Valid points
            if not points or len(points) < 3:
                log.error(
                    "controller.polygon.invalid_points",
                    count=len(points) if points else 0,
                )
                return False

            # Check if we are in single video mode (active video set but no project path)
            active_video = self.project_manager.get_active_zone_video()

            # Validation 2: Project exists or Active Video exists
            if not self.project_manager.project_path and not active_video:
                log.error("controller.polygon.no_project_or_video")
                return False

            # Validation 3: Data structure
            project_data = getattr(self.project_manager, "project_data", {})
            if self.project_manager.project_path and "detection_zones" not in project_data:
                self.project_manager.save_zone_data(ZoneData(), persist=False)
                log.info("controller.polygon.initialized_detection_zones")

            # Save
            if not self.project_manager.project_path and active_video:
                # Single video mode: direct save to sidecar
                zone_data = self.project_manager.get_zone_data(video_path=active_video)
                if not zone_data:
                    zone_data = ZoneData()
                zone_data.polygon = points
                self.project_manager.save_zone_data(
                    zone_data, video_path=active_video, persist=False
                )
            else:
                # Project mode
                self.project_manager.update_main_polygon(points)

            # Force visual update
            self._publish_event(Events.UI_REDRAW_ZONES, {})

            log.info("controller.polygon.saved", points=len(points))
            return True

        except Exception as e:
            log.error("controller.polygon.save_error", error=str(e))
            return False

    def save_manual_arena(self, polygon_points: list[list[int]]):
        """Save manually adjusted arena and update detector.

        Phase 3: Consolidated from ZoneArenaOrchestrator.save_manual_arena
        """
        log.info("controller.arena.save_manual", points_count=len(polygon_points))
        # Delegate to set_main_arena_polygon which handles persistence
        success = self.set_main_arena_polygon(polygon_points)
        if success and self.detector:
            # Update detector zones
            self._publish_event(Events.DETECTOR_UPDATE_ZONES, {})

    def add_roi_polygon(self, roi_points: list[list[int]], name: str, color: tuple[int, int, int]):
        """Add ROI with overlap validation.

        Phase 3: Consolidated from ZoneArenaOrchestrator.add_roi_polygon
        """
        try:
            log.info("controller.zone.add_roi", name=name, points=len(roi_points))

            # Validate project exists OR active video
            active_video = self.project_manager.get_active_zone_video()
            if not self.project_manager.project_path and not active_video:
                log.error("controller.zone.add_roi.no_project_or_video", name=name)
                return False

            zone_data = self.project_manager.get_zone_data(video_path=active_video)

            # Validate ROI is within main arena
            if zone_data.polygon and len(zone_data.polygon) >= 3:
                arena_poly = np.array(zone_data.polygon, dtype=np.float32)

                # Adjust points that are slightly outside
                adjusted_points = []
                centroid_x = float(np.mean(arena_poly[:, 0]))
                centroid_y = float(np.mean(arena_poly[:, 1]))

                for point in roi_points:
                    px, py = float(point[0]), float(point[1])
                    result = cv2.pointPolygonTest(arena_poly, (px, py), True)

                    # If slightly outside (within 3 pixels), nudge inside
                    if -3.0 <= result < 0:
                        dx = centroid_x - px
                        dy = centroid_y - py
                        length = float(np.sqrt(dx * dx + dy * dy))
                        if length > 0:
                            px += (dx / length) * 3.0
                            py += (dy / length) * 3.0

                    adjusted_points.append([float(px), float(py)])

                # Validate adjusted points
                points_outside = 0
                for point in adjusted_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(point), False)
                    if result < 0:
                        points_outside += 1

                # If adjustment worked, use adjusted points
                if points_outside == 0:
                    roi_points = adjusted_points

                if points_outside > 0:
                    outside_percent = (points_outside / len(roi_points)) * 100
                    log.warning(
                        "controller.roi.outside_arena",
                        name=name,
                        points_outside=points_outside,
                        percent=outside_percent,
                    )

                    if self.view and not self.view.ask_ok_cancel(
                        "ROI Fora da Arena",
                        (
                            f"A ROI '{name}' tem {points_outside} pontos "
                            f"({outside_percent:.1f}%) "
                            "fora da arena principal.\n\nDeseja continuar mesmo assim?"
                        ),
                    ):
                        return False

                # Validate overlap with existing ROIs
                for i, existing_roi in enumerate(zone_data.roi_polygons):
                    if len(existing_roi) >= 3:
                        overlapping_points = 0
                        existing_poly = np.array(existing_roi, dtype=np.int32)

                        for point in roi_points:
                            result = cv2.pointPolygonTest(existing_poly, tuple(point), False)
                            if result >= 0:
                                overlapping_points += 1

                        if overlapping_points > 0:
                            overlap_percent = (overlapping_points / len(roi_points)) * 100

                            if overlap_percent > 20:
                                existing_name = (
                                    zone_data.roi_names[i]
                                    if i < len(zone_data.roi_names)
                                    else f"ROI_{i + 1}"
                                )
                                log.warning(
                                    "controller.roi.overlap",
                                    name=name,
                                    existing=existing_name,
                                    percent=overlap_percent,
                                )

                                if self.view and not self.view.ask_ok_cancel(
                                    "ROIs Sobrepostas",
                                    f"A nova ROI '{name}' tem {overlap_percent:.1f}% de "
                                    f"sobreposição com '{existing_name}'.\n\n"
                                    "Deseja continuar?",
                                ):
                                    return False

            # Add ROI after validations
            zone_data.roi_polygons.append(roi_points)
            zone_data.roi_names.append(name)
            zone_data.roi_colors.append(color)

            # Save and reload zones in detector
            # If no project path, pass video_path explicitly to persist to sidecar
            save_path = (
                active_video if (not self.project_manager.project_path and active_video) else None
            )

            # Determine persist flag
            should_persist = bool(self.project_manager.project_path)

            self.project_manager.save_zone_data(
                zone_data, video_path=save_path, persist=should_persist
            )

            if self.detector:
                self._publish_event(Events.DETECTOR_UPDATE_ZONES, {})
            log.info("controller.zone.add_roi.success", name=name)
            return True

        except Exception as e:
            log.error("controller.zone.add_roi.error", name=name, error=str(e))
            return False

    # ========================================================================
    # Group D: Processing Configuration (ProcessingConfigOrchestrator)
    # ========================================================================

    def _determine_processing_mode(self) -> ProcessingMode:
        """Inspect current detector/settings state to infer active mode.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._determine_processing_mode
        """
        if self.detector and hasattr(self.detector, "is_single_subject_mode"):
            try:
                if self.detector.is_single_subject_mode():
                    return ProcessingMode.SINGLE_SUBJECT
            except Exception:
                log.warning(
                    "controller.processing_mode.detector_probe_failed",
                    exc_info=True,
                )

        try:
            use_single = bool(self.settings.tracking.use_single_subject_tracker)
            log.info(
                "controller.determine_processing_mode",
                use_single_subject_tracker=use_single,
                result="SINGLE_SUBJECT" if use_single else "MULTI_TRACK",
            )
            if use_single:
                return ProcessingMode.SINGLE_SUBJECT
        except AttributeError:
            pass

        return ProcessingMode.MULTI_TRACK

    def _publish_processing_mode(
        self,
        *,
        source: str,
        force: bool = False,
        mode_override: ProcessingMode | None = None,
    ) -> ProcessingReport:
        """Notify the GUI about current processing mode when it changes.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._publish_processing_mode
        """
        mode = mode_override or self._determine_processing_mode()
        if not force and mode == getattr(self, "_active_processing_mode", None):
            return ProcessingReport(mode=mode, source=source)

        self._active_processing_mode = mode
        report = ProcessingReport(mode=mode, source=source)
        if self.view and hasattr(self.view, "update_processing_mode"):
            self.ui_state_controller._schedule_on_ui(self.view.update_processing_mode, report)
        return report

    def _resolve_single_animal_mode(self, single_video_config: dict | None) -> bool | None:
        """Derive whether single-animal tracking mode should be active.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._resolve_single_animal_mode
        """

        def _coerce_to_int(value):
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        if single_video_config:
            count = _coerce_to_int(single_video_config.get("animals_per_aquarium"))
            if count is not None:
                enabled = count == 1
                log.debug(
                    "controller.single_animal_mode.resolved_single_video",
                    animals_per_aquarium=count,
                    enabled=enabled,
                )
                return enabled

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration") or {}
        count = _coerce_to_int(calibration.get("animals_per_aquarium"))
        if count is not None:
            enabled = count == 1
            log.debug(
                "controller.single_animal_mode.resolved_project",
                animals_per_aquarium=count,
                enabled=enabled,
            )
            return enabled

        return None

    def _resolve_single_subject_tracker_preference(
        self, single_video_config: dict | None
    ) -> bool | None:
        """Resolve single-subject tracker preference from project or single video config.

        Phase 3: Consolidated from
        ProcessingConfigOrchestrator._resolve_single_subject_tracker_preference
        """
        log.info(
            "controller.resolve_tracker.entry",
            has_config=single_video_config is not None,
            config_keys=list(single_video_config.keys()) if single_video_config else [],
        )

        # Check directly in single_video_config first
        if single_video_config:
            if "use_single_subject_tracker" in single_video_config:
                pref = bool(single_video_config["use_single_subject_tracker"])
                log.info(
                    "controller.resolve_tracker.explicit",
                    use_single_subject=pref,
                    source="single_video_config",
                )
                return pref

            animals_per_aquarium = single_video_config.get("animals_per_aquarium")
            if animals_per_aquarium is not None:
                pref = int(animals_per_aquarium) == 1
                log.info(
                    "controller.resolve_tracker.from_animals",
                    use_single_subject=pref,
                    animals_per_aquarium=animals_per_aquarium,
                    source="single_video_config",
                )
                return pref

        # Try to get project type
        project_type = None
        if single_video_config:
            project_type = single_video_config.get("project_type")

        if not project_type:
            project_data = getattr(self.project_manager, "project_data", {})
            if project_data:
                project_type = project_data.get("project_type")

        # Delegate to detector service
        return self.detector_service._resolve_single_subject_tracker_preference(project_type)

    def _configure_single_subject_tracker(self, enabled: bool) -> None:
        """Configure single-subject tracking mode.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._configure_single_subject_tracker
        """
        # Note: Would delegate to DetectorCoordinator in Phase 3
        # For now, update settings directly
        self.settings.tracking.use_single_subject_tracker = bool(enabled)
        self._publish_processing_mode(
            source="tracker_configuration",
            force=True,
        )

    def _determine_processing_intervals(self, single_video_config: dict | None) -> tuple[int, int]:
        """Determine processing intervals from config or project.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._determine_processing_intervals
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
            log.info(
                "controller.processing.intervals_single_video",
                analysis_interval=analysis_interval_frames,
                display_interval=display_interval_frames,
                config_keys=list(single_video_config.keys()),
                animals_per_aquarium=single_video_config.get("animals_per_aquarium"),
                use_single_subject_tracker=single_video_config.get("use_single_subject_tracker"),
            )
        else:
            project_data = getattr(self.project_manager, "project_data", {}) or {}
            analysis_interval_frames = project_data.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = project_data.get(
                "display_interval_frames", display_interval_frames
            )

        return int(analysis_interval_frames), int(display_interval_frames)

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config: dict | None) -> Iterator[bool]:
        """Context manager for temporary single-animal mode.

        Phase 3: Consolidated from ProcessingConfigOrchestrator._temporary_single_animal_mode
        """
        log.info(
            "controller.temporary_mode.entry",
            has_config=single_video_config is not None,
            config_keys=list(single_video_config.keys()) if single_video_config else [],
        )

        previous_mode = self.settings.video_processing.single_animal_per_aquarium
        resolved_mode = self._resolve_single_animal_mode(single_video_config)

        previous_tracker_pref = self.settings.tracking.use_single_subject_tracker
        resolved_tracker_pref = self._resolve_single_subject_tracker_preference(single_video_config)
        if resolved_tracker_pref is None:
            resolved_tracker_pref = previous_tracker_pref

        if resolved_mode is not None and resolved_mode != previous_mode:
            self.settings.video_processing.single_animal_per_aquarium = resolved_mode
            log.info(
                "controller.processing.single_animal_mode",
                enabled=resolved_mode,
                previous=previous_mode,
                scope="single_video" if single_video_config else "project",
            )

        tracker_changed = resolved_tracker_pref != previous_tracker_pref
        if tracker_changed:
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            log.info(
                "controller.processing.single_subject_tracker",
                enabled=resolved_tracker_pref,
                previous=previous_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

        self._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
        self._publish_processing_mode(
            source="processing.temporary_mode.enter",
            force=True,
        )

        try:
            yield self.settings.video_processing.single_animal_per_aquarium
        finally:
            if self.settings.video_processing.single_animal_per_aquarium != previous_mode:
                self.settings.video_processing.single_animal_per_aquarium = previous_mode
                log.info(
                    "controller.processing.single_animal_mode_restored",
                    restored=previous_mode,
                )

            if tracker_changed:
                self.settings.tracking.use_single_subject_tracker = previous_tracker_pref
                log.info(
                    "controller.processing.single_subject_tracker_restored",
                    restored=previous_tracker_pref,
                )

            self._configure_single_subject_tracker(
                self.settings.tracking.use_single_subject_tracker
            )
            self._publish_processing_mode(
                source="processing.temporary_mode.exit",
                force=True,
            )

    # ========================================================================
    # Group E: Validation and State Management
    # ========================================================================

    def validate_can_start_processing(
        self,
        *,
        check_project_loaded: bool = True,
        check_zones: bool = False,
        check_videos_exist: bool = False,
    ) -> ValidationResult:
        """Validate that processing can start.

        Phase 3: Retained from original ProcessingCoordinator (Sprint 11)
        """
        log.debug(
            "processing_coordinator.validate_can_start_processing",
            check_project=check_project_loaded,
            check_zones=check_zones,
            check_videos=check_videos_exist,
        )

        # Validation 1: Processing already active?
        processing_state = self.state_manager.get_processing_state()
        if processing_state.is_processing:
            log.warning("processing_coordinator.validation.already_active")
            return ValidationResult.failure(
                error_code="processing_already_active",
                error_message="Uma análise de vídeo já está em andamento. "
                "Por favor, aguarde ou cancele a análise atual.",
                context={"current_video": processing_state.current_video},
            )

        # Validation 2: Project loaded?
        if check_project_loaded:
            if not self.project_manager.project_path:
                log.warning("processing_coordinator.validation.no_project_loaded")
                return ValidationResult.failure(
                    error_code="no_project_loaded",
                    error_message="Nenhum projeto carregado",
                    context={},
                )

        # Validation 3: Zones/arena defined?
        if check_zones:
            zone_data = self.project_manager.get_zone_data()
            if not zone_data or not zone_data.polygon:
                log.warning("processing_coordinator.validation.no_main_arena")
                return ValidationResult.failure(
                    error_code="no_main_arena",
                    error_message="O polígono principal do aquário não foi definido",
                    context={
                        "has_zone_data": zone_data is not None,
                        "has_polygon": bool(zone_data and zone_data.polygon),
                        "roi_count": len(zone_data.roi_polygons) if zone_data else 0,
                    },
                )

        # Validation 4: Videos exist in project?
        if check_videos_exist:
            all_videos = self.project_manager.get_all_videos() or []
            if not all_videos:
                log.warning("processing_coordinator.validation.no_videos")
                return ValidationResult.failure(
                    error_code="no_videos_in_project",
                    error_message="Nenhum vídeo cadastrado no projeto atualmente",
                    context={"video_count": 0},
                )

        log.debug("processing_coordinator.validate_can_start_processing.success")
        return ValidationResult.success()

    # ========================================================================
    # Group F: Supporting Methods (Private)
    # ========================================================================

    def _extract_metadata_from_config(self, config: dict) -> dict:
        """Extract metadata from single video config."""
        metadata = {}
        if config:
            for key in ["group", "group_display_name", "day", "subject"]:
                if key in config:
                    metadata[key] = config[key]

        # Set defaults
        if "group" not in metadata:
            metadata["group"] = "single_video"
        if "group_display_name" not in metadata:
            metadata["group_display_name"] = "Vídeo Único"
        if "day" not in metadata:
            metadata["day"] = "1"
        if "subject" not in metadata:
            metadata["subject"] = "1"

        return metadata

    def _handle_targeted_selection_errors(
        self, selection_result, video_paths: list[str] | None
    ) -> bool:
        """Handle UI feedback for targeted selection mode errors."""
        if not video_paths:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo selecionado para processamento.",
                },
            )
            return False

        if selection_result.has_missing:
            sample = [os.path.basename(path) for path in selection_result.missing_targets[:5]]
            if len(selection_result.missing_targets) > 5:
                sample.append(f"... (+{len(selection_result.missing_targets) - 5})")
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos fora do projeto",
                    "message": "Alguns itens selecionados não pertencem ao projeto atual:\n"
                    + "\n".join(sample),
                },
            )

        if selection_result.candidate_count == 0:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                },
            )
            return False

        return True

    def _handle_pending_selection_errors(self, selection_result) -> bool:
        """Handle UI feedback for pending selection mode errors."""
        if selection_result.candidate_count == 0:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo pendente para ser processado.",
                },
            )
            return False
        return True

    def _extract_and_validate_candidate_paths(self, candidate_entries) -> list[str] | None:
        """Extract and validate video paths from candidate entries."""
        candidate_paths = [
            video.get("path")
            for video in candidate_entries
            if isinstance(video.get("path"), str) and video.get("path")
        ]

        if not candidate_paths:
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro",
                    "message": (
                        "Não foi possível localizar caminhos válidos para os vídeos selecionados."
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
            self._publish_event(
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
                except Exception as exc:
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

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation.

        Phase 3: Consolidated from AnalysisOrchestrator._process_summary_video
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

        try:
            trajectory_df = pd.read_parquet(trajectory_path)
        except Exception as exc:
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

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)

            arena_polygon_px = list(zone_data.polygon or [])

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

            calib_data = self.project_manager.project_data.get("calibration", {})
            width_cm = calib_data.get("aquarium_width_cm")
            height_cm = calib_data.get("aquarium_height_cm")
            if not width_cm or not height_cm:
                return "skipped", f"{experiment_id}: calibração incompleta (px/cm).", None, False

            cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
            _, video_height_px = cal.target_dims_px
            pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
            arena_polygon_warped = cal.transform_points(arena_polygon_px)

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

            metadata = self.project_manager.get_metadata_for_experiment(experiment_id) or {
                "experiment_id": experiment_id,
                "video_name": experiment_id,
            }

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
        except Exception as exc:
            return "failed", f"{experiment_id}: erro inesperado ({exc}).", None, False
        finally:
            self.project_manager.set_active_zone_video(None)
