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

        # New: Batch processing state for Multi-Aquarium
        self._auto_assign_aquariums: bool = False
        self._last_assignment_configs: list[dict] | None = None
        self._assigned_videos: set[str] = set()  # Idempotency guard

        log.info("processing_coordinator.initialized.phase3")

    def reset_multi_aquarium_state(self) -> None:
        """Reset batch assignment state when project changes.

        CRITICAL: This method prevents state leakage between projects.
        The _auto_assign_aquariums and _last_assignment_configs variables
        must be reset when loading a new project to avoid applying
        metadata from a previous project to the new one.
        """
        self._auto_assign_aquariums = False
        self._last_assignment_configs = None
        self._assigned_videos.clear()  # Reset idempotency tracking
        log.info("processing_coordinator.multi_aquarium_state.reset")

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

        bus.subscribe(
            Events.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
            lambda data: self._on_aquarium_assignment_completed(data),
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

        # Reset multi-aquarium state when a new project is loaded
        # CRITICAL: Prevents state leakage between projects
        bus.subscribe(
            "PROJECT_LOADED",
            lambda data: self.reset_multi_aquarium_state(),
        )

        log.info("processing_coordinator.register_handlers.complete", count=6)

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
                        "message": (
                            "Nenhum dos vídeos selecionados contém arena definida "
                            "para processamento."
                        ),
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

        def _on_started_wrapper():
            self._on_processing_started(videos_to_process)

        def _on_progress_wrapper(idx, total, exp_id, fraction, msg, stats):
            self._on_processing_progress(
                videos_to_process, idx, total, exp_id, fraction, msg, stats
            )

        def _on_video_completed_wrapper(idx, total, exp_id, success):
            self._on_video_completed(videos_to_process, idx, total, exp_id, success)

        def _on_completed_wrapper(cancelled, output_dir, summary=None):
            self._on_processing_complete(
                videos_to_process, cancelled, output_dir, summary, on_completed_callback
            )

        return ProcessingCallbacks(
            on_started=_on_started_wrapper,
            on_progress=_on_progress_wrapper,
            on_frame_processed=self._on_frame_processed,
            on_video_completed=_on_video_completed_wrapper,
            on_error=self._on_processing_error,
            on_completed=_on_completed_wrapper,
            on_fatal_error=self._on_processing_fatal_error,
        )

    def _on_processing_started(self, videos_to_process: list[dict]):
        """Internal handler for processing start."""
        if not self.view or not self.root:
            return

        self.ui_coordinator.show_progress_bar(self.view)
        self.ui_coordinator.set_status(
            self.view,
            f"Iniciando processamento para {len(videos_to_process)} vídeos...",
        )
        self.project_manager.set_active_zone_video(None)
        self._publish_processing_mode(source="worker.started", force=True)

    def _on_processing_progress(
        self,
        videos_to_process: list[dict],
        index: int,
        total: int,
        experiment_id: str,
        fraction: float,
        message: str,
        stats: dict | None,
    ):
        """Internal handler for progress updates."""
        if self.cancel_event.is_set() or not self.view:
            return

        overall_progress = f"Processando {index + 1}/{total}: {experiment_id}"
        step_status = f"Etapa: {message}"
        self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
        self.ui_coordinator.update_progress(self.view, fraction)
        self.ui_coordinator.update_view(
            self.view, "update_analysis_progress", fraction, step_status
        )

        # Extract video metadata
        video_metadata = {}
        if 0 <= index < len(videos_to_process):
            current_video = videos_to_process[index]
            video_metadata = current_video.get("metadata", {})

        log.debug(
            "on_progress.metadata_extracted",
            index=index,
            total=total,
            experiment_id=experiment_id,
            group=video_metadata.get("group"),
        )

        # Publish task status update
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

    def _on_frame_processed(self, frame, detections, processing_info):
        """Internal handler for display frame updates."""
        if frame is not None:
            self._publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

        if detections is not None and processing_info:
            self._publish_event(
                Events.UI_UPDATE_DETECTION_OVERLAY,
                {"detections": detections, "report": processing_info},
            )

    def _on_video_completed(
        self,
        videos_to_process: list[dict],
        index: int,
        total: int,
        experiment_id: str,
        success: bool,
    ):
        """Internal handler for single video completion."""
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

        # Results directory logic
        if video_results_dir:
            results_dir = video_results_dir
        else:
            v_name = os.path.splitext(os.path.basename(video_path))[0]
            results_dir = os.path.join(os.path.dirname(video_path), f"{v_name}_results")

        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_exists = os.path.exists(trajectory_path)

        # Multi-aquarium fallback check
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
                for alt_p in alt_paths:
                    if os.path.exists(alt_p):
                        # Use video's current metadata if possible
                        current_v = next(
                            (x for x in videos_to_process if x.get("path") == video_path), {}
                        )
                        alt_multi_outputs[aq_id] = {
                            "results_dir": aq_subdir,
                            "parquet_files": {"trajectory": alt_p},
                            "group": current_v.get("group"),
                            "subject_id": current_v.get("subject"),
                            "day": current_v.get("day", 1),
                        }
                        break

            if alt_multi_outputs:
                trajectory_exists = False

        self._register_completed_outputs(
            video_path,
            results_dir,
            trajectory_path,
            trajectory_exists,
            alt_multi_outputs,
            experiment_id,
            video_results_dir,
        )

    def _register_completed_outputs(
        self,
        video_path,
        results_dir,
        trajectory_path,
        trajectory_exists,
        alt_multi_outputs,
        experiment_id,
        video_results_dir,
    ):
        """Helper to register outputs after video completion."""
        # Register single trajectory
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
        elif not alt_multi_outputs:
            log.warning(
                "controller.video_completed.trajectory_not_found",
                experiment_id=experiment_id,
                expected_path=trajectory_path,
            )

        # Multi-aquarium registration
        outputs_by_aquarium = alt_multi_outputs.copy() if alt_multi_outputs else {}
        if (
            video_results_dir
            and video_results_dir != results_dir
            and os.path.exists(video_results_dir)
        ):
            self._scan_multi_aquarium_outputs(video_results_dir, experiment_id, outputs_by_aquarium)

        if outputs_by_aquarium:
            self.project_manager.register_multi_aquarium_outputs(
                video_path=video_path, outputs_by_aquarium=outputs_by_aquarium
            )
            log.info(
                "controller.video_completed.multi_aquarium_registered",
                video=experiment_id,
                aquariums=list(outputs_by_aquarium.keys()),
            )
            self._handle_sequential_multi_aquarium(outputs_by_aquarium)
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})
            self._generate_completion_reports(video_path, experiment_id, True)
        elif trajectory_exists:
            self._generate_completion_reports(video_path, experiment_id, False)

    def _scan_multi_aquarium_outputs(self, results_dir, experiment_id, outputs_by_aquarium):
        """Scan directory for multi-aquarium outputs."""
        for aq_id in [0, 1]:
            aq_subdir = os.path.join(results_dir, f"aquarium_{aq_id}")
            if not os.path.exists(aq_subdir):
                continue
            traj_candidates = [
                os.path.join(
                    aq_subdir, f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet"
                ),
                os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
            ]
            traj_file = next((p for p in traj_candidates if os.path.exists(p)), None)
            if traj_file:
                outputs_by_aquarium[aq_id] = {
                    "results_dir": aq_subdir,
                    "parquet_files": {"trajectory": traj_file},
                    "day": 1,  # Default
                }

    def _handle_sequential_multi_aquarium(self, outputs_by_aquarium):
        """Handle advancement in sequential multi-aquarium mode."""
        if hasattr(self, "_sequential_context") and self._sequential_context:
            ctx = self._sequential_context
            ctx_outputs = ctx.get("outputs_by_aquarium", {})
            ctx_outputs.update(outputs_by_aquarium)
            ctx["outputs_by_aquarium"] = ctx_outputs
            ctx["current_aquarium_index"] = ctx.get("current_aquarium_index", 0) + 1

            if self.view and self.root:
                self.root.after(50, self._process_next_aquarium_in_sequence)
            else:
                self._process_next_aquarium_in_sequence()

    def _generate_completion_reports(self, video_path, experiment_id, is_multi):
        """Generate reports after video completion."""
        try:
            self.generate_project_reports([video_path])
        except Exception as e:
            log.error(
                f"controller.video_completed.report_failed_{'multi' if is_multi else 'single'}",
                video=experiment_id,
                error=str(e),
            )

    def _on_processing_error(self, error: Exception, context: str):
        """Internal handler for processing errors."""
        log.error("controller.processing.worker_error", context=context, error=str(error))
        if self.root and self.view:
            self.ui_coordinator.schedule(
                lambda: self.view.show_error("Erro na Análise", f"{context}: {error}")
            )

    def _on_processing_fatal_error(self, exc, context, recovery_info):
        """Internal handler for fatal processing errors."""
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

    def _on_processing_complete(
        self,
        videos_to_process: list[dict],
        was_cancelled: bool,
        output_dir: str,
        summary: dict | None,
        callback: Callable | None,
    ):
        """Internal handler for complete processing finish."""
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

        self._publish_event(
            Events.UI_REFRESH_PROJECT_VIEWS,
            {
                "reason": "analysis_completed",
                "append_summary": True,
                "immediate": False,
            },
        )

        if callback:
            callback()

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
        """Start the actual processing for a single video after zone setup."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=str(video_path))

        # 1. Sequential Mode Handle
        is_multi_aq = hasattr(zone_data, "aquariums")
        use_seq = is_multi_aq and getattr(zone_data, "sequential_processing", False)

        # 2. Extract Calibration Data
        calib_data = self._extract_calibration_from_config(config)
        n_aq = calib_data["n"]

        if use_seq:
            self._handle_sequential_single_video_start(video_path, config, zone_data, calib_data)
            return

        # 3. Validate
        val = self.validate_can_start_processing(False, False, False)
        if not val.is_valid:
            self._show_validation_error(val)
            return

        self.project_manager.set_active_zone_video(video_path)

        # 4. Multi-aq UI/Model Sync
        zone_data = self._sync_multi_aquarium_setup(video_path, n_aq, zone_data)

        # 5. Persist Calib & Settings
        self._persist_single_video_calibration(config, calib_data)

        # 6. Register Video
        self._ensure_single_video_registered(video_path, config, zone_data, calib_data)

        # 7. Save Zones
        self._ensure_single_video_zones_saved(video_path, zone_data)

        # 8. Setup Detector
        if not self._setup_detector_for_single_video(video_path, zone_data):
            return

        # 9. Final Start
        self._execute_single_video_analysis(video_path)

    def _extract_calibration_from_config(self, config: dict) -> dict:
        """Helper to extract calibration params from config."""
        n_aq = 1
        w_cm = None
        h_cm = None

        if isinstance(config, dict):
            try:
                n_aq = int(config.get("num_aquariums", 1))
                self.settings.analysis_config.num_aquariums = n_aq
            except (TypeError, ValueError):
                pass

            try:
                raw_w = config.get("aquarium_width_cm")
                w_cm = float(raw_w) if raw_w not in (None, "") else None
            except (TypeError, ValueError):
                pass

            try:
                raw_h = config.get("aquarium_height_cm")
                h_cm = float(raw_h) if raw_h not in (None, "") else None
            except (TypeError, ValueError):
                pass

        return {"w": w_cm, "h": h_cm, "n": n_aq}

    def _handle_sequential_single_video_start(self, video_path, config, zone_data, calib):
        """Handle sequential multi-aquarium start logic."""
        log.info(
            "workflow.seq_multi.detected", video=str(video_path), aq_cnt=len(zone_data.aquariums)
        )
        w_cm, h_cm, n_aq = calib["w"], calib["h"], calib["n"]

        if w_cm and h_cm:
            c = self.project_manager.project_data.get("calibration") or {}
            c.setdefault("num_aquariums", c.get("num_aquariums", n_aq))
            c.setdefault("animals_per_aquarium", c.get("animals_per_aquarium", 1))
            c.update({"aquarium_width_cm": w_cm, "aquarium_height_cm": h_cm})
            self.project_manager.project_data["calibration"] = c
            if self.project_manager.project_path:
                self.project_manager.save_project()
            self.project_manager.invalidate_groups_cache()

        # Ensure registered
        v_entry = self.project_manager.find_video_entry(path=video_path)
        if not v_entry:
            meta = self._extract_metadata_from_config(config)
            if w_cm:
                meta.setdefault("aquarium_width_cm", w_cm)
            if h_cm:
                meta.setdefault("aquarium_height_cm", h_cm)

            v_dict = {
                "path": str(video_path),
                "experiment_id": os.path.splitext(os.path.basename(str(video_path)))[0],
                "status": "processing",
                "has_arena": bool(zone_data.aquariums),
                "has_rois": any(bool(aq.roi_polygons) for aq in zone_data.aquariums),
                "multi_aquarium_mode": True,
            }
            if meta:
                v_dict["metadata"] = meta
            self.project_manager.add_video_batch([v_dict], save_project=False)
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {"reason": "seq_reg", "imm": True})
        else:
            meta = v_entry.get("metadata") or {}
            updated = False
            if w_cm and not meta.get("aquarium_width_cm"):
                meta["aquarium_width_cm"] = w_cm
                updated = True
            if h_cm and not meta.get("aquarium_height_cm"):
                meta["aquarium_height_cm"] = h_cm
                updated = True
            if updated:
                v_entry["metadata"] = meta
                if self.project_manager.project_path:
                    self.project_manager.save_project()

        self.project_manager.set_active_zone_video(video_path)
        self._start_sequential_multi_aquarium_processing(video_path, config, zone_data)

    def _show_validation_error(self, val):
        """Show validation error to UI."""
        log.warning("workflow.single_video.val_failed", code=val.error_code)
        self._publish_event(
            Events.UI_SHOW_WARNING,
            {"title": "Validação Falhou", "message": val.error_message},
        )

    def _sync_multi_aquarium_setup(self, video_path, n_aq, zone_data) -> ZoneData:
        """Sync multi-aquarium setup with UI and model."""
        if n_aq > 1:
            log.info("workflow.single_video.setup_multi_aq", count=n_aq)
            curr = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if not curr:
                from zebtrack.core.detector import AquariumData, MultiAquariumZoneData

                aqs = [AquariumData(id=i) for i in range(n_aq)]
                new_m = MultiAquariumZoneData(aquariums=aqs)
                persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(video_path, new_m, persist)
                zone_data = new_m

            if self.view and hasattr(self.view, "zone_controls"):
                self.view.zone_controls.update_aquarium_count(n_aq)
                self.view.zone_controls.set_active_aquarium(0)
        elif self.view and hasattr(self.view, "zone_controls"):
            self.view.zone_controls.update_aquarium_count(1)
        return zone_data

    def _persist_single_video_calibration(self, config, calib):
        """Persist calibration and settings for single video."""
        w_cm, h_cm = calib["w"], calib["h"]
        if w_cm and h_cm:
            c = self.project_manager.project_data.get("calibration") or {}
            c.setdefault("num_aquariums", c.get("num_aquariums", 1))
            c.setdefault("animals_per_aquarium", c.get("animals_per_aquarium", 1))
            c.update({"aquarium_width_cm": w_cm, "aquarium_height_cm": h_cm})
            self.project_manager.project_data["calibration"] = c

            a_int, d_int = self._determine_processing_intervals(config)
            self.project_manager.project_data["analysis_interval_frames"] = a_int
            self.project_manager.project_data["display_interval_frames"] = d_int

            if "behavioral_analysis" in config:
                self.project_manager.project_data["behavioral_config"] = config[
                    "behavioral_analysis"
                ]

            if self.project_manager.project_path:
                self.project_manager.save_project()
            log.info("workflow.single_video.cal_saved", w=w_cm, h=h_cm)

    def _ensure_single_video_registered(self, video_path, config, zone_data, calib):
        """Ensure single video is registered in project."""
        v_entry = self.project_manager.find_video_entry(path=video_path)
        if not v_entry:
            log.info("workflow.single_video.registering", video=str(video_path))
            w_cm, h_cm = calib["w"], calib["h"]
            meta = self._extract_metadata_from_config(config)
            if w_cm:
                meta.setdefault("aquarium_width_cm", w_cm)
            if h_cm:
                meta.setdefault("aquarium_height_cm", h_cm)

            v_name = os.path.splitext(os.path.basename(str(video_path)))[0]
            has_a = False
            has_r = False
            if zone_data:
                if hasattr(zone_data, "aquariums"):
                    has_a = bool(zone_data.aquariums)
                    has_r = any(bool(aq.roi_polygons) for aq in zone_data.aquariums)
                else:
                    has_a = bool(zone_data.polygon)
                    has_r = bool(zone_data.roi_polygons)

            v_dict = {
                "path": str(video_path),
                "experiment_id": v_name,
                "status": "processing",
                "has_arena": has_a,
                "has_rois": has_r,
            }
            if meta:
                v_dict["metadata"] = meta
            self.project_manager.add_video_batch([v_dict], save_project=False)
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {"reason": "reg", "imm": True})

    def _ensure_single_video_zones_saved(self, video_path, zone_data):
        """Ensure zones are saved for single video."""
        should_s = False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                should_s = bool(zone_data.aquariums)
            else:
                should_s = bool(zone_data.polygon or zone_data.roi_polygons)

        if should_s:
            r_cnt = 0
            if hasattr(zone_data, "aquariums"):
                r_cnt = sum(len(aq.roi_polygons) for aq in zone_data.aquariums)
            elif hasattr(zone_data, "roi_polygons"):
                r_cnt = len(zone_data.roi_polygons)

            log.info("workflow.single_video.save_zones", video=str(video_path), count=r_cnt)
            self.project_manager.save_zone_data(
                zone_data, video_path, persist=bool(self.project_manager.project_path)
            )

    def _setup_detector_for_single_video(self, video_path, zone_data) -> bool:
        """Setup detector with zones for single video."""
        if not self.detector:
            return True
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": f"Não foi possível abrir: {video_path}"},
            )
            return False
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.detector.set_zones(zone_data, w, h)
        has_aq = bool(zone_data and (zone_data.polygon or hasattr(zone_data, "aquariums")))
        self.detector.set_aquarium_region_defined(has_aq)
        log.info("controller.single_video.zones_init", has_aq=has_aq)
        return True

    def _execute_single_video_analysis(self, video_path):
        """Final execution start for single video."""
        scanned = ProjectManager.scan_input_paths([str(video_path)])
        if not scanned:
            if self.view:
                self.view.show_error("Erro", "Não foi possível identificar vídeo válido.")
            return

        out_dir = self.project_manager.get_results_directory()
        log.info("controller.single_video.analysing", video=str(video_path), out=out_dir)
        self.process_videos(scanned, out_dir)

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
                        "message": (
                            f"Não foi possível identificar {num_aquariums} aquário(s) "
                            "estável(is) no vídeo. Isso pode ocorrer devido a reflexos, "
                            "pouca luz ou movimento excessivo da câmera.\n\n"
                            "Por favor, defina a área manualmente."
                        ),
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

                # Retrieve available groups for the dialog
                available_groups = self.project_manager.get_available_groups() or []

                # Check for "Apply to all" active state
                if self._auto_assign_aquariums and self._last_assignment_configs:
                    log.info("multi_auto_detect.auto_assigning", video=str(video_path))
                    self._on_aquarium_assignment_completed(
                        {
                            "video_path": str(video_path),
                            "configs": self._last_assignment_configs,
                            "apply_to_all": True,
                        }
                    )
                else:
                    # Trigger Assignment Dialog
                    # Note: We pass multi_aquarium_config if it was provided in the request
                    self._publish_event(
                        Events.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
                        {
                            "video_path": str(video_path),
                            "available_groups": available_groups,
                            "multi_aquarium_config": data.get("multi_aquarium_config"),
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

    def _on_aquarium_assignment_completed(self, data: dict) -> None:
        """Handle completion of aquarium assignment (group/subject/day).

        Updates the MultiAquariumZoneData with the assigned metadata.
        """
        if not isinstance(data, dict):
            return

        video_path = data.get("video_path")
        configs = data.get("configs")  # List of dicts: {aquarium_id, group, subject_id, day}
        apply_to_all = data.get("apply_to_all", False)

        if not video_path or not configs:
            return

        # Idempotency guard: skip if already assigned
        video_key = str(video_path)
        if video_key in self._assigned_videos:
            log.debug(
                "assignment_complete.skipped_duplicate",
                video=os.path.basename(video_path),
            )
            return

        # Update batch state
        if apply_to_all:
            self._auto_assign_aquariums = True
            self._last_assignment_configs = configs

        try:
            # 1. Load existing Multi Zone Data
            zone_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if not zone_data:
                log.warning("assignment_complete.no_zone_data", video=video_path)
                return

            # 2. Update each aquarium's metadata
            updated = False
            for config in configs:
                aq_id = config.get("aquarium_id")

                # Find matching aquarium
                target_aq = next((aq for aq in zone_data.aquariums if aq.id == aq_id), None)
                if target_aq:
                    target_aq.group = config.get("group")
                    target_aq.subject_id = config.get("subject_id")
                    target_aq.day = config.get("day", "1")
                    updated = True

            # 3. Save updated data
            if updated:
                should_persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path, zone_data, persist=should_persist
                )

                # Mark as assigned (idempotency)
                self._assigned_videos.add(video_key)

                # Mark zones as finalized (all aquariums have metadata)
                video_entry = self.project_manager.find_video_entry(path=video_path)
                if video_entry:
                    video_entry["zones_finalized"] = True
                    if self.project_manager.project_path:
                        self.project_manager.save_project()

                log.info(
                    "assignment_complete.zones_updated",
                    video=os.path.basename(video_path),
                    apply_to_all=apply_to_all,
                    zones_finalized=True,
                )

                # 4. Refresh UI to show new groups/subjects (optional but good)
                self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

        except Exception as e:
            log.error("assignment_complete.error", error=str(e), exc_info=True)

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
                                "experiment_id": (
                                    f"{os.path.splitext(os.path.basename(path))[0]}_aq{aq_id}"
                                ),
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

                        if entry_meta:
                            df = self._enrich_unified_report_metadata(df, entry_meta, process_entry)
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
            # 1. Align and concatenate
            final_df, schema_mismatch, all_columns = self._align_and_concatenate_unified_dfs(dfs)

            # 2. Export Word and Excel
            self._export_unified_reports(
                final_df, unified_dir, roi_colors_map, schema_mismatch, all_columns
            )
        except Exception as e:
            log.error("workflow.unified_report.failed", error=str(e), exc_info=True)
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro no Relatório", "message": f"{e}"},
            )
        finally:
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Generate reports (Word, Excel, Parquet) for specified videos."""
        if not video_paths:
            return

        log.info("workflow.reports.start", count=len(video_paths))
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatórios detalhados..."})

        # Pre-generate summaries
        entries = [self.project_manager.find_video_entry(p) for p in video_paths]
        self.generate_parquet_summaries([e for e in entries if e], self.settings)

        count, errors = 0, []
        self._ensure_analysis_service_ready()

        for path in video_paths:
            try:
                self._generate_single_video_reports(path)
                count += 1
            except Exception as e:
                log.error("workflow.reports.video_failed", video=path, error=str(e))
                errors.append(f"{os.path.basename(path)}: {e}")

        self._finalize_report_generation(count, errors)

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

    def _ensure_analysis_service_ready(self):
        """Ensure AnalysisService is initialized with current settings."""
        if not self.analysis_service:
            from zebtrack.analysis.analysis_service import AnalysisService

            self.analysis_service = AnalysisService(settings_obj=self.settings)
        elif self.analysis_service.settings is None:
            self.analysis_service.settings = self.settings

    def _generate_single_video_reports(self, path: str):
        """Orchestrate report generation for a single video path."""
        experiment_id = os.path.splitext(os.path.basename(path))[0]
        entry = self.project_manager.find_video_entry(path=path)
        if not entry:
            return

        metadata = entry.get("metadata", {})
        multi_outputs = entry.get("multi_aquarium_outputs")

        if multi_outputs:
            self._generate_multi_aquarium_reports(path, experiment_id, entry, multi_outputs)
        else:
            self._generate_standard_report(path, experiment_id, entry, metadata)

    def _generate_multi_aquarium_reports(self, path, exp_id, entry, multi_outputs):
        """Generate reports for multi-aquarium videos."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        analysis_params = self.analysis_service.collect_analysis_parameters(project_data)
        calib = project_data.get("calibration", {})
        fps = float(self.settings.video_processing.fps)
        probed_w, probed_h = self._probe_video_dimensions(str(path))

        zone_data = self.project_manager.get_multi_aquarium_zone_data(video_path=path)
        if not zone_data:
            zone_data = self.project_manager.get_zone_data(video_path=path)

        for aq_id_str, output_info in multi_outputs.items():
            aq_id = int(aq_id_str)
            self._process_single_aquarium_in_multi(
                path,
                exp_id,
                entry,
                aq_id,
                output_info,
                zone_data,
                calib,
                fps,
                probed_w,
                probed_h,
                analysis_params,
            )

    def _process_single_aquarium_in_multi(
        self, path, exp_id, entry, aq_id, output_info, zone_data, calib, fps, p_w, p_h, params
    ):
        """Process a single aquarium within a multi-aquarium video for report generation."""
        aq_results_dir = output_info.get("results_dir")
        aq_parquet_files = output_info.get("parquet_files", {})
        trajectory_path = aq_parquet_files.get("trajectory")

        if not trajectory_path or not os.path.exists(trajectory_path):
            log.warning("workflow.reports.multi_aquarium.missing_trajectory", video=path, aq=aq_id)
            return

        df = pd.read_parquet(trajectory_path)
        aq_metadata = {
            **entry.get("metadata", {}),
            "aquarium_id": aq_id,
            "group": output_info.get("group", entry.get("metadata", {}).get("group")),
            "subject": output_info.get("subject_id", entry.get("metadata", {}).get("subject")),
        }

        # Geometry
        arena_polygon = []
        if hasattr(zone_data, "aquariums") and zone_data.aquariums:
            for aq in zone_data.aquariums:
                if aq.id == aq_id:
                    arena_polygon = aq.polygon if aq.polygon else []
                    break
        elif zone_data:
            arena_polygon = zone_data.polygon if zone_data.polygon else []

        fb_w = getattr(zone_data, "video_width", p_w) or p_w
        fb_h = getattr(zone_data, "video_height", p_h) or p_h

        off_x, off_y, loc_w, loc_h = self._compute_local_space_geometry(arena_polygon, fb_w, fb_h)
        arena_poly_local = [(float(x) - off_x, float(y) - off_y) for x, y in arena_polygon]
        if not arena_poly_local:
            arena_poly_local = [
                (0.0, 0.0),
                (float(loc_w), 0.0),
                (float(loc_w), float(loc_h)),
                (0.0, float(loc_h)),
            ]

        rois, roi_colors_map = self._collect_rois_for_aquarium(zone_data, aq_id, off_x, off_y)
        df = self._normalize_df_to_local_space(df, off_x, off_y, loc_w, loc_h)

        # Calibration
        px_x, px_y = self._resolve_pixel_cm(aq_metadata, calib, loc_w, loc_h)

        # Background
        frame_crop = (off_x, off_y, loc_w, loc_h) if arena_polygon else None
        video_path_report = self._prepare_background_image(path, exp_id, aq_results_dir, frame_crop)

        analysis_result = self.analysis_service.run_full_analysis_as_dto(
            trajectory_df=df,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=int(loc_h or p_h or 720),
            arena_polygon_px=arena_poly_local,
            rois=rois,
            fps=fps,
            metadata=aq_metadata,
            roi_colors=roi_colors_map,
            freezing_vel_threshold=self.settings.video_processing.freezing_velocity_threshold,
            freezing_min_duration=self.settings.video_processing.freezing_min_duration_s,
            video_path=video_path_report,
            frame_crop_box=frame_crop,
            behavioral_config=params.get("behavioral_config"),
        )

        self._export_individual_outputs(analysis_result, aq_results_dir, f"{exp_id}_aq{aq_id}")

    def _generate_standard_report(self, path, exp_id, entry, metadata):
        """Generate report for a standard (single aquarium) video."""
        results_path = self.project_manager.resolve_results_directory(
            exp_id, video_path=path, metadata=metadata
        )
        os.makedirs(results_path, exist_ok=True)

        traj_path = os.path.join(results_path, f"3_CoordMovimento_{exp_id}.parquet")
        if not os.path.exists(traj_path):
            log.warning("workflow.reports.missing_trajectory", video=path)
            return

        df = pd.read_parquet(traj_path)
        zone_data = self.project_manager.get_zone_data(video_path=path)
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        analysis_params = self.analysis_service.collect_analysis_parameters(project_data)
        calib = project_data.get("calibration", {})
        px_x_orig, px_y_orig = (
            float(calib.get("pixel_per_cm_x", 1.0)),
            float(calib.get("pixel_per_cm_y", 1.0)),
        )

        p_w, p_h = self._probe_video_dimensions(str(path))
        fb_w = getattr(zone_data, "video_width", p_w) or p_w
        fb_h = getattr(zone_data, "video_height", p_h) or p_h

        arena_poly_px = list(zone_data.polygon or [])
        if not arena_poly_px:
            arena_poly_px = [[0, 0], [fb_w, 0], [fb_w, fb_h], [0, fb_h]]

        off_x, off_y, loc_w, loc_h = self._compute_local_space_geometry(arena_poly_px, fb_w, fb_h)
        arena_poly_local = [(float(x) - off_x, float(y) - off_y) for x, y in arena_poly_px]

        rois, roi_colors_map = self._collect_rois_for_standard(zone_data, off_x, off_y)
        df = self._normalize_df_to_local_space(df, off_x, off_y, loc_w, loc_h)

        px_x, px_y = self._resolve_pixel_cm(metadata, calib, loc_w, loc_h, px_x_orig, px_y_orig)

        # Background
        frame_crop = (off_x, off_y, loc_w, loc_h)
        video_path_report = self._prepare_background_image(path, exp_id, results_path, frame_crop)

        analysis_result = self.analysis_service.run_full_analysis_as_dto(
            trajectory_df=df,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=int(loc_h),
            arena_polygon_px=arena_poly_local,
            rois=rois,
            fps=float(self.settings.video_processing.fps),
            metadata=metadata,
            roi_colors=roi_colors_map,
            freezing_vel_threshold=self.settings.video_processing.freezing_velocity_threshold,
            freezing_min_duration=self.settings.video_processing.freezing_min_duration_s,
            video_path=video_path_report,
            frame_crop_box=None,
            behavioral_config=analysis_params.get("behavioral_config"),
        )

        report_paths = self._export_individual_outputs(analysis_result, results_path, exp_id)
        self.project_manager.register_processing_outputs(
            video_path=path, report_path=report_paths["docx"], summary_excel=report_paths["xlsx"]
        )

    def _collect_rois_for_aquarium(self, zone_data, aq_id, off_x, off_y):
        """Extract ROIs for a specific aquarium in multi-aquarium data."""
        rois = []
        roi_colors_map = {}
        if hasattr(zone_data, "aquariums") and zone_data.aquariums:
            for aq in zone_data.aquariums:
                if aq.id != aq_id:
                    continue
                for i, poly in enumerate(aq.roi_polygons):
                    translated_poly = [(float(px) - off_x, float(py) - off_y) for px, py in poly]
                    name = aq.roi_names[i] if i < len(aq.roi_names) else f"ROI_{i}"
                    if len(translated_poly) >= 3:
                        rois.append(
                            ROI(name=name, geometry=Polygon(translated_poly), coordinate_space="px")
                        )
                    if i < len(aq.roi_colors):
                        roi_colors_map[name] = aq.roi_colors[i]
                break
        return rois, roi_colors_map

    def _collect_rois_for_standard(self, zone_data, off_x, off_y):
        """Extract ROIs for standard single-aquarium data."""
        rois = []
        roi_colors_map = {}
        if zone_data:
            for i, poly in enumerate(zone_data.roi_polygons):
                translated_poly = [(float(px) - off_x, float(py) - off_y) for px, py in poly]
                name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                if len(translated_poly) >= 3:
                    rois.append(
                        ROI(name=name, geometry=Polygon(translated_poly), coordinate_space="px")
                    )
                if i < len(zone_data.roi_colors):
                    roi_colors_map[name] = zone_data.roi_colors[i]
        return rois, roi_colors_map

    def _resolve_pixel_cm(self, metadata, calib, loc_w, loc_h, px_x_orig=1.0, px_y_orig=1.0):
        """Resolve pixel/cm ratio using projet calibration or metadata fallbacks."""
        w_cm = metadata.get("aquarium_width_cm") or calib.get("aquarium_width_cm")
        h_cm = metadata.get("aquarium_height_cm") or calib.get("aquarium_height_cm")

        px_x = (
            px_x_orig if px_x_orig > 1.0 else (loc_w / float(w_cm) if (w_cm and loc_w > 0) else 1.0)
        )
        px_y = (
            px_y_orig if px_y_orig > 1.0 else (loc_h / float(h_cm) if (h_cm and loc_h > 0) else 1.0)
        )
        return px_x, px_y

    def _prepare_background_image(self, video_file, exp_id, results_dir, crop_box):
        """Extract and save a cropped frame for report backgrounds."""
        if crop_box:
            frame = self._extract_cropped_background_frame(video_file, crop_box)
            if frame is not None:
                try:
                    bg_path = os.path.join(results_dir, f"{exp_id}_bg.png")
                    cv2.imwrite(bg_path, frame)
                    return bg_path
                except Exception:
                    pass
        return video_file

    def _export_individual_outputs(self, analysis_result, results_dir, exp_id):
        """Export individual Word and Excel reports."""
        reporter = Reporter.from_analysis(analysis_result)
        os.makedirs(results_dir, exist_ok=True)
        report_base = os.path.join(results_dir, f"4_Relatorio_{exp_id}")
        docx_path = f"{report_base}.docx"
        xlsx_path = f"{report_base}.xlsx"
        reporter.export_individual_report(docx_path)
        reporter.export_summary_data(xlsx_path, format="excel")
        return {"docx": docx_path, "xlsx": xlsx_path}

    def _probe_video_dimensions(self, video_file: str) -> tuple[int, int]:
        """Probe video width and height."""
        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            return (0, 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return w, h

    def _compute_local_space_geometry(self, polygon, fb_w, fb_h):
        """Compute local space geometry for an aquarium."""
        if not polygon:
            return 0, 0, max(fb_w, 1), max(fb_h, 1)
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        min_x, min_y = int(np.floor(min(xs))), int(np.floor(min(ys)))
        max_x, max_y = int(np.ceil(max(xs))), int(np.ceil(max(ys)))
        return min_x, min_y, max(max_x - min_x, 1), max(max_y - min_y, 1)

    def _normalize_df_to_local_space(self, df, offset_x, offset_y, w, h):
        """Normalize dataframe coordinates to local aquarium space."""
        if offset_x == 0 and offset_y == 0:
            return df.copy()
        local_df = df.copy()
        cols_to_drop = ["x_cm", "y_cm", "x_center_cm", "y_center_cm"]
        local_df = local_df.drop(columns=[c for c in cols_to_drop if c in local_df.columns])
        for col in ("x_center_px", "x1", "x2"):
            if col in local_df.columns:
                local_df[col] = (local_df[col] - offset_x).clip(lower=0, upper=w)
        for col in ("y_center_px", "y1", "y2"):
            if col in local_df.columns:
                local_df[col] = (local_df[col] - offset_y).clip(lower=0, upper=h)
        return local_df

    def _extract_cropped_background_frame(self, video_file, crop_box):
        """Extract a single cropped frame from video."""
        if not crop_box:
            return None
        cap = cv2.VideoCapture(video_file)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        x, y, w, h = map(int, crop_box)
        return frame[y : y + h, x : x + w].copy()

    def _finalize_report_generation(self, count, errors):
        """Finalize report generation UI feedback."""
        self._publish_event(Events.UI_SET_STATUS, {"message": "Relatórios gerados."})
        if errors:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {"title": "Erros na Geração", "message": "Falhas em:\n" + "\n".join(errors[:5])},
            )
        elif count > 0:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Relatórios Gerados",
                    "message": f"Gerados relatórios para {count} vídeos.",
                },
            )

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
        """Process a single video for summary generation."""
        self._ensure_analysis_service_ready()

        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]
        multi_outputs = video.get("multi_aquarium_outputs")

        if multi_outputs:
            return self._process_multi_summary_video(
                video, experiment_id, path, multi_outputs, settings_obj, expected_roi_names
            )

        return self._process_standard_summary_video(
            video, experiment_id, path, settings_obj, expected_roi_names
        )

    def _process_multi_summary_video(
        self, video, exp_id, path, multi_outputs, settings, expected_rois
    ):
        """Process multi-aquarium video for summary generation."""
        try:
            multi_zone = self.project_manager.get_multi_aquarium_zone_data(path)
            if not multi_zone:
                return "skipped", f"{exp_id}: dados multi-aquário ausentes.", None, False

            processed_count, summary_paths = 0, []
            for aq_id_str, output_info in multi_outputs.items():
                aq_id = int(aq_id_str)
                s_path = self._process_one_aquarium_summary(
                    video, exp_id, path, aq_id, output_info, multi_zone, settings, expected_rois
                )
                if s_path:
                    summary_paths.append(s_path)
                    processed_count += 1

            if processed_count > 0:
                video["has_complete_data"] = True
                return (
                    "completed",
                    f"{exp_id} ({processed_count} aquários)",
                    summary_paths[-1],
                    True,
                )
            return "skipped", f"{exp_id}: nenhum aquário processado.", None, False
        except Exception as e:
            log.error("processing.multi_summary_failed", error=str(e))
            return "failed", f"{exp_id}: erro multi-aquário {e}", None, False

    def _process_one_aquarium_summary(
        self, video, exp_id, path, aq_id, out, multi_zone, settings, expected
    ):
        """Process summary for a single aquarium in multi-aquarium mode."""
        aq_results_dir = out.get("results_dir")
        traj_path = out.get("parquet_files", {}).get("trajectory")
        if not traj_path or not os.path.exists(traj_path):
            return None

        aq_zone = next((a for a in multi_zone.aquariums if getattr(a, "id", None) == aq_id), None)
        if not aq_zone:
            return None

        df = pd.read_parquet(traj_path)
        if df.empty:
            return None

        calib = self.project_manager.project_data.get("calibration", {})
        px_x, px_y, poly_warped, video_h, rois, colors, cal = self._prepare_summary_geometry(
            aq_zone.polygon, aq_zone.roi_polygons, aq_zone.roi_names, aq_zone.roi_colors, calib
        )

        aq_meta = {
            "experiment_id": f"{exp_id}_aq{aq_id}",
            "video_name": exp_id,
            "group": out.get("group"),
            "subject": out.get("subject_id"),
            "day": out.get("day"),
            "aquarium_id": aq_id,
        }
        behavioral_config = self.analysis_service.collect_analysis_parameters(
            self.project_manager.project_data
        ).get("behavioral_config", {})

        reporter = Reporter(
            trajectory_df=df,
            metadata=aq_meta,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=video_h,
            arena_polygon_px=poly_warped,
            rois=rois,
            fps=settings.video_processing.fps,
            roi_colors=colors,
            video_path=path,
            calibration=cal,
            frame_crop_box=out.get("frame_crop_box"),
            behavioral_config=behavioral_config,
            settings_obj=settings,
        )

        os.makedirs(aq_results_dir, exist_ok=True)
        s_path = os.path.join(aq_results_dir, f"{exp_id}_aq{aq_id}_summary.parquet")
        reporter.export_summary_data(s_path, format="parquet", expected_roi_names=expected)
        video["multi_aquarium_outputs"][str(aq_id)]["parquet_files"]["summary"] = s_path
        return s_path

    def _process_standard_summary_video(self, video, exp_id, path, settings, expected):
        """Process standard single-aquarium video for summary generation."""
        # Implementation of standard summary logic...
        # For brevity, I'll extract common parts and wrap up
        res_path = self.project_manager.resolve_results_directory(exp_id, video_path=path)
        res_dir = str(res_path)
        traj_path = video.get("parquet_files", {}).get("trajectory")
        if not traj_path or not os.path.exists(traj_path):
            candidates = [
                os.path.join(res_dir, f"3_CoordMovimento_{exp_id}.parquet"),
                os.path.join(os.path.dirname(path), f"3_CoordMovimento_{exp_id}.parquet"),
            ]
            traj_path = next((c for c in candidates if os.path.exists(c)), None)
        if not traj_path:
            return "skipped", f"{exp_id}: trajetória ausente.", None, False

        df = pd.read_parquet(traj_path)
        if df.empty:
            return "skipped", f"{exp_id}: trajetória vazia.", None, False

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)
            calib = self.project_manager.project_data.get("calibration", {}) or {}
            px_x, px_y, poly_warped, video_h, rois, colors, cal = self._prepare_summary_geometry(
                zone_data.polygon or [],
                zone_data.roi_polygons,
                zone_data.roi_names,
                zone_data.roi_colors,
                calib,
            )

            meta = self.project_manager.get_metadata_for_experiment(exp_id) or {
                "experiment_id": exp_id
            }
            behavioral_config = self.analysis_service.collect_analysis_parameters(
                self.project_manager.project_data
            ).get("behavioral_config", {})

            reporter = Reporter(
                trajectory_df=df,
                metadata=meta,
                pixelcm_x=px_x,
                pixelcm_y=px_y,
                video_height_px=video_h,
                arena_polygon_px=poly_warped,
                rois=rois,
                fps=settings.video_processing.fps,
                roi_colors=colors,
                video_path=path,
                calibration=cal,
                behavioral_config=behavioral_config,
                settings_obj=settings,
            )

            os.makedirs(res_dir, exist_ok=True)
            s_path = os.path.join(res_dir, f"{exp_id}_summary.parquet")
            reporter.export_summary_data(s_path, format="parquet", expected_roi_names=expected)
            video.setdefault("parquet_files", {})["summary"] = s_path
            video["has_complete_data"] = True
            return "completed", exp_id, s_path, True
        except Exception as e:
            return "failed", f"{exp_id}: erro {e}", None, False
        finally:
            self.project_manager.set_active_zone_video(None)

    def _prepare_summary_geometry(self, poly, r_polys, r_names, r_colors, calib):
        """Common geometry preparation for summary generation."""
        w_cm = calib.get("aquarium_width_cm", 0)
        h_cm = calib.get("aquarium_height_cm", 0)
        cal = Calibration(np.array(poly), w_cm, h_cm)
        _, video_h = cal.target_dims_px
        px_x, px_y = cal.pixel_per_cm_ratio
        poly_warped = cal.transform_points(poly)

        rois = []
        for i, r_poly in enumerate(r_polys):
            wp = cal.transform_points(r_poly)
            name = r_names[i] if i < len(r_names) else f"ROI {i + 1}"
            rois.append(
                ROI(
                    name=name,
                    geometry=Polygon([(float(x), float(y)) for x, y in wp]),
                    coordinate_space="px",
                )
            )

        colors = {
            (r_names[i] if i < len(r_names) else f"ROI {i + 1}"): r_colors[i]
            for i in range(len(r_colors))
        }
        return px_x, px_y, poly_warped, video_h, rois, colors, cal
