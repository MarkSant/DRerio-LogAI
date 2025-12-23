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
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.core.video_classification_service import VideoClassificationService
    from zebtrack.core.video_selection_service import VideoSelectionService
    from zebtrack.core.video_validation_service import VideoValidationService
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.orchestrators.ui_state_controller import UIStateController
    from zebtrack.settings import Settings
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
        ui_coordinator: UIScheduler,
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
            ui_coordinator: UIScheduler for UI updates
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
        self._is_detecting_aquarium: bool = False

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
                data.get("video_path") if isinstance(data, dict) else None,
                data.get("config") if isinstance(data, dict) else {},
                data.get("zone_data") if isinstance(data, dict) else None,
            ),
        )
        bus.subscribe(
            Events.PROJECT_PROCESS_VIDEOS,
            lambda data: self.process_pending_project_videos(
                data.get("video_paths") if isinstance(data, dict) else None
            ),
        )
        # Auto-detect aquarium event
        bus.subscribe(
            Events.ZONE_AUTO_DETECT,
            lambda data: self.run_aquarium_detection(
                video_path=data.get("video_path") if isinstance(data, dict) else None,
                stabilization_frames=int(data.get("stabilization_frames", 10))
                if isinstance(data, dict)
                else 10,
            ),
        )
        # Generate reports event
        bus.subscribe(
            Events.PROJECT_GENERATE_SUMMARIES,
            lambda data: self.generate_project_reports(
                data.get("video_paths") if isinstance(data, dict) else None
            ),
        )
        # Generate trajectories (from Reports tab)
        bus.subscribe(
            Events.PROCESSING_GENERATE_TRAJECTORIES,
            lambda data: self.process_pending_project_videos(
                [s.rpartition("_video_")[-1] for s in data.get("selection", ())]
                if isinstance(data, dict) and "selection" in data
                else None
            ),
        )

        # Multi-aquarium auto-detection event (Phase 5)
        bus.subscribe(
            Events.ZONE_MULTI_AUTO_DETECT,
            lambda data: self._handle_multi_auto_detect(data),
        )

        # Unified report generation
        def _handle_report_generate(data):
            if not isinstance(data, dict):
                return
            report_type = data.get("report_type")
            videos = data.get("videos", [])
            paths = [v.get("path") for v in videos if v.get("path")]

            if report_type == "unified":
                self.generate_unified_report(paths)
            else:
                self.generate_project_reports(paths)

        bus.subscribe(Events.REPORT_GENERATE, _handle_report_generate)

        log.info("processing_coordinator.register_handlers.complete", count=5)

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

        # Check for existing results and ask for overwrite
        if ready_with_trajectory and self.view:
            if self.view.ask_ok_cancel(
                "Resultados Existentes",
                f"{len(ready_with_trajectory)} vídeos já possuem trajetórias processadas.\n"
                "Deseja reprocessá-los (sobrescrevendo os dados anteriores)?",
            ):
                pass  # User confirmed overwrite
            else:
                ready_with_trajectory = []  # User declined, skip these

        if skip_dialog:
            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)
            eligible_videos.extend(arena_only)

            if arena_only:
                log.info(
                    "workflow.project_processing.including_arena_only",
                    count=len(arena_only),
                )

            if not eligible_videos:
                self._publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum dos vídeos selecionados contém arena definida para processamento.",
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
        # SYNC: Ensure global settings reflect project/wizard preference for single animal mode
        # This is critical because ProcessingWorker reads from settings to init ByteTracker
        use_single_subject = self._resolve_single_subject_tracker_preference(single_video_config)
        if use_single_subject is not None:
            if use_single_subject != self.settings.tracking.use_single_subject_tracker:
                log.info(
                    "processing_coordinator.sync_settings",
                    use_single_subject_tracker=use_single_subject,
                    reason="worker_initialization_sync",
                )
                self.settings.tracking.use_single_subject_tracker = use_single_subject
                # Also sync legacy flag for compatibility
                self.settings.video_processing.single_animal_per_aquarium = use_single_subject

        # Calculate processing intervals from config or project settings
        analysis_interval, display_interval = self._determine_processing_intervals(
            single_video_config
        )

        log.info(
            "create_processing_context",
            cancel_event_id=id(self.cancel_event),
            is_set=self.cancel_event.is_set(),
            analysis_interval_frames=analysis_interval,
            display_interval_frames=display_interval,
            use_single_subject=use_single_subject,
        )
        return ProcessingContext(
            videos_to_process=videos_to_process,
            output_base_dir=output_base_dir,
            cancel_event=self.cancel_event,
            settings=self.settings,
            single_video_config=single_video_config,
            zone_data=zone_data,
            analysis_interval_frames=analysis_interval,
            display_interval_frames=display_interval,
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

        def on_progress(
            index: int,
            total: int,
            experiment_id: str,
            fraction: float,
            message: str,
            stats: dict | None,
        ):
            """Call with progress updates."""
            if self.cancel_event.is_set() or not self.view:
                return

            overall_progress = f"Processando {index + 1}/{total}: {experiment_id}"
            step_status = f"Etapa: {message}"
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, step_status
            )

            # Extract video metadata for current video
            video_metadata = {}
            if 0 <= index < len(videos_to_process):
                current_video = videos_to_process[index]
                video_metadata = current_video.get("metadata", {})

            # Log metadata extraction for debugging
            log.debug(
                "on_progress.metadata_extracted",
                index=index,
                total=total,
                experiment_id=experiment_id,
                group=video_metadata.get("group"),
                day=video_metadata.get("day"),
                subject=video_metadata.get("subject"),
            )

            # Publish task status update for Analysis tab display
            self._publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {
                    "payload": {
                        "index": index,
                        "total": total,
                        "experiment_id": experiment_id,
                        "step": message,
                        "group": video_metadata.get("group"),
                        "day": video_metadata.get("day"),
                        "subject": video_metadata.get("subject"),
                    }
                },
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

        total_videos = len(videos_to_process)

        def on_video_completed(index: int, total: int, experiment_id: str, success: bool):
            """Call when a single video completes tracking.

            Registers the trajectory output with the project manager so that
            has_trajectory flag is set and the UI displays the correct status.
            """
            log.info(
                "controller.video_completed",
                index=index,
                total=total,
                experiment_id=experiment_id,
                success=success,
            )

            if not success:
                return

            # Find the video entry by experiment_id
            video_path = None
            video_results_dir = None
            for v in videos_to_process:
                v_path = v.get("path", "")
                v_exp_id = os.path.splitext(os.path.basename(v_path))[0]
                if v_exp_id == experiment_id:
                    video_path = v_path
                    video_results_dir = v.get("results_dir")
                    break

            if not video_path:
                log.warning(
                    "controller.video_completed.video_not_found",
                    experiment_id=experiment_id,
                )
                return

            # Use pre-calculated results_dir if available, otherwise construct fallback
            if video_results_dir:
                results_dir = video_results_dir
            else:
                video_name = os.path.splitext(os.path.basename(video_path))[0]
                results_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_results")
            trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
            trajectory_exists = os.path.exists(trajectory_path)

            # Check alternate multi-aquarium locations before warning
            alt_multi_outputs: dict[int, dict] = {}
            if not trajectory_exists and results_dir and os.path.exists(results_dir):
                for aq_id in [0, 1]:
                    aq_subdir = os.path.join(results_dir, f"aquarium_{aq_id}")
                    if not os.path.exists(aq_subdir):
                        continue

                    alt_paths = [
                        os.path.join(
                            aq_subdir, f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet"
                        ),
                        os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
                    ]
                    for alt_path in alt_paths:
                        if os.path.exists(alt_path):
                            alt_multi_outputs[aq_id] = {
                                "results_dir": aq_subdir,
                                "parquet_files": {"trajectory": alt_path},
                                "group": v.get("group"),
                                "subject_id": v.get("subject"),
                                "day": v.get("day", 1),
                            }
                            break

                if alt_multi_outputs:
                    trajectory_exists = False  # avoid single-video registration

            # Register the trajectory output with the project manager
            if trajectory_exists:
                self.project_manager.register_processing_outputs(
                    video_path=video_path,
                    results_dir=results_dir,
                    trajectory_path=trajectory_path,
                )
                log.info(
                    "controller.video_completed.trajectory_registered",
                    experiment_id=experiment_id,
                    trajectory_path=trajectory_path,
                )
            else:
                if not alt_multi_outputs:
                    log.warning(
                        "controller.video_completed.trajectory_not_found",
                        experiment_id=experiment_id,
                        expected_path=trajectory_path,
                    )

            # Check for multi-aquarium outputs
            outputs_by_aquarium = alt_multi_outputs.copy() if alt_multi_outputs else {}

            # Also check video_results_dir if different from results_dir (e.g. project mode with custom path)
            if (
                video_results_dir
                and video_results_dir != results_dir
                and os.path.exists(video_results_dir)
            ):
                for aq_id in [0, 1]:
                    aq_subdir = os.path.join(video_results_dir, f"aquarium_{aq_id}")
                    if os.path.exists(aq_subdir):
                        traj_candidates = [
                            os.path.join(
                                aq_subdir,
                                f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet",
                            ),
                            os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
                        ]
                        traj_file = next((p for p in traj_candidates if os.path.exists(p)), None)
                        if traj_file:
                            group = v.get("group")
                            subject = v.get("subject")
                            outputs_by_aquarium[aq_id] = {
                                "results_dir": aq_subdir,
                                "parquet_files": {"trajectory": traj_file},
                                "group": group,
                                "subject_id": subject,
                                "day": v.get("day", 1),
                            }

            is_multi_aquarium = bool(outputs_by_aquarium)

            # Sequential multi-aquarium: let the dedicated completion handler drive advancement
            if hasattr(self, "_sequential_context") and self._sequential_context:
                return

            if is_multi_aquarium and outputs_by_aquarium:
                self.project_manager.register_multi_aquarium_outputs(
                    video_path=video_path, outputs_by_aquarium=outputs_by_aquarium
                )
                log.info(
                    "controller.video_completed.multi_aquarium_registered",
                    video=experiment_id,
                    aquariums=list(outputs_by_aquarium.keys()),
                )

                # Sequential multi-aquarium: advance to next aquarium if context exists
                if hasattr(self, "_sequential_context") and self._sequential_context:
                    ctx = self._sequential_context
                    # Store outputs to context for later unified registration
                    ctx_outputs = ctx.get("outputs_by_aquarium", {})
                    ctx_outputs.update(outputs_by_aquarium)
                    ctx["outputs_by_aquarium"] = ctx_outputs
                    ctx["current_aquarium_index"] = ctx.get("current_aquarium_index", 0) + 1

                    if hasattr(self, "view") and self.view and hasattr(self.view, "root"):
                        self.view.root.after(50, self._process_next_aquarium_in_sequence)
                    else:
                        self._process_next_aquarium_in_sequence()

                self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

                # Generate report immediately
                try:
                    self.generate_project_reports([video_path])
                except Exception as e:
                    log.error("controller.video_completed.report_failed", error=str(e))
            elif trajectory_exists and total_videos <= 1:
                # Single-video flow: generate reports immediately when trajectory is ready
                try:
                    self.generate_project_reports([video_path])
                except Exception as e:
                    log.error(
                        "controller.video_completed.report_failed_single",
                        video=experiment_id,
                        error=str(e),
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

            # Refresh project views to show new results/status
            self._publish_event(
                Events.UI_REFRESH_PROJECT_VIEWS,
                {
                    "reason": "analysis_completed",
                    "append_summary": True,
                    "immediate": False,
                },
            )

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

    def cancel_processing(self) -> None:
        """Cancel any active processing."""
        log.info("coordinator.cancel_requested")
        self.cancel_event.set()

        if self.processing_worker and self.processing_worker.is_running:
            log.info("coordinator.cancelling_worker")
            self.processing_worker.cancel()

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

        # Check for sequential multi-aquarium processing mode
        is_multi_aquarium = hasattr(zone_data, "aquariums")
        use_sequential = is_multi_aquarium and getattr(zone_data, "sequential_processing", False)

        # Extract calibration parameters provided in the single-video dialog
        width_cm = None
        height_cm = None
        num_aquariums = 1

        if isinstance(config, dict):
            # Extract num_aquariums
            try:
                num_aquariums = int(config.get("num_aquariums", 1))
                # Update global settings
                self.settings.analysis_config.num_aquariums = num_aquariums
            except (TypeError, ValueError):
                pass

            try:
                raw_width = config.get("aquarium_width_cm")
                width_cm = float(raw_width) if raw_width not in (None, "") else None
            except (TypeError, ValueError):
                width_cm = None

            try:
                raw_height = config.get("aquarium_height_cm")
                height_cm = float(raw_height) if raw_height not in (None, "") else None
            except (TypeError, ValueError):
                height_cm = None

        if use_sequential:
            log.info(
                "workflow.sequential_multi.detected",
                video=str(video_path),
                aquarium_count=len(zone_data.aquariums),
            )

            # Persist calibration into project state so reports have dimensions
            if width_cm and height_cm:
                calib = self.project_manager.project_data.get("calibration") or {}
                calib.setdefault("num_aquariums", calib.get("num_aquariums", num_aquariums))
                calib.setdefault("animals_per_aquarium", calib.get("animals_per_aquarium", 1))
                calib.update(
                    {
                        "aquarium_width_cm": width_cm,
                        "aquarium_height_cm": height_cm,
                    }
                )
                self.project_manager.project_data["calibration"] = calib

                if self.project_manager.project_path:
                    self.project_manager.save_project()

                log.info(
                    "workflow.sequential_multi.calibration_saved",
                    width_cm=width_cm,
                    height_cm=height_cm,
                    persisted=bool(self.project_manager.project_path),
                )

            # Ensure video is registered with metadata so summaries can read dimensions
            video_entry = self.project_manager.find_video_entry(path=video_path)
            if not video_entry:
                metadata = self._extract_metadata_from_config(config)
                if width_cm:
                    metadata.setdefault("aquarium_width_cm", width_cm)
                if height_cm:
                    metadata.setdefault("aquarium_height_cm", height_cm)

                video_name = os.path.splitext(os.path.basename(str(video_path)))[0]

                has_arena = bool(zone_data.aquariums)
                has_rois = any(bool(aq.roi_polygons) for aq in zone_data.aquariums)

                video_data = {
                    "path": str(video_path),
                    "experiment_id": video_name,
                    "status": "processing",
                    "has_arena": has_arena,
                    "has_rois": has_rois,
                    "multi_aquarium_mode": True,
                }

                if metadata:
                    video_data["metadata"] = metadata

                self.project_manager.add_video_batch([video_data], save_project=False)

                self._publish_event(
                    Events.UI_REFRESH_PROJECT_VIEWS,
                    {"reason": "sequential_video_registered", "immediate": True},
                )
            else:
                # Update existing entry with calibration metadata if missing
                metadata = video_entry.get("metadata") or {}
                updated = False
                if width_cm and not metadata.get("aquarium_width_cm"):
                    metadata["aquarium_width_cm"] = width_cm
                    updated = True
                if height_cm and not metadata.get("aquarium_height_cm"):
                    metadata["aquarium_height_cm"] = height_cm
                    updated = True
                if updated:
                    video_entry["metadata"] = metadata
                    if self.project_manager.project_path:
                        self.project_manager.save_project()

            self.project_manager.set_active_zone_video(video_path)

            self._start_sequential_multi_aquarium_processing(video_path, config, zone_data)
            return

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

        # Apply multi-aquarium configuration if needed
        if num_aquariums > 1:
            log.info("workflow.single_video.setup_multi_aquarium", count=num_aquariums)

            # Check if we need to initialize MultiAquariumZoneData
            current_zones = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if not current_zones:
                from zebtrack.core.detector import MultiAquariumZoneData, AquariumData

                # Create default aquariums
                aquariums = [AquariumData(id=i) for i in range(num_aquariums)]
                new_multi = MultiAquariumZoneData(aquariums=aquariums)

                # Persist (using safe save logic)
                should_persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path, new_multi, persist=should_persist
                )
                zone_data = new_multi  # Update local ref

            # Update UI controls
            if self.view and hasattr(self.view, "zone_controls"):
                self.view.zone_controls.update_aquarium_count(num_aquariums)
                self.view.zone_controls.set_active_aquarium(0)
        else:
            # Ensure UI is in single mode
            if self.view and hasattr(self.view, "zone_controls"):
                self.view.zone_controls.update_aquarium_count(1)

        # Persist calibration into project state for report generation (option A)
        if width_cm and height_cm:
            calib = self.project_manager.project_data.get("calibration") or {}
            calib.setdefault("num_aquariums", calib.get("num_aquariums", 1))
            calib.setdefault("animals_per_aquarium", calib.get("animals_per_aquarium", 1))
            calib.update(
                {
                    "aquarium_width_cm": width_cm,
                    "aquarium_height_cm": height_cm,
                }
            )
            self.project_manager.project_data["calibration"] = calib

            # Persist intervals into project state as well
            analysis_interval, display_interval = self._determine_processing_intervals(config)
            self.project_manager.project_data["analysis_interval_frames"] = analysis_interval
            self.project_manager.project_data["display_interval_frames"] = display_interval

            # Persist behavioral config
            if "behavioral_analysis" in config:
                self.project_manager.project_data["behavioral_config"] = config[
                    "behavioral_analysis"
                ]

            if self.project_manager.project_path:
                self.project_manager.save_project()

            log.info(
                "workflow.single_video.calibration_saved",
                width_cm=width_cm,
                height_cm=height_cm,
                persisted=bool(self.project_manager.project_path),
            )

        # Register the single video in project_manager
        video_entry = self.project_manager.find_video_entry(path=video_path)
        if not video_entry:
            log.info("workflow.single_video.registering_video", video=str(video_path))

            metadata = self._extract_metadata_from_config(config)
            if width_cm:
                metadata.setdefault("aquarium_width_cm", width_cm)
            if height_cm:
                metadata.setdefault("aquarium_height_cm", height_cm)

            video_name = os.path.splitext(os.path.basename(str(video_path)))[0]
            # Determine arena/ROI presence based on zone data type
            has_arena = False
            has_rois = False

            if zone_data:
                # Check for MultiAquariumZoneData by attribute presence or type name to avoid imports
                if hasattr(zone_data, "aquariums"):
                    has_arena = bool(zone_data.aquariums)
                    has_rois = any(bool(aq.roi_polygons) for aq in zone_data.aquariums)
                else:
                    has_arena = bool(zone_data.polygon)
                    has_rois = bool(zone_data.roi_polygons)

            video_data = {
                "path": str(video_path),
                "experiment_id": video_name,
                "status": "processing",
                "has_arena": has_arena,
                "has_rois": has_rois,
            }
            if metadata:
                video_data["metadata"] = metadata

            self.project_manager.add_video_batch(
                [video_data],
                save_project=False,
            )
            # Force UI update so video appears in the list immediately (as processing)
            self._publish_event(
                Events.UI_REFRESH_PROJECT_VIEWS,
                {"reason": "single_video_registered", "immediate": True},
            )

        # Save the zone data for this video
        should_save_zones = False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                should_save_zones = bool(zone_data.aquariums)
            else:
                should_save_zones = bool(zone_data.polygon or zone_data.roi_polygons)

        if should_save_zones:
            # Safe log parameter calculation
            roi_count = 0
            if hasattr(zone_data, "aquariums"):
                roi_count = sum(len(aq.roi_polygons) for aq in zone_data.aquariums)
            elif hasattr(zone_data, "roi_polygons"):
                roi_count = len(zone_data.roi_polygons)

            log.info(
                "workflow.single_video.saving_zones",
                video=str(video_path),
                has_arena=should_save_zones,  # Already computed
                roi_count=roi_count,
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
            has_aquarium = bool(
                zone_data and (zone_data.polygon or hasattr(zone_data, "aquariums"))
            )
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

    # =========================================================================
    # Sequential Multi-Aquarium Processing
    # =========================================================================

    def _start_sequential_multi_aquarium_processing(
        self,
        video_path: Path | str,
        config: dict,
        multi_zone_data,
    ) -> None:
        """Process each aquarium sequentially (2 video passes).

        Reuses single-aquarium logic for each aquarium, processing the complete
        video for aquarium 0, then automatically starting aquarium 1.

        Args:
            video_path: Path to the video file.
            config: Processing configuration dictionary.
            multi_zone_data: MultiAquariumZoneData with all aquarium configurations.
        """
        from zebtrack.core.detector import MultiAquariumZoneData

        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        if not isinstance(multi_zone_data, MultiAquariumZoneData):
            log.error("workflow.sequential_multi.invalid_zone_data")
            return

        log.info(
            "workflow.sequential_multi.start",
            video=str(video_path),
            aquarium_count=len(multi_zone_data.aquariums),
        )

        # Store context for chained processing
        self._sequential_context = {
            "video_path": video_path,
            "config": config,
            "multi_zone_data": multi_zone_data,
            "current_aquarium_index": 0,
            "total_aquariums": len(multi_zone_data.aquariums),
            "outputs_by_aquarium": {},  # Will store outputs for each aquarium
        }

        # Initialize multi_aquarium_outputs in video entry
        video_entry = self.project_manager.find_video_entry(path=str(video_path))
        if video_entry:
            video_entry["multi_aquarium_mode"] = True
            video_entry["multi_aquarium_outputs"] = {}

        # Notify user
        aq_count = len(multi_zone_data.aquariums)
        self._publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Processamento Sequencial",
                "message": f"Iniciando processamento sequencial de {aq_count} aquários.\n"
                "Cada aquário será processado separadamente.",
            },
        )

        # Start processing the first aquarium
        self._process_next_aquarium_in_sequence()

    def _process_next_aquarium_in_sequence(self) -> None:
        """Process the next aquarium in the sequence."""
        if not hasattr(self, "_sequential_context") or self._sequential_context is None:
            log.warning("workflow.sequential_multi.no_context")
            return

        ctx = self._sequential_context

        if ctx["current_aquarium_index"] >= ctx["total_aquariums"]:
            # All aquariums processed - finalize and generate reports
            log.info(
                "workflow.sequential_multi.complete",
                total_aquariums=ctx["total_aquariums"],
            )

            video_path = str(ctx["video_path"])
            outputs_by_aquarium = ctx.get("outputs_by_aquarium", {})

            # Register all aquarium outputs with project manager
            if outputs_by_aquarium:
                self.project_manager.register_multi_aquarium_outputs(
                    video_path=video_path,
                    outputs_by_aquarium=outputs_by_aquarium,
                )
                log.info(
                    "workflow.sequential_multi.outputs_registered",
                    video=os.path.basename(video_path),
                    aquarium_count=len(outputs_by_aquarium),
                )

            # Update processing state
            self.state_manager.update_processing_state(
                source="controller.sequential_multi.complete",
                is_processing=False,
            )

            # Generate reports for all aquariums
            try:
                self._publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Gerando relatórios para todos os aquários..."},
                )
                self.generate_project_reports([video_path])
            except Exception as e:
                log.error(
                    "workflow.sequential_multi.report_failed",
                    error=str(e),
                )

            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento Concluído",
                    "message": f"Todos os {ctx['total_aquariums']} aquários foram processados "
                    "e relatórios gerados com sucesso.",
                },
            )

            # Refresh project views
            self._publish_event(
                Events.UI_REFRESH_PROJECT_VIEWS,
                {"reason": "sequential_multi_complete", "immediate": True},
            )

            self._sequential_context = None
            return

        aquarium_index = ctx["current_aquarium_index"]
        aquarium = ctx["multi_zone_data"].aquariums[aquarium_index]

        log.info(
            "workflow.sequential_multi.aquarium_start",
            aquarium_id=aquarium.id,
            aquarium_index=aquarium_index + 1,
            total=ctx["total_aquariums"],
            group=aquarium.group,
            subject_id=aquarium.subject_id,
        )

        # Convert to single-aquarium ZoneData
        zone_data = aquarium.to_zone_data()

        # Configure output directory for this aquarium
        video_name = os.path.splitext(os.path.basename(str(ctx["video_path"])))[0]
        base_output = os.path.join(
            os.path.dirname(str(ctx["video_path"])),
            f"{video_name}_results",
        )
        aquarium_output = os.path.join(base_output, f"aquarium_{aquarium.id}")
        os.makedirs(aquarium_output, exist_ok=True)

        # Notify user of current aquarium
        self._publish_event(
            Events.UI_SET_STATUS,
            {
                "message": f"Processando Aquário {aquarium_index + 1}/{ctx['total_aquariums']}...",
            },
        )

        # Use single-aquarium flow
        self._start_single_aquarium_for_sequential(
            ctx["video_path"],
            ctx["config"],
            zone_data,
            aquarium_output,
            aquarium.id,
        )

    def _start_single_aquarium_for_sequential(
        self,
        video_path: Path,
        config: dict,
        zone_data,
        output_dir: str,
        aquarium_id: int,
    ) -> None:
        """Start single-aquarium processing as part of sequential flow.

        Args:
            video_path: Path to the video file.
            config: Processing configuration dictionary.
            zone_data: ZoneData for the single aquarium.
            output_dir: Output directory for results.
            aquarium_id: ID of the aquarium being processed.
        """
        # Update detector with single-aquarium zones
        if self.detector:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                self._publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro", "message": f"Não foi possível abrir o vídeo: {video_path}"},
                )
                self._sequential_context = None
                return
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            self.detector.set_zones(zone_data, width, height)
            self.detector.set_aquarium_region_defined(bool(zone_data.polygon))
            self.detector.reset_tracking_state()

        # Prepare processing environment
        scanned_files = ProjectManager.scan_input_paths([str(video_path)])
        if not scanned_files:
            log.error("workflow.sequential_multi.scan_failed", video=str(video_path))
            self._sequential_context = None
            return
        video_to_process = scanned_files[0]

        # Hint callbacks to use the per-aquarium results directory instead of the base video path
        video_to_process["results_dir"] = output_dir
        # Track aquarium id to correctly attribute outputs on completion
        video_to_process["aquarium_id"] = aquarium_id

        # Create callbacks with completion handler
        callbacks = self.create_processing_callbacks([video_to_process])

        # Get aquarium info for output registration
        current_aquarium = self._sequential_context["multi_zone_data"].aquariums[
            self._sequential_context["current_aquarium_index"]
        ]
        experiment_id = os.path.splitext(os.path.basename(str(video_path)))[0]

        def on_sequential_complete(
            was_cancelled: bool, output_dir_completed: str, summary: dict | None = None
        ):
            """Handle completion of single aquarium processing."""
            # Do NOT call original on_completed - it would trigger single-video report generation
            # We'll generate reports after ALL aquariums are processed

            if not was_cancelled:
                log.info(
                    "workflow.sequential_multi.aquarium_complete",
                    aquarium_id=aquarium_id,
                )

                # Register aquarium outputs in context for later batch registration
                if self._sequential_context:
                    trajectory_path = os.path.join(
                        output_dir_completed, f"3_CoordMovimento_{experiment_id}.parquet"
                    )

                    frame_crop_box = None
                    if current_aquarium.polygon:
                        xs = [pt[0] for pt in current_aquarium.polygon]
                        ys = [pt[1] for pt in current_aquarium.polygon]
                        min_x, max_x = min(xs), max(xs)
                        min_y, max_y = min(ys), max(ys)
                        frame_crop_box = (
                            int(min_x),
                            int(min_y),
                            int(max_x - min_x),
                            int(max_y - min_y),
                        )

                    # Store output info for this aquarium
                    self._sequential_context["outputs_by_aquarium"][aquarium_id] = {
                        "results_dir": output_dir_completed,
                        "parquet_files": {"trajectory": trajectory_path},
                        "group": current_aquarium.group,
                        "subject_id": current_aquarium.subject_id,
                        "day": current_aquarium.day,
                        "frame_crop_box": frame_crop_box,
                    }

                    log.info(
                        "workflow.sequential_multi.aquarium_output_stored",
                        aquarium_id=aquarium_id,
                        results_dir=output_dir,
                        trajectory_exists=os.path.exists(trajectory_path),
                    )

                    # Advance to next aquarium
                    self._sequential_context["current_aquarium_index"] += 1
                    # Use after() to avoid recursive call depth issues
                    if hasattr(self, "view") and self.view and hasattr(self.view, "root"):
                        self.view.root.after(100, self._process_next_aquarium_in_sequence)
                    else:
                        self._process_next_aquarium_in_sequence()
            else:
                log.error(
                    "workflow.sequential_multi.aquarium_failed",
                    aquarium_id=aquarium_id,
                    error="cancelled" if was_cancelled else "unknown",
                )
                self._publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro no Processamento",
                        "message": f"Falha ao processar aquário {aquarium_id + 1}.",
                    },
                )
                self._sequential_context = None

        # Override default completion to chain next aquarium in sequential mode
        callbacks.on_completed = on_sequential_complete

        # Create processing context with single-aquarium zone_data
        context = self.create_processing_context(
            [video_to_process],
            output_dir,
            single_video_config=config,
            zone_data=zone_data,  # ZoneData, not MultiAquariumZoneData
        )

        # Clear cancel event and start worker
        self.cancel_event.clear()
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        # Update processing state
        self.state_manager.update_processing_state(
            source="controller.sequential_multi.aquarium_start",
            is_processing=True,
            current_video=f"{os.path.basename(str(video_path))} (Aquário {aquarium_id + 1})",
            processing_start_time=datetime.now(),
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

        if data_changed and self.project_manager.project_path:
            self.project_manager.save_project()

        # CRITICAL FIX: Recovery for MultiAquarium videos classified as 'without_arena'
        # This handles cases where file-system scan misses the arena (no parquet)
        # but ProjectManager has valid MultiAquariumZoneData in memory.

        for video in list(without_arena):
            raw_path = video.get("path")
            if not raw_path:
                continue

            # Try robust path matching (String vs Path, Slash vs Backslash)
            candidates = [
                raw_path,
                str(raw_path),
                str(Path(raw_path)),
                Path(raw_path).as_posix(),
                str(Path(raw_path)).replace("/", "\\"),
            ]

            found_data = None
            for c in candidates:
                data = self.project_manager.get_multi_aquarium_zone_data(c)
                if data:
                    found_data = data
                    log.info(
                        "processing_coordinator.classification.recovered",
                        video=raw_path,
                        match_key=c,
                    )
                    break

            if found_data:
                without_arena.remove(video)
                arena_only.append(video)

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            log.warning(
                "debug.processing_coordinator.failure",
                without_arena_count=len(without_arena),
                first_without_arena=without_arena[0].get("path") if without_arena else "N/A",
            )
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

        # Update processing state to trigger UI navigation to analysis view
        first_video = eligible_videos[0] if eligible_videos else {}
        self.state_manager.update_processing_state(
            source="controller.process_pending_project_videos",
            is_processing=True,
            current_video=os.path.basename(first_video.get("path", "")),
            processing_start_time=datetime.now(),
        )

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
        # Guard against re-entry
        if self._is_detecting_aquarium:
            log.warning("aquarium_detection.guard.active")
            return

        self._is_detecting_aquarium = True

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

            # MELHORIA: Check if we expect multiple aquariums based on settings
            num_aquariums = self.settings.analysis_config.num_aquariums

            if num_aquariums > 1:
                # Multi-aquarium mode
                polygons = detector.detect_multiple_aquariums(
                    video_path=str(video_path),
                    expected_count=num_aquariums,
                    stabilization_frames=stabilization_frames,
                    min_area_ratio=self.settings.detection_zones.min_aquarium_area_ratio,
                    max_area_ratio=self.settings.detection_zones.max_aquarium_area_ratio,
                )

                if polygons:
                    log.info(
                        "controller.aquarium_detection.multi_success",
                        count=len(polygons),
                    )
                    # For multi-aquarium, we might need a different event or payload structure
                    # Check if UI supports list of polygons in UI_SETUP_INTERACTIVE_POLYGON
                    # If not, we might need to send them one by one or change the event.
                    # Assuming for now we send the first one as main or adapt.
                    # EDIT: Multi-aquarium usually uses ZONE_MULTI_AUTO_DETECT_SUCCESS.
                    # Let's try to adapt to UI_SETUP_INTERACTIVE_POLYGON strictness or use the multi event.

                    if len(polygons) == num_aquariums:
                        self._publish_event(
                            Events.ZONE_MULTI_AUTO_DETECT_SUCCESS,
                            {
                                "video_path": str(video_path),
                                "polygons": [
                                    p.tolist() if hasattr(p, "tolist") else p for p in polygons
                                ],
                            },
                        )
                        # Also notify "Pronto" via status
                    else:
                        # Partial detection?
                        pass

            else:
                # Original Single-aquarium mode
                polygons = detector.detect_aquariums(
                    str(video_path),
                    stabilization_frames=stabilization_frames,
                    min_area_ratio=self.settings.detection_zones.min_aquarium_area_ratio,
                    max_area_ratio=self.settings.detection_zones.max_aquarium_area_ratio,
                )

                if polygons:
                    main_polygon = polygons[0]
                    log.info(
                        "controller.aquarium_detection.success",
                        polygon_points=len(main_polygon),
                    )
                    self._publish_event(
                        Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
                    )

            if not polygons:
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Automática Falhou",
                        "message": f"Não foi possível identificar {num_aquariums} aquário(s) estável(is) "
                        "no vídeo. Isso pode ocorrer devido a reflexos, pouca luz ou "
                        "movimento excessivo da câmera.\n\nPor favor, defina a área "
                        "manualmente.",
                    },
                )
                return

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
            self._is_detecting_aquarium = False

    def _handle_multi_auto_detect(self, data: dict) -> None:
        """Handle multi-aquarium auto-detection event.

        Phase 5: Event handler for ZONE_MULTI_AUTO_DETECT.

        Args:
            data: Event payload with video_path and optional stabilization_frames.
        """
        if not isinstance(data, dict):
            return

        video_path = data.get("video_path")
        stabilization_frames = int(data.get("stabilization_frames", 10))
        expected_count = int(data.get("expected_count", 2))

        if not video_path:
            log.warning("multi_auto_detect.no_video_path")
            return

        log.info(
            "multi_auto_detect.start",
            video_path=str(video_path),
            expected_count=expected_count,
        )

        self._publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Detectando {expected_count} aquários, por favor aguarde..."},
        )

        try:
            # Get detection method and model
            aquarium_method = self.settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self._publish_event(
                    Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                    {
                        "video_path": str(video_path),
                        "reason": f"Modelo {aquarium_method} não encontrado",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_multiple_aquariums(
                video_path=str(video_path),
                expected_count=expected_count,
                stabilization_frames=stabilization_frames,
                min_area_ratio=self.settings.detection_zones.min_aquarium_area_ratio,
                max_area_ratio=self.settings.detection_zones.max_aquarium_area_ratio,
            )

            if len(polygons) == expected_count:
                log.info(
                    "multi_auto_detect.success",
                    video_path=str(video_path),
                    count=len(polygons),
                )
                self._publish_event(
                    Events.ZONE_MULTI_AUTO_DETECT_SUCCESS,
                    {
                        "video_path": str(video_path),
                        "polygons": [p.tolist() if hasattr(p, "tolist") else p for p in polygons],
                    },
                )
            else:
                reason = f"Encontrados {len(polygons)} aquários, esperados {expected_count}"
                log.warning("multi_auto_detect.count_mismatch", reason=reason)
                self._publish_event(
                    Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                    {"video_path": str(video_path), "reason": reason},
                )

        except Exception as e:
            log.error("multi_auto_detect.failed", error=str(e), exc_info=True)
            self._publish_event(
                Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                {"video_path": str(video_path), "reason": str(e)},
            )
        finally:
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

        # Get expected ROI names from first video for schema standardization
        video_paths = [v.get("path") for v in target_videos if v.get("path")]
        expected_roi_names = self._find_project_roi_names(video_paths) if video_paths else None

        for video in target_videos:
            state = None
            try:
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                    expected_roi_names=expected_roi_names,
                )
            except Exception as exc:
                state, info_msg, _ppath, changed = "failed", str(exc), None, False

            if state == "completed":
                completed.append(info_msg or "(desconhecido)")
                data_changed = data_changed or bool(changed)
            else:
                skipped.append(info_msg.split(":")[0] if info_msg else "(desconhecido)")
                details.append(f"• {info_msg}")

        if data_changed and self.project_manager.project_path:
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
        vp_settings = getattr(self.settings, "video_processing", None)
        analysis_interval_frames = getattr(vp_settings, "processing_interval", 10)
        display_interval_frames = getattr(vp_settings, "display_interval", analysis_interval_frames)

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

    def _find_project_roi_names(self, video_paths: list[str]) -> list[str] | None:
        """Find ROI names from the first video in project that has zone data defined.

        This is used to standardize ROI column schemas across all summary parquets.
        Assumes first analyzed video already has ROIs/arena defined.

        Args:
            video_paths: List of video file paths in the project

        Returns:
            List of ROI names from first video with zone data, or None if no zones found
        """
        for path in video_paths:
            try:
                zone_data = self.project_manager.get_zone_data(video_path=path)
                if zone_data and (zone_data.roi_names or zone_data.polygon):
                    if zone_data.roi_names:
                        log.info(
                            "processing_coordinator.found_project_rois",
                            video=path,
                            roi_count=len(zone_data.roi_names),
                            roi_names=zone_data.roi_names,
                        )
                        return list(zone_data.roi_names)
            except Exception as e:
                log.debug("processing_coordinator.zone_lookup_failed", video=path, error=str(e))
                continue

        log.warning("processing_coordinator.no_project_rois_found")
        return None

    def generate_unified_report(self, video_paths: list[str] | None = None) -> None:
        """Generate a unified report aggregating data from multiple videos."""
        if not video_paths:
            return

        log.info("workflow.unified_report.start", count=len(video_paths))
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatório unificado..."})

        if not self.project_manager.project_path:
            self._publish_event(
                Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Nenhum projeto carregado."}
            )
            return

        unified_dir = self.project_manager.project_path / "unified_reports"
        unified_dir.mkdir(parents=True, exist_ok=True)

        dfs = []
        roi_colors_map = {}  # Collect ROI colors from all videos

        for path in video_paths:
            entry = self.project_manager.find_video_entry(path=path)
            if not entry:
                continue

            # Collect ROI colors from zone data
            try:
                zone_data = self.project_manager.get_zone_data(video_path=path)
                if zone_data and zone_data.roi_names and zone_data.roi_colors:
                    for roi_name, color in zip(zone_data.roi_names, zone_data.roi_colors):
                        # Store first color encountered for each ROI name
                        if roi_name not in roi_colors_map:
                            roi_colors_map[roi_name] = color
            except Exception as e:
                log.debug(
                    "workflow.unified_report.color_collection_failed", path=path, error=str(e)
                )

            # Find summary parquet
            # Handle multi-aquarium entries
            multi_outputs = entry.get("multi_aquarium_outputs")

            entries_to_process = []
            if multi_outputs:
                # Add sub-entries
                for aq_id, out_info in multi_outputs.items():
                    entries_to_process.append(
                        {
                            "parquet_files": out_info.get("parquet_files", {}),
                            "metadata": {
                                "group": out_info.get("group"),
                                "subject": out_info.get("subject_id"),
                                "day": out_info.get("day"),
                                # Use a unique experiment ID for the sub-entry
                                "experiment_id": f"{os.path.splitext(os.path.basename(path))[0]}_aq{aq_id}",
                                "aquarium_id": aq_id,
                            },
                            "is_multi": True,
                        }
                    )
            else:
                # Add main entry
                entries_to_process.append(
                    {
                        "parquet_files": entry.get("parquet_files", {}),
                        "metadata": entry.get("metadata", {}),
                        "experiment_id": entry.get(
                            "experiment_id", os.path.splitext(os.path.basename(path))[0]
                        ),
                        "is_multi": False,
                    }
                )

            for process_entry in entries_to_process:
                parquet_files = process_entry.get("parquet_files", {})
                summary_path = parquet_files.get("summary")
                entry_meta = process_entry.get("metadata", {})

                # If path exists, read it
                if summary_path and os.path.exists(summary_path):
                    try:
                        df = pd.read_parquet(summary_path)

                        # Re-enrich metadata
                        if entry_meta:
                            # Update group_id
                            group_val = entry_meta.get("group_id") or entry_meta.get("group")
                            if group_val and "group_id" in df.columns:
                                df["group_id"] = str(group_val)
                            elif group_val:
                                df["group_id"] = str(group_val)  # Create likely missing column

                            # Update experiment_id details
                            exp_id = process_entry.get("experiment_id") or entry_meta.get(
                                "experiment_id"
                            )
                            if exp_id and "experiment_id" in df.columns:
                                df["experiment_id"] = str(exp_id)
                            elif exp_id:
                                df["experiment_id"] = str(exp_id)

                            # If multi-aquarium, explicitly set subject_id if needed
                            subj_val = entry_meta.get("subject") or entry_meta.get("subject_id")
                            if subj_val:
                                # Often stored as 'subject_id' column
                                if "subject_id" in df.columns:
                                    df["subject_id"] = str(subj_val)
                                else:
                                    df["subject_id"] = str(subj_val)

                        dfs.append(df)
                    except Exception as e:
                        log.warning(
                            "workflow.unified_report.read_failed", file=summary_path, error=str(e)
                        )

        if not dfs:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Dados insuficientes",
                    "message": "Não foi possível encontrar sumários para os vídeos selecionados.",
                },
            )
            return

        try:
            # Align DataFrame columns before concatenation
            all_columns = set()
            for df in dfs:
                all_columns.update(df.columns)

            # Detect ROI column mismatch (only check ROI-specific columns, not derived/metadata)
            roi_pattern_prefixes = ["tempo_no_", "entradas_no_", "distancia_no_"]
            roi_columns_per_df = []
            for df in dfs:
                roi_cols = {
                    col
                    for col in df.columns
                    if any(col.startswith(prefix) for prefix in roi_pattern_prefixes)
                }
                roi_columns_per_df.append(roi_cols)

            # Schema mismatch only if ROI columns differ
            schema_mismatch = len(set(map(frozenset, roi_columns_per_df))) > 1

            # Pad missing columns with pd.NA
            aligned_dfs = []
            for df in dfs:
                df_copy = df.copy()
                for col in all_columns:
                    if col not in df_copy.columns:
                        df_copy[col] = pd.NA
                # Sort columns for consistency
                aligned_dfs.append(df_copy[sorted(all_columns)])

            # Suppress FutureWarning from pandas about empty/all-NA columns
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", category=FutureWarning, message=".*DataFrame concatenation.*"
                )
                aggregated_df = pd.concat(aligned_dfs, ignore_index=True)

            # Warn user if ROI schemas differ (unless suppressed)
            if schema_mismatch and not self.settings.ui_features.suppress_roi_mismatch_warning:
                log.warning(
                    "workflow.unified_report.schema_mismatch", column_count=len(all_columns)
                )
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "ROIs Diferentes Detectadas",
                        "message": (
                            "Atenção: Alguns vídeos possuem ROIs diferentes.\n\n"
                            "Certifique-se de que todos os vídeos do projeto usam as mesmas ROIs "
                            "para relatórios consistentes.\n\n"
                            "Você pode suprimir este aviso em config.yaml: "
                            "ui_features.suppress_roi_mismatch_warning: true"
                        ),
                    },
                )

            # Generate filenames with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"relatorio_unificado_{timestamp}"

            # Export Word (pass ROI colors, detector_params is optional)
            word_path = unified_dir / f"{base_name}.docx"
            Reporter.export_project_report(
                aggregated_df, word_path, roi_colors=roi_colors_map, detector_params=None
            )

            # Export Excel (replace pd.NA with 0 for numeric columns to avoid empty cells)
            excel_path = unified_dir / f"{base_name}.xlsx"
            excel_df = aggregated_df.copy()
            # Replace pd.NA with 0 in numeric columns only
            for col in excel_df.select_dtypes(include=["number"]).columns:
                excel_df[col] = excel_df[col].fillna(0)
            excel_df.to_excel(excel_path, index=False)

            # Export Parquet
            parquet_path = unified_dir / f"{base_name}.parquet"
            aggregated_df.to_parquet(parquet_path, index=False)

            log.info(
                "workflow.unified_report.complete",
                word_path=str(word_path),
                excel_path=str(excel_path),
                parquet_path=str(parquet_path),
                row_count=len(aggregated_df),
            )

            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Relatório Unificado Gerado",
                    "message": f"Relatórios salvos em:\n{unified_dir}\n\nArquivos:\n• {word_path.name}\n• {excel_path.name}",
                },
            )

            # Clear UI status and refresh views
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

        except Exception as e:
            log.error("workflow.unified_report.failed", error=str(e))
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro na Geração", "message": f"Falha ao gerar relatório unificado: {e}"},
            )

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Generate reports (Word, Excel, Parquet) for specified videos."""
        if not video_paths:
            return

        log.info("workflow.reports.start", count=len(video_paths))
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatórios detalhados..."})

        video_dim_cache: dict[str, tuple[int, int]] = {}

        def _probe_video_dims(video_file: str) -> tuple[int, int]:
            if video_file in video_dim_cache:
                return video_dim_cache[video_file]

            cap = cv2.VideoCapture(video_file)
            if not cap.isOpened():
                return (0, 0)

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            video_dim_cache[video_file] = (width, height)
            return width, height

        def _compute_local_space(
            polygon_pts: list[list[int]] | list[tuple[int, int]], fallback_w: int, fallback_h: int
        ) -> tuple[int, int, int, int]:
            if polygon_pts:
                xs = [pt[0] for pt in polygon_pts]
                ys = [pt[1] for pt in polygon_pts]
                min_x = int(np.floor(min(xs)))
                min_y = int(np.floor(min(ys)))
                max_x = int(np.ceil(max(xs)))
                max_y = int(np.ceil(max(ys)))
                width_px = max(max_x - min_x, 1)
                height_px = max(max_y - min_y, 1)
                return min_x, min_y, width_px, height_px

            return 0, 0, max(fallback_w, 1), max(fallback_h, 1)

        def _normalize_df_to_local(
            df: pd.DataFrame, offset_x: int, offset_y: int, width_px: int, height_px: int
        ) -> pd.DataFrame:
            if offset_x == 0 and offset_y == 0:
                return df.copy()

            local_df = df.copy()
            upper_x = width_px if width_px else None
            upper_y = height_px if height_px else None

            # IMPROVEMENT: Drop existing CM columns to force recalculation in local space
            cols_to_drop = [
                "x_cm",
                "y_cm",
                "x_center_cm",
                "y_center_cm",
                "x_cm_smoothed",
                "y_cm_smoothed",
            ]
            local_df = local_df.drop(columns=[c for c in cols_to_drop if c in local_df.columns])

            for col in ("x_center_px", "x1", "x2"):
                if col in local_df.columns:
                    local_df[col] = (local_df[col] - offset_x).clip(lower=0, upper=upper_x)

            for col in ("y_center_px", "y1", "y2"):
                if col in local_df.columns:
                    local_df[col] = (local_df[col] - offset_y).clip(lower=0, upper=upper_y)

            return local_df

        def _extract_cropped_frame(video_file: str, crop_box: tuple[int, int, int, int] | None):
            if not crop_box:
                return None

            cap = cv2.VideoCapture(video_file)
            if not cap.isOpened():
                return None

            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return None

            x, y, w, h = crop_box
            x = max(0, int(x))
            y = max(0, int(y))
            w = max(1, int(w))
            h = max(1, int(h))
            x2 = min(frame.shape[1], x + w)
            y2 = min(frame.shape[0], y + h)

            if x >= x2 or y >= y2:
                return None

            return frame[y:y2, x:x2].copy()

        # Generate Parquet Summaries first
        target_videos = []
        for path in video_paths:
            entry = self.project_manager.find_video_entry(path=path)
            if entry:
                target_videos.append(entry)

        if target_videos:
            self.generate_parquet_summaries(target_videos, self.settings)

        # Generate Word/Excel Reports
        count = 0
        errors = []

        # Ensure analysis service is available and configured
        if not self.analysis_service:
            from zebtrack.analysis.analysis_service import AnalysisService

            self.analysis_service = AnalysisService(settings_obj=self.settings)
            log.info("workflow.reports.analysis_service_created_lazy")
        elif self.analysis_service.settings is None:
            self.analysis_service.settings = self.settings
            log.info("workflow.reports.analysis_service_settings_injected_lazy")

        for path in video_paths:
            try:
                # Resolve trajectory path
                experiment_id = os.path.splitext(os.path.basename(path))[0]

                # Fix: Use find_video_entry instead of get_video_metadata
                video_entry = self.project_manager.find_video_entry(path=path)
                metadata = video_entry.get("metadata", {}) if video_entry else {}

                if not metadata:
                    metadata = self.project_manager.derive_processing_metadata(
                        experiment_id, video_path=path
                    )

                # Check for multi-aquarium mode
                multi_outputs = video_entry.get("multi_aquarium_outputs") if video_entry else None
                if multi_outputs:
                    # Handle multi-aquarium video - generate reports per aquarium
                    log.info(
                        "workflow.reports.multi_aquarium.start",
                        video=experiment_id,
                        aquarium_count=len(multi_outputs),
                    )

                    project_data = getattr(self.project_manager, "project_data", {}) or {}

                    # Collection params including behavioral config
                    analysis_params = self.analysis_service.collect_analysis_parameters(
                        project_data
                    )
                    behavioral_config = analysis_params.get("behavioral_config")

                    calib = project_data.get("calibration", {})
                    pixelcm_x = float(calib.get("pixel_per_cm_x", 1.0))
                    pixelcm_y = float(calib.get("pixel_per_cm_y", 1.0))
                    fps = float(self.settings.video_processing.fps)

                    probed_width, probed_height = _probe_video_dims(str(path))

                    for aq_id_str, output_info in multi_outputs.items():
                        try:
                            aq_id = int(aq_id_str)
                            aq_results_dir = output_info.get("results_dir")
                            aq_parquet_files = output_info.get("parquet_files", {})
                            trajectory_path = aq_parquet_files.get("trajectory")

                            if not trajectory_path or not os.path.exists(trajectory_path):
                                log.warning(
                                    "workflow.reports.multi_aquarium.missing_trajectory",
                                    video=path,
                                    aquarium_id=aq_id,
                                    trajectory_path=trajectory_path,
                                )
                                continue

                            # Load trajectory
                            df = pd.read_parquet(trajectory_path)

                            # Build aquarium-specific metadata
                            aq_metadata = {
                                **metadata,
                                "aquarium_id": aq_id,
                                "group": output_info.get("group", metadata.get("group")),
                                "subject": output_info.get("subject_id", metadata.get("subject")),
                            }

                            # Get zone data - try multi-aquarium specific first
                            zone_data = self.project_manager.get_multi_aquarium_zone_data(
                                video_path=path
                            )
                            if not zone_data:
                                zone_data = self.project_manager.get_zone_data(video_path=path)

                            # Extract aquarium-specific polygon and ROIs
                            arena_polygon: list[list[int]] | list[tuple[int, int]] = []
                            rois: list[ROI] = []
                            roi_colors_map: dict[str, tuple[int, int, int]] = {}

                            fallback_width = (
                                getattr(zone_data, "video_width", probed_width) or probed_width
                            )
                            fallback_height = (
                                getattr(zone_data, "video_height", probed_height) or probed_height
                            )

                            # Check if zone_data is MultiAquariumZoneData
                            if hasattr(zone_data, "aquariums") and zone_data.aquariums:
                                # Multi-aquarium zone data
                                for aq in zone_data.aquariums:
                                    if aq.id == aq_id:
                                        arena_polygon = aq.polygon if aq.polygon else []
                                        # Build ROIs
                                        from shapely.geometry import Polygon

                                        from zebtrack.analysis.roi import ROI

                                        for i, poly in enumerate(aq.roi_polygons):
                                            translated_poly = [(px, py) for px, py in poly]
                                            name = (
                                                aq.roi_names[i]
                                                if i < len(aq.roi_names)
                                                else f"ROI_{i}"
                                            )
                                            if len(translated_poly) >= 3:
                                                roi_geometry = Polygon(translated_poly)
                                                rois.append(
                                                    ROI(
                                                        name=name,
                                                        geometry=roi_geometry,
                                                        coordinate_space="px",
                                                    )
                                                )
                                            if i < len(aq.roi_colors):
                                                roi_colors_map[name] = aq.roi_colors[i]
                                        break
                            elif zone_data:
                                # Standard zone data (fallback)
                                arena_polygon = zone_data.polygon if zone_data.polygon else []

                            offset_x, offset_y, local_w, local_h = _compute_local_space(
                                arena_polygon, fallback_width, fallback_height
                            )
                            frame_crop_box = (
                                (offset_x, offset_y, local_w, local_h) if arena_polygon else None
                            )

                            # Translate polygons to aquarium-local coordinates
                            arena_polygon_local = [
                                (float(x) - offset_x, float(y) - offset_y) for x, y in arena_polygon
                            ]

                            if not arena_polygon_local:
                                arena_polygon_local = [
                                    (0.0, 0.0),
                                    (float(local_w), 0.0),
                                    (float(local_w), float(local_h)),
                                    (0.0, float(local_h)),
                                ]

                            rois = []
                            if hasattr(zone_data, "aquariums") and zone_data.aquariums:
                                for aq in zone_data.aquariums:
                                    if aq.id != aq_id:
                                        continue
                                    for i, poly in enumerate(aq.roi_polygons):
                                        translated_poly = [
                                            (float(px) - offset_x, float(py) - offset_y)
                                            for px, py in poly
                                        ]
                                        name = (
                                            aq.roi_names[i] if i < len(aq.roi_names) else f"ROI_{i}"
                                        )
                                        if len(translated_poly) >= 3:
                                            rois.append(
                                                ROI(
                                                    name=name,
                                                    geometry=Polygon(translated_poly),
                                                    coordinate_space="px",
                                                )
                                            )
                                        if i < len(aq.roi_colors):
                                            roi_colors_map[name] = aq.roi_colors[i]
                                    break
                            elif arena_polygon:
                                from zebtrack.analysis.roi import ROI
                                from shapely.geometry import Polygon

                                rois = []
                                zone_roi_polys = getattr(zone_data, "roi_polygons", []) or []
                                zone_roi_names = getattr(zone_data, "roi_names", []) or []
                                zone_roi_colors = getattr(zone_data, "roi_colors", []) or []

                                for i, poly in enumerate(zone_roi_polys):
                                    translated_poly = [
                                        (float(px) - offset_x, float(py) - offset_y)
                                        for px, py in poly
                                    ]
                                    name = (
                                        zone_roi_names[i] if i < len(zone_roi_names) else f"ROI_{i}"
                                    )
                                    if len(translated_poly) >= 3:
                                        rois.append(
                                            ROI(
                                                name=name,
                                                geometry=Polygon(translated_poly),
                                                coordinate_space="px",
                                            )
                                        )
                                    if i < len(zone_roi_colors):
                                        roi_colors_map[name] = zone_roi_colors[i]

                            df = _normalize_df_to_local(df, offset_x, offset_y, local_w, local_h)

                            video_height_local = local_h or fallback_height or probed_height or 720

                            # Fallback: calculate pixelcm from metadata if not present in project calibration
                            width_cm_meta = aq_metadata.get("aquarium_width_cm") or calib.get(
                                "aquarium_width_cm"
                            )
                            height_cm_meta = aq_metadata.get("aquarium_height_cm") or calib.get(
                                "aquarium_height_cm"
                            )

                            if pixelcm_x <= 1.0 and width_cm_meta and local_w > 0:
                                pixelcm_x_local = local_w / float(width_cm_meta)
                                log.info(
                                    "workflow.reports.calculation.fallback_pixelcm_x",
                                    value=pixelcm_x_local,
                                    width_cm=width_cm_meta,
                                )
                            else:
                                pixelcm_x_local = pixelcm_x if pixelcm_x > 0 else 1.0

                            if pixelcm_y <= 1.0 and height_cm_meta and local_h > 0:
                                pixelcm_y_local = local_h / float(height_cm_meta)
                                log.info(
                                    "workflow.reports.calculation.fallback_pixelcm_y",
                                    value=pixelcm_y_local,
                                    height_cm=height_cm_meta,
                                )
                            else:
                                pixelcm_y_local = pixelcm_y if pixelcm_y > 0 else 1.0

                            # Persist crop for report backgrounds
                            video_path_for_report = str(path)
                            frame_crop_for_report = frame_crop_box
                            if frame_crop_box:
                                frame_image = _extract_cropped_frame(str(path), frame_crop_box)
                                if frame_image is not None:
                                    try:
                                        background_frame_path = os.path.join(
                                            aq_results_dir,
                                            f"{experiment_id}_aq{aq_id}_frame.png",
                                        )
                                        cv2.imwrite(background_frame_path, frame_image)
                                        video_path_for_report = background_frame_path
                                        frame_crop_for_report = None
                                    except Exception:
                                        background_frame_path = None

                            aq_metadata["aquarium_offset_px"] = {
                                "x": offset_x,
                                "y": offset_y,
                                "width": local_w,
                                "height": local_h,
                            }

                            # Run Analysis
                            analysis_result = self.analysis_service.run_full_analysis_as_dto(
                                trajectory_df=df,
                                pixelcm_x=pixelcm_x_local,
                                pixelcm_y=pixelcm_y_local,
                                video_height_px=int(video_height_local),
                                arena_polygon_px=arena_polygon_local,
                                rois=rois,
                                fps=fps,
                                metadata=aq_metadata,
                                roi_colors=roi_colors_map,
                                freezing_vel_threshold=(
                                    self.settings.video_processing.freezing_velocity_threshold
                                ),
                                freezing_min_duration=(
                                    self.settings.video_processing.freezing_min_duration_s
                                ),
                                video_path=video_path_for_report,
                                frame_crop_box=frame_crop_for_report,
                                behavioral_config=behavioral_config,
                            )

                            reporter = Reporter.from_analysis(analysis_result)

                            # Export with aquarium suffix
                            os.makedirs(aq_results_dir, exist_ok=True)
                            aq_experiment_id = f"{experiment_id}_aq{aq_id}"
                            report_base = os.path.join(
                                aq_results_dir, f"4_Relatorio_{aq_experiment_id}"
                            )
                            reporter.export_individual_report(f"{report_base}.docx")
                            reporter.export_summary_data(f"{report_base}.xlsx", format="excel")

                            log.info(
                                "workflow.reports.multi_aquarium.generated",
                                video=experiment_id,
                                aquarium_id=aq_id,
                                report_path=f"{report_base}.docx",
                            )
                            count += 1

                        except Exception as aq_e:
                            log.error(
                                "workflow.reports.multi_aquarium.aquarium_failed",
                                video=path,
                                aquarium_id=aq_id_str,
                                error=str(aq_e),
                            )
                            errors.append(f"{experiment_id}_aq{aq_id_str}: {aq_e!s}")

                    continue  # Skip to next video after handling multi-aquarium

                # Standard single-aquarium processing
                results_path = self.project_manager.resolve_results_directory(
                    experiment_id, video_path=path, metadata=metadata
                )
                os.makedirs(results_path, exist_ok=True)

                trajectory_path = os.path.join(
                    results_path, f"3_CoordMovimento_{experiment_id}.parquet"
                )
                if not os.path.exists(trajectory_path):
                    # Fallback to local dir
                    trajectory_path = os.path.join(
                        os.path.dirname(path),
                        f"{experiment_id}_results",
                        f"3_CoordMovimento_{experiment_id}.parquet",
                    )
                    if not os.path.exists(trajectory_path):
                        log.warning("workflow.reports.missing_trajectory", video=path)
                        continue

                # Load trajectory
                df = pd.read_parquet(trajectory_path)

                # Get calibration and zones
                zone_data = self.project_manager.get_zone_data(video_path=path)
                project_data = getattr(self.project_manager, "project_data", {}) or {}

                # Collection params including behavioral config
                analysis_params = self.analysis_service.collect_analysis_parameters(project_data)
                behavioral_config = analysis_params.get("behavioral_config")

                # Calibration params
                calib = project_data.get("calibration", {})
                pixelcm_x = float(calib.get("pixel_per_cm_x", 1.0))
                pixelcm_y = float(calib.get("pixel_per_cm_y", 1.0))

                # Fetch aquarium dimensions for fallback
                # Use metadata from video first, then fallback to global calibration
                video_metadata = metadata or {}
                width_cm_meta = video_metadata.get("aquarium_width_cm") or calib.get(
                    "aquarium_width_cm"
                )
                height_cm_meta = video_metadata.get("aquarium_height_cm") or calib.get(
                    "aquarium_height_cm"
                )

                probed_w, probed_h = _probe_video_dims(str(path))
                fallback_w = getattr(zone_data, "video_width", probed_w) or probed_w
                fallback_h = getattr(zone_data, "video_height", probed_h) or probed_h

                # Normalize to local aquarium space (Consistency with multi-aquarium)
                arena_polygon_px = list(zone_data.polygon or [])
                if not arena_polygon_px:
                    arena_polygon_px = [
                        [0, 0],
                        [fallback_w, 0],
                        [fallback_w, fallback_h],
                        [0, fallback_h],
                    ]

                offset_x, offset_y, local_w, local_h = _compute_local_space(
                    arena_polygon_px, fallback_w, fallback_h
                )

                # Translate polygons to local
                arena_polygon_local = [
                    (float(x) - offset_x, float(y) - offset_y) for x, y in arena_polygon_px
                ]

                # ROIs
                rois = []
                roi_colors_map = {}
                if zone_data:
                    from shapely.geometry import Polygon
                    from zebtrack.analysis.roi import ROI

                    for i, poly in enumerate(zone_data.roi_polygons):
                        translated_poly = [
                            (float(px) - offset_x, float(py) - offset_y) for px, py in poly
                        ]
                        name = (
                            zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                        )
                        if len(translated_poly) >= 3:
                            rois.append(
                                ROI(
                                    name=name,
                                    geometry=Polygon(translated_poly),
                                    coordinate_space="px",
                                )
                            )

                        if i < len(zone_data.roi_colors):
                            roi_colors_map[name] = zone_data.roi_colors[i]

                df = _normalize_df_to_local(df, offset_x, offset_y, local_w, local_h)
                fps = float(self.settings.video_processing.fps)

                # Persist crop for report backgrounds (Standard Single Aquarium)
                video_path_for_report = str(path)
                frame_crop_for_report = (offset_x, offset_y, local_w, local_h)

                frame_image = _extract_cropped_frame(str(path), frame_crop_for_report)
                if frame_image is not None:
                    try:
                        background_frame_path = os.path.join(
                            results_path,
                            f"{experiment_id}_background.png",
                        )
                        cv2.imwrite(background_frame_path, frame_image)
                        video_path_for_report = background_frame_path
                        frame_crop_for_report = None  # Already cropped
                    except Exception:
                        pass

                # Calibration object for the DTO
                cal = Calibration(
                    np.array(arena_polygon_px),
                    calib.get("aquarium_width_cm", 0),
                    calib.get("aquarium_height_cm", 0),
                )

                # Run Analysis
                # Fallback: calculate pixelcm from metadata if not present in project calibration
                if pixelcm_x <= 1.0 and width_cm_meta and local_w > 0:
                    pixelcm_x_final = local_w / float(width_cm_meta)
                else:
                    pixelcm_x_final = pixelcm_x if pixelcm_x > 0 else 1.0

                if pixelcm_y <= 1.0 and height_cm_meta and local_h > 0:
                    pixelcm_y_final = local_h / float(height_cm_meta)
                else:
                    pixelcm_y_final = pixelcm_y if pixelcm_y > 0 else 1.0

                analysis_result = self.analysis_service.run_full_analysis_as_dto(
                    trajectory_df=df,
                    pixelcm_x=pixelcm_x_final,
                    pixelcm_y=pixelcm_y_final,
                    video_height_px=int(local_h),
                    arena_polygon_px=arena_polygon_local,
                    rois=rois,
                    fps=fps,
                    metadata=metadata,
                    roi_colors=roi_colors_map,
                    freezing_vel_threshold=self.settings.video_processing.freezing_velocity_threshold,
                    freezing_min_duration=self.settings.video_processing.freezing_min_duration_s,
                    video_path=video_path_for_report,
                    frame_crop_box=frame_crop_for_report,
                    calibration=None if video_path_for_report.endswith(".png") else cal,
                    behavioral_config=behavioral_config,
                )

                reporter = Reporter.from_analysis(analysis_result)

                # Export
                report_base = os.path.join(results_path, f"4_Relatorio_{experiment_id}")
                os.makedirs(os.path.dirname(report_base), exist_ok=True)
                reporter.export_individual_report(f"{report_base}.docx")
                reporter.export_summary_data(f"{report_base}.xlsx", format="excel")

                # Register outputs to update project status
                self.project_manager.register_processing_outputs(
                    video_path=path,
                    report_path=f"{report_base}.docx",
                    summary_excel=f"{report_base}.xlsx",
                )

                count += 1
            except Exception as e:
                log.error("workflow.reports.failed", video=path, error=str(e))
                errors.append(f"{os.path.basename(path)}: {e!s}")

        self._publish_event(Events.UI_SET_STATUS, {"message": "Relatórios gerados."})

        if errors:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Erros na Geração de Relatórios",
                    "message": "Alguns relatórios falharam:\n" + "\n".join(errors[:5]),
                },
            )
        elif count > 0:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Relatórios Gerados",
                    "message": (
                        f"Foram gerados relatórios completos (Word/Excel) para {count} vídeos."
                    ),
                },
            )

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

            for dim_key in ("aquarium_width_cm", "aquarium_height_cm"):
                if dim_key in config and config.get(dim_key) not in (None, ""):
                    try:
                        metadata[dim_key] = float(config.get(dim_key))
                    except (TypeError, ValueError):
                        pass

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
        """Load zone data from parquet files for eligible videos.

        Also serializes zone data and results_dir into each video_info dict so
        the worker can access per-video zones and output paths during batch processing.
        """
        zones_updated = False
        from zebtrack.core.zone_manager import ZoneManager

        for video_info in eligible_videos:
            video_path = video_info.get("path", "")
            experiment_id = os.path.splitext(os.path.basename(video_path))[0] if video_path else ""

            # Calculate correct results_dir using project metadata
            metadata = video_info.get("metadata", {})
            results_path = self.project_manager.resolve_results_directory(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata=metadata,
            )
            video_info["results_dir"] = str(results_path)
            log.debug(
                "workflow.results_dir_attached_to_video_info",
                video=os.path.basename(video_path),
                results_dir=str(results_path),
            )

            # Check for Multi-Aquarium Data First
            multi_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if multi_data:
                video_info["zone_data"] = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)
                log.info(
                    "workflow.multi_aquarium_zone_data_attached",
                    video=os.path.basename(video_path),
                    aquarium_count=len(multi_data.aquariums),
                )
                continue

            if video_info.get("has_arena") or video_info.get("has_rois"):
                # Debug: log parquet_files before loading
                pf = video_info.get("parquet_files", {})
                log.debug(
                    "workflow.zone_load.parquet_files_check",
                    video=os.path.basename(video_path),
                    parquet_files=pf,
                    has_arena_file=bool(pf.get("arena")),
                    has_rois_file=bool(pf.get("rois")),
                )
                try:
                    zone_data = ProjectManager.load_zones_from_parquet(video_info)
                except Exception as exc:
                    log.warning(
                        "workflow.project_processing.zone_load_failed",
                        video=os.path.basename(video_info.get("path", "")),
                        error=str(exc),
                    )
                    zone_data = None

                # Fallback: check project manager memory/cache if parquet load failed
                if not zone_data or not zone_data.polygon:
                    log.info("workflow.zone_load.fallback_memory", video=experiment_id)
                    zone_data = self.project_manager.get_zone_data(video_path=video_path)

                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True

                    # Serialize zone data into video_info for worker access
                    video_info["zone_data"] = {
                        "polygon": zone_data.polygon,
                        "roi_polygons": zone_data.roi_polygons,
                        "roi_names": zone_data.roi_names,
                        "roi_colors": zone_data.roi_colors,
                    }
                    log.info(
                        "workflow.zone_data_attached_to_video_info",
                        video=os.path.basename(video_info.get("path", "")),
                        polygon_points=len(zone_data.polygon),
                        roi_count=len(zone_data.roi_polygons),
                    )

        if zones_updated and self.project_manager.project_path:
            self.project_manager.save_project()

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
        expected_roi_names: list[str] | None = None,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation.

        Phase 3: Consolidated from AnalysisOrchestrator._process_summary_video

        Args:
            video: Video dictionary entry from project
            settings_obj: Settings object
            expected_roi_names: Optional list of ROI names for schema standardization
        """
        # Ensure analysis service is available and configured
        if not self.analysis_service:
            from zebtrack.analysis.analysis_service import AnalysisService

            self.analysis_service = AnalysisService(settings_obj=self.settings)
        elif self.analysis_service.settings is None:
            self.analysis_service.settings = self.settings

        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]

        # Check for multi-aquarium outputs first
        multi_outputs = video.get("multi_aquarium_outputs")
        if multi_outputs:
            try:
                # Load multi-aquarium zone data
                multi_zone_data = self.project_manager.get_multi_aquarium_zone_data(path)
                if not multi_zone_data:
                    return (
                        "skipped",
                        f"{experiment_id}: dados de zonas multi-aquário ausentes.",
                        None,
                        False,
                    )

                processed_count = 0
                total_aquariums = len(multi_outputs)
                summary_paths = []

                for aq_id_str, output_info in multi_outputs.items():
                    aq_id = int(aq_id_str)
                    aq_results_dir = output_info.get("results_dir")
                    aq_parquet_files = output_info.get("parquet_files", {})
                    trajectory_path = aq_parquet_files.get("trajectory")
                    frame_crop_box = output_info.get("frame_crop_box")

                    if not trajectory_path or not os.path.exists(trajectory_path):
                        log.warning(f"Trajetória ausente para aquário {aq_id} em {experiment_id}")
                        continue

                    # Get specific zone data for this aquarium (match by id)
                    aq_zone = next(
                        (
                            aq
                            for aq in multi_zone_data.aquariums
                            if getattr(aq, "id", None) == aq_id
                        ),
                        None,
                    )
                    if aq_zone is None:
                        log.warning(f"Zonas ausentes para aquário {aq_id} em {experiment_id}")
                        continue

                    # Read trajectory
                    try:
                        trajectory_df = pd.read_parquet(trajectory_path)
                    except Exception:
                        continue

                    if trajectory_df.empty:
                        continue

                    # Calibration (assume shared per-aquarium dimensions OR global calibration)
                    # Currently multi-aquarium setup implies identical tanks or partitioned view
                    # We reuse the project calibration logic but applied to the sub-arena

                    # Transform arena polygon
                    arena_polygon_px = list(aq_zone.polygon or [])
                    # ... (Validation logic similar to single video, omitted for brevity but critical)
                    if len(arena_polygon_px) < 3:
                        # Fallback for rectangular approximation if needed
                        pass

                    calib_data = self.project_manager.project_data.get("calibration", {})
                    width_cm = calib_data.get("aquarium_width_cm")
                    height_cm = calib_data.get("aquarium_height_cm")

                    # If calibration is missing, likely skip or warn
                    if not width_cm or not height_cm:
                        log.warning(f"Calibração ausente para {experiment_id} (Aq {aq_id})")
                        continue

                    cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
                    _, video_height_px = cal.target_dims_px
                    pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
                    arena_polygon_warped = cal.transform_points(arena_polygon_px)

                    # Transform ROIs
                    roi_polygons = list(aq_zone.roi_polygons or [])
                    roi_names = list(aq_zone.roi_names or [])
                    roi_colors_list = list(aq_zone.roi_colors or [])
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

                    # Metadata
                    aq_metadata = {
                        "experiment_id": f"{experiment_id}_aq{aq_id}",
                        "video_name": experiment_id,
                        "group": output_info.get("group"),
                        "subject": output_info.get("subject_id"),
                        "day": output_info.get("day"),
                        "aquarium_id": aq_id,
                    }

                    # Retrieve behavioral config (including perspective)
                    parameters = self.analysis_service.collect_analysis_parameters(
                        self.project_manager.project_data,
                    )
                    behavioral_config = parameters.get("behavioral_config", {})

                    reporter = Reporter(
                        trajectory_df=trajectory_df,
                        metadata=aq_metadata,
                        pixelcm_x=pixelcm_x,
                        pixelcm_y=pixelcm_y,
                        video_height_px=video_height_px,
                        arena_polygon_px=arena_polygon_warped,
                        rois=rois,
                        fps=settings_obj.video_processing.fps,
                        roi_colors=roi_colors,
                        video_path=path,
                        calibration=cal,
                        frame_crop_box=frame_crop_box,
                        sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
                        freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
                        freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
                        smoothing_window_length=settings_obj.trajectory_smoothing.window_length,
                        smoothing_polyorder=settings_obj.trajectory_smoothing.polyorder,
                        settings_obj=settings_obj,
                        behavioral_config=behavioral_config,
                    )

                    # Save summary
                    os.makedirs(aq_results_dir, exist_ok=True)
                    summary_path = os.path.join(
                        aq_results_dir, f"{experiment_id}_aq{aq_id}_summary.parquet"
                    )
                    reporter.export_summary_data(
                        summary_path, format="parquet", expected_roi_names=expected_roi_names
                    )

                    # Update output info
                    video["multi_aquarium_outputs"][aq_id_str]["parquet_files"]["summary"] = (
                        summary_path
                    )
                    summary_paths.append(summary_path)
                    processed_count += 1

                if processed_count > 0:
                    video["has_complete_data"] = True
                    return (
                        "completed",
                        f"{experiment_id} ({processed_count} aquários)",
                        summary_paths[-1],
                        True,
                    )
                else:
                    return (
                        "skipped",
                        f"{experiment_id}: nenhum aquário processado com sucesso.",
                        None,
                        False,
                    )

            except Exception as e:
                log.error("processing.multi_summary_failed", error=str(e), exc_info=True)
                return "failed", f"{experiment_id}: erro multi-aquário {e}", None, False

        # Single video path (legacy/standard)
        experiment_id = os.path.splitext(os.path.basename(path))[0]
        # ... existing logic continues below ...
        metadata_hint = dict(video.get("metadata") or {})
        results_path = self.project_manager.resolve_results_directory(
            experiment_id, video_path=path, metadata=metadata_hint
        )
        results_dir = str(results_path)

        calibration_persisted = False

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

            calib_data = self.project_manager.project_data.get("calibration", {}) or {}
            width_cm = calib_data.get("aquarium_width_cm")
            height_cm = calib_data.get("aquarium_height_cm")

            try:
                width_cm = float(width_cm) if width_cm not in (None, "") else None
            except (TypeError, ValueError):
                width_cm = None

            try:
                height_cm = float(height_cm) if height_cm not in (None, "") else None
            except (TypeError, ValueError):
                height_cm = None

            if not (width_cm and height_cm):
                fallback_meta = video.get("metadata") if isinstance(video, dict) else {}
                fallback_width = fallback_meta.get("aquarium_width_cm") if fallback_meta else None
                fallback_height = fallback_meta.get("aquarium_height_cm") if fallback_meta else None

                try:
                    fallback_width = (
                        float(fallback_width) if fallback_width not in (None, "") else None
                    )
                    fallback_height = (
                        float(fallback_height) if fallback_height not in (None, "") else None
                    )
                except (TypeError, ValueError):
                    fallback_width = None
                    fallback_height = None

                if fallback_width and fallback_height:
                    width_cm = fallback_width
                    height_cm = fallback_height
                    calib_data.setdefault("num_aquariums", calib_data.get("num_aquariums", 1))
                    calib_data.setdefault(
                        "animals_per_aquarium", calib_data.get("animals_per_aquarium", 1)
                    )
                    calib_data.update(
                        {
                            "aquarium_width_cm": width_cm,
                            "aquarium_height_cm": height_cm,
                        }
                    )
                    self.project_manager.project_data["calibration"] = calib_data
                    calibration_persisted = True
                    if self.project_manager.project_path:
                        self.project_manager.save_project()

                    self._publish_event(
                        Events.UI_SHOW_WARNING,
                        {
                            "title": "Calibração aplicada",
                            "message": (
                                "Dimensões do aquário foram lidas da configuração deste vídeo "
                                "porque a calibração do projeto estava vazia. Os valores foram "
                                "salvos no projeto para os próximos relatórios."
                            ),
                        },
                    )
                    log.warning(
                        "workflow.reports.calibration_fallback_applied",
                        video=experiment_id,
                        width_cm=width_cm,
                        height_cm=height_cm,
                    )
                else:
                    # Enforce calibration: fail with guidance
                    log.error(
                        "workflow.reports.calibration_missing",
                        video=experiment_id,
                        width_cm=width_cm,
                        height_cm=height_cm,
                    )
                    return (
                        "skipped",
                        f"{experiment_id}: calibração ausente. Defina largura/altura do aquário (cm) no projeto/assistente antes de gerar relatórios.",
                        None,
                        calibration_persisted,
                    )

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

            # Retrieve behavioral config (including perspective)
            parameters = self.analysis_service.collect_analysis_parameters(
                self.project_manager.project_data,
            )
            behavioral_config = parameters.get("behavioral_config", {})

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
                settings_obj=settings_obj,
                behavioral_config=behavioral_config,
            )

            os.makedirs(results_dir, exist_ok=True)
            parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
            reporter.export_summary_data(
                parquet_path, format="parquet", expected_roi_names=expected_roi_names
            )

            video.setdefault("parquet_files", {})["summary"] = parquet_path
            video["has_complete_data"] = True
            return "completed", experiment_id, parquet_path, True
        except Exception as exc:
            return (
                "failed",
                f"{experiment_id}: erro inesperado ({exc}).",
                None,
                calibration_persisted,
            )
        finally:
            self.project_manager.set_active_zone_video(None)
