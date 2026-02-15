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

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
from zebtrack.core.detector import MultiAquariumZoneData, ZoneData
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
    from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
    from zebtrack.coordinators.ui_state_coordinator import UIStateController
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.core.video_classification_service import VideoClassificationService
    from zebtrack.core.video_selection_service import VideoSelectionService
    from zebtrack.core.video_validation_service import VideoValidationService
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.io.recorder_factory import RecorderFactory
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
        dialog_coordinator: DialogCoordinator | None = None,
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
            dialog_coordinator: Optional DialogCoordinator for UI dialog interactions
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
        self.dialog_coordinator = dialog_coordinator

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

        # Batch processing context - suppresses per-video dialogs during batch
        self._batch_context: dict | None = None

        # New: Sequential context for multi-aquarium processing
        self._sequential_context: dict[str, Any] | None = None

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

    def _is_batch_processing(self) -> bool:
        """Check if we're currently processing multiple videos in batch mode.

        Returns:
            True if batch processing is active and has more than 1 video.
        """
        return self._batch_context is not None and self._batch_context.get("total_videos", 0) > 1

    def _init_batch_context(self, total_videos: int) -> None:
        """Initialize batch processing context.

        Args:
            total_videos: Total number of videos to process in this batch.
        """
        self._batch_context = {
            "total_videos": total_videos,
            "completed_videos": 0,
            "successful_videos": [],
            "failed_videos": [],
        }
        log.info(
            "batch_context.initialized",
            total_videos=total_videos,
            suppress_dialogs=total_videos > 1,
        )

    def _update_batch_context(self, video_path: str, success: bool) -> None:
        """Update batch context when a video completes.

        Args:
            video_path: Path of the completed video.
            success: Whether the video was processed successfully.
        """
        if not self._batch_context:
            return

        self._batch_context["completed_videos"] += 1
        if success:
            self._batch_context["successful_videos"].append(video_path)
        else:
            self._batch_context["failed_videos"].append(video_path)

        log.debug(
            "batch_context.video_completed",
            video=os.path.basename(video_path),
            completed=self._batch_context["completed_videos"],
            total=self._batch_context["total_videos"],
        )

    def _finalize_batch_context(self) -> dict | None:
        """Finalize batch context and return summary.

        Returns:
            Batch summary dict or None if not in batch mode.
        """
        if not self._batch_context:
            return None

        summary = {
            "total": self._batch_context["total_videos"],
            "successful": len(self._batch_context["successful_videos"]),
            "failed": len(self._batch_context["failed_videos"]),
            "successful_videos": self._batch_context["successful_videos"],
            "failed_videos": self._batch_context["failed_videos"],
        }

        log.info(
            "batch_context.finalized",
            total=summary["total"],
            successful=summary["successful"],
            failed=summary["failed"],
        )

        self._batch_context = None
        # Restore dialog suppression when batch finishes
        self._set_dialog_suppression(False)
        return summary

    def _set_dialog_suppression(self, suppress: bool) -> None:
        """Toggle dialog suppression on the GUI DialogManager.

        During batch processing, modal messagebox dialogs are suppressed and
        replaced with status-bar updates and log entries.

        Args:
            suppress: True to suppress, False to restore normal behavior.
        """
        try:
            if self.view and hasattr(self.view, "dialog_manager"):
                self.view.dialog_manager.set_dialog_suppression(suppress)
        except AttributeError:
            log.debug(
                "processing_coordinator._set_dialog_suppression.failed",
                suppress=suppress,
            )

    def _on_processing_mode_changed(self, data: dict) -> None:
        """Handle processing mode change (Parallel vs Sequential).

        Args:
            data: Event data containing:
                - sequential (bool): True for sequential, False for parallel
                - apply_to_all (bool): If True (default), applies to all videos
        """
        sequential = bool(data.get("sequential", True))  # Default to sequential
        apply_to_all = bool(data.get("apply_to_all", True))  # Default to apply to all

        if apply_to_all:
            # Apply to ALL videos with multi-aquarium data
            self._apply_processing_mode_to_all_videos(sequential)
        else:
            # Apply only to current video
            video_path = self.project_manager.get_active_zone_video()
            if video_path:
                self._apply_processing_mode_to_video(video_path, sequential)

    def _apply_processing_mode_to_video(self, video_path: str | Path, sequential: bool) -> bool:
        """Apply processing mode to a single video.

        Returns:
            True if mode was changed, False otherwise.
        """
        multi_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
        if multi_data and multi_data.sequential_processing != sequential:
            multi_data.sequential_processing = sequential
            self.project_manager.save_multi_aquarium_zone_data(video_path, multi_data, persist=True)
            log.info(
                "processing_coordinator.mode_changed", video=str(video_path), sequential=sequential
            )
            return True
        return False

    def _apply_processing_mode_to_all_videos(self, sequential: bool) -> None:
        """Apply processing mode to all videos with multi-aquarium data."""
        project_data = self.project_manager.project_data
        if not project_data:
            return

        videos = project_data.get("videos", [])
        changed_count = 0

        for video_entry in videos:
            video_path = video_entry.get("path")
            if not video_path:
                continue

            if self._apply_processing_mode_to_video(video_path, sequential):
                changed_count += 1

        if changed_count > 0:
            log.info(
                "processing_coordinator.mode_changed_all",
                sequential=sequential,
                videos_updated=changed_count,
            )
            # Save project once after all updates
            if self.project_manager.project_path:
                self.project_manager.save_project()

    # ========================================================================
    # Group A: Video Processing Workflows (VideoProcessingOrchestrator)
    # ========================================================================

    def start_project_processing_workflow(self) -> None:
        """Add and process videos with robust zone validation.

        Migrated from VideoProcessingOrchestrator (Phase 3E → Phase 0.3).
        Handles:
        1. Validation via validate_can_start_processing()
        2. Zone validation via DialogCoordinator
        3. File picker for video selection
        4. Scanning and batching via ProjectManager
        5. Mixed data scenario handling via DialogCoordinator
        6. Processing worker creation and thread start
        """
        log.info("workflow.project_processing.start")

        coordinator = self
        view = self.view
        dialog_coordinator = self.dialog_coordinator

        if not view:
            log.error("workflow.project_processing.no_view")
            return

        if not dialog_coordinator:
            log.error("workflow.project_processing.no_dialog_coordinator")
            return

        # Validate processing preconditions (project loaded, not already processing)
        validation_result = coordinator.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,  # Zone validation is complex with UI, handled below
            check_videos_exist=False,
        )

        if not dialog_coordinator.handle_validation_error(validation_result):
            return

        # Validate zones with UI interaction (arena creation, ROI warnings)
        if not dialog_coordinator.validate_zones_with_ui():
            return

        # 1. Ask user to select files or folders
        paths = view.ask_open_filenames(
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
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Nenhum Vídeo Encontrado",
                        "message": "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados.",  # noqa: E501
                    },
                )
            return

        # 3. Handle mixed data scenario (processed vs unprocessed videos)
        videos_to_process = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)
        if videos_to_process is None:
            return  # User cancelled or videos already added

        if not videos_to_process:
            if self.event_bus:
                self.event_bus.publish_event(
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

        callbacks = coordinator.create_processing_callbacks(videos_to_process)
        context = coordinator.create_processing_context(
            videos_to_process, str(self.project_manager.project_path or "")
        )

        coordinator.processing_worker = ProcessingWorker(context, callbacks)
        coordinator.processing_thread = coordinator.processing_worker.start_in_thread()

        if self.ui_state_controller:
            self.ui_state_controller.activate_analysis_view_mode()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        if self.event_bus:
            self.event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sucesso",
                    "message": (
                        f"{len(videos_to_process)} vídeo(s) adicionado(s) para processamento."
                    ),
                },
            )

        log.info(
            "workflow.project_processing.started",
            videos_count=len(videos_to_process),
        )

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
                video_path=str(data.get("video_path", "")) if isinstance(data, dict) else "",
                config=data.get("config", {}) if isinstance(data, dict) else {},
                zone_data=cast(
                    Any,
                    data.get("zone_data") if isinstance(data, dict) else None,
                ),
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
        # NOTE: This event is also handled by trigger_batch_trajectory_processing callback
        # which does proper path resolution. This handler is kept for backward compatibility
        # but should NOT process if paths contain tree IDs (handled by callback instead).
        def _handle_generate_trajectories(data: dict | None) -> None:
            if not isinstance(data, dict) or "selection" not in data:
                return
            selection = data.get("selection", ())
            # Skip if selection contains tree item IDs (handled by callback)
            # The callback does proper path resolution via resolve_processing_reports_video_paths
            if any(
                "_sub_" in str(s) or not str(s).endswith((".mp4", ".avi", ".mov", ".mkv"))
                for s in selection
            ):
                log.debug(
                    "processing_coordinator.generate_trajectories.skipped",
                    reason="selection_contains_tree_ids_handled_by_callback",
                )
                return
            # Only process if we have actual video paths
            paths = [
                s
                for s in selection
                if isinstance(s, str) and s.endswith((".mp4", ".avi", ".mov", ".mkv"))
            ]
            if paths:
                self.process_pending_project_videos(paths)

        bus.subscribe(Events.PROCESSING_GENERATE_TRAJECTORIES, _handle_generate_trajectories)

        # Multi-aquarium auto-detection event (Phase 5)
        bus.subscribe(
            Events.ZONE_MULTI_AUTO_DETECT,
            lambda data: self._handle_multi_auto_detect(data),
        )

        bus.subscribe(
            Events.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
            lambda data: self._on_aquarium_assignment_completed(data),
        )

        # Handle processing mode toggle (Parallel vs Sequential)
        bus.subscribe(
            Events.ZONE_PROCESSING_MODE_CHANGED,
            lambda data: self._on_processing_mode_changed(data),
        )

        # Unified report generation
        def _handle_report_generate(data):
            if not isinstance(data, dict):
                return
            report_type = data.get("report_type")
            videos = data.get("videos", [])
            paths = [v.get("path") for v in videos if v.get("path")]
            replace_existing = bool(data.get("replace_existing", False))
            report_scope = str(data.get("report_scope", "all"))

            if report_type == "unified":
                self.generate_unified_report(
                    paths,
                    replace_existing=replace_existing,
                    report_scope=report_scope,
                )
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

    def _create_project_settings_snapshot(self) -> Settings:
        """Create a Settings object with project-specific overrides applied."""
        # Deep copy global settings to avoid mutating shared state
        snapshot = self.settings.model_copy(deep=True)
        project_data = self.project_manager.project_data or {}

        # 1. Video Processing Overrides
        if "analysis_offset_frames" in project_data:
            snapshot.video_processing.processing_offset = project_data["analysis_offset_frames"]

        # 2. Trajectory Smoothing Overrides
        analysis_params = project_data.get("analysis_parameters", {})
        if "smoothing_window_length" in analysis_params:
            snapshot.trajectory_smoothing.window_length = analysis_params["smoothing_window_length"]
        if "smoothing_polyorder" in analysis_params:
            snapshot.trajectory_smoothing.polyorder = analysis_params["smoothing_polyorder"]

        # 3. ROI Settings Overrides
        roi_settings = project_data.get("roi_settings", {})
        if "roi_inclusion_rule" in roi_settings:
            snapshot.roi_inclusion_rule = roi_settings["roi_inclusion_rule"]
        if "roi_buffer_radius_value" in roi_settings:
            snapshot.roi_buffer_radius_value = roi_settings["roi_buffer_radius_value"]
        if "roi_min_bbox_overlap_ratio" in roi_settings:
            snapshot.roi_min_bbox_overlap_ratio = roi_settings["roi_min_bbox_overlap_ratio"]

        # 4. Behavioral Formatting
        behavioral_config = project_data.get("behavioral_config", {})
        if behavioral_config and hasattr(snapshot, "behavioral_analysis"):
            ba = snapshot.behavioral_analysis
            if "aquarium_perspective" in behavioral_config:
                perspective_raw = str(behavioral_config["aquarium_perspective"]).strip().lower()
                perspective_raw = perspective_raw.replace("-", "_")
                if perspective_raw in {"top_down", "top_down_view", "topdown", "top"}:
                    ba.aquarium_perspective = "top_down"
                else:
                    ba.aquarium_perspective = "lateral"
            if "thigmotaxis_distance_cm" in behavioral_config:
                ba.default_thigmotaxis_distance_cm = behavioral_config["thigmotaxis_distance_cm"]
            if "geotaxis_distance_cm" in behavioral_config:
                ba.default_geotaxis_distance_cm = behavioral_config["geotaxis_distance_cm"]
            if "geotaxis_num_zones" in behavioral_config:
                ba.default_geotaxis_num_zones = behavioral_config["geotaxis_num_zones"]
            if "geotaxis_bottom_zones" in behavioral_config:
                ba.default_geotaxis_bottom_zones = behavioral_config["geotaxis_bottom_zones"]
            if "geotaxis_mode" in behavioral_config:
                ba.geotaxis_mode = behavioral_config["geotaxis_mode"]

        return snapshot

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
        # Create project-specific settings snapshot
        # This ensures Worker receives correct Offset, ROI, and Behavioral settings
        settings_snapshot = self._create_project_settings_snapshot()

        # SYNC: Ensure global settings reflect project/wizard preference for single animal mode
        # This is critical because ProcessingWorker reads from settings to init ByteTracker
        use_single_subject = self._resolve_single_subject_tracker_preference(single_video_config)
        if use_single_subject is not None:
            if use_single_subject != settings_snapshot.tracking.use_single_subject_tracker:
                log.info(
                    "processing_coordinator.sync_settings",
                    use_single_subject_tracker=use_single_subject,
                    reason="worker_initialization_sync",
                )
                settings_snapshot.tracking.use_single_subject_tracker = use_single_subject
                # Also sync legacy flag for compatibility
                settings_snapshot.video_processing.single_animal_per_aquarium = use_single_subject

            # Keep runtime settings aligned with snapshot so UI mode label reflects
            # the effective tracker mode selected by wizard/project configuration.
            if use_single_subject != self.settings.tracking.use_single_subject_tracker:
                log.info(
                    "processing_coordinator.sync_runtime_tracking_mode",
                    use_single_subject_tracker=use_single_subject,
                    reason="ui_mode_sync",
                )
                self.settings.tracking.use_single_subject_tracker = use_single_subject
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
            settings=settings_snapshot,
            single_video_config=single_video_config,
            zone_data=zone_data,
            analysis_interval_frames=analysis_interval,
            display_interval_frames=display_interval,
            process_single_video_func=process_single_video_func,
            apply_project_settings_func=apply_project_settings_func,
            determine_intervals_func=self._determine_processing_intervals,
            retry_strategy=settings_snapshot.video_processing.batch_retry_strategy,
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

        def _on_progress_wrapper(
            idx: int, total: int, exp_id: str | None, fraction: float, msg: str, stats: dict | None
        ) -> None:
            self._on_processing_progress(
                videos_to_process, idx, total, exp_id, fraction, msg, stats
            )

        def _on_video_completed_wrapper(
            idx: int, total: int, exp_id: str | None, success: bool
        ) -> None:
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
        if not self.view:
            return

        # Initialize batch context to track progress and suppress per-video dialogs.
        # Guard: only initialize if not already set (it may have been pre-initialized
        # by process_pending_project_videos before the worker started).
        if self._batch_context is None:
            self._init_batch_context(len(videos_to_process))

        self.ui_coordinator.show_progress_bar(self.view)
        self.ui_coordinator.set_status(
            self.view,
            f"Iniciando processamento para {len(videos_to_process)} vídeos...",
        )
        self.project_manager.set_active_zone_video(None)

        # Guard: if the main thread already determined SINGLE_SUBJECT mode
        # (e.g. via batch_pre_start_sync), preserve it — the worker callback
        # would otherwise re-determine from the main-thread detector (which
        # is never configured for single mode) and overwrite with MULTI_TRACK.
        current_mode = getattr(self, "_active_processing_mode", None)
        if current_mode is ProcessingMode.SINGLE_SUBJECT:
            self._publish_processing_mode(
                source="worker.started",
                force=True,
                mode_override=ProcessingMode.SINGLE_SUBJECT,
            )
        else:
            self._publish_processing_mode(source="worker.started", force=True)

    def _on_processing_progress(
        self,
        videos_to_process: list[dict],
        index: int,
        total: int,
        experiment_id: str | None,
        fraction: float,
        message: str,
        stats: dict | None,
    ) -> None:
        """Internal handler for progress updates."""
        if self.cancel_event.is_set():
            return

        display_exp_id = experiment_id or "Video"
        overall_progress = f"Processando {index + 1}/{total}: {display_exp_id}"
        step_status = f"Etapa: {message}"
        if self.view:
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, step_status
            )

        # Extract video metadata
        video_metadata = {}
        if 0 <= index < len(videos_to_process):
            current_video = videos_to_process[index]
            metadata = current_video.get("metadata")
            if isinstance(metadata, dict):
                video_metadata = metadata

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
                    "experiment_id": experiment_id or "Unknown",
                    "step": message,
                    "progress_fraction": float(fraction),
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
            self._publish_event(
                Events.UI_DISPLAY_FRAME,
                {
                    "frame": frame,
                    "detections": detections,
                },
            )

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
        experiment_id: str | None,
        success: bool,
    ) -> None:
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

        # NEW: Use index directly for robustness (Phase 3 fix)
        if 0 <= index < len(videos_to_process):
            video_info = videos_to_process[index]
            video_path = video_info.get("path")
            video_results_dir = video_info.get("results_dir")
            # Use original experiment_id (base filename) for parquet names
            # but allow override if stored in video_info
            v_exp_id = video_info.get("experiment_id")
            if not v_exp_id and video_path:
                v_exp_id = os.path.splitext(os.path.basename(str(video_path)))[0]

            if not v_exp_id:
                v_exp_id = "Unknown"
        else:
            log.warning("controller.video_completed.index_out_of_bounds", index=index)
            return

        # Results directory logic
        if video_results_dir:
            results_dir = video_results_dir
        else:
            base_dir = os.path.dirname(str(video_path)) if video_path else "."
            results_dir = os.path.join(base_dir, f"{v_exp_id}_results")

        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{v_exp_id}.parquet")
        # Check if worker used the suffixed experiment_id for the file
        if not os.path.exists(trajectory_path):
            trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")

        trajectory_exists = os.path.exists(trajectory_path)

        # Multi-aquarium fallback check
        alt_multi_outputs: dict[int, dict] = {}

        # EXPLODED TASK HANDLER: If this was an exploded sequential task,
        # it MUST be registered as multi-aquarium
        aq_id_override = video_info.get("aquarium_id")
        if aq_id_override is not None and trajectory_exists:
            log.info("controller.video_completed.exploded_task_detected", aq_id=aq_id_override)
            alt_multi_outputs[aq_id_override] = {
                "results_dir": results_dir,
                "parquet_files": {"trajectory": trajectory_path},
                "group": video_info.get("group") or (video_info.get("metadata", {}).get("group")),
                "subject_id": video_info.get("subject")
                or (video_info.get("metadata", {}).get("subject")),
                "day": video_info.get("day", 1),
            }
            trajectory_exists = False  # Force multi-aquarium registration path below

        if (
            not trajectory_exists
            and not alt_multi_outputs
            and results_dir
            and os.path.exists(results_dir)
        ):
            for aq_id in [0, 1]:
                aq_subdir = os.path.join(results_dir, f"aquarium_{aq_id}")
                if not os.path.exists(aq_subdir):
                    continue

                alt_paths = [
                    os.path.join(
                        aq_subdir, f"3_CoordMovimento_{v_exp_id}_aquarium_{aq_id}.parquet"
                    ),
                    os.path.join(
                        aq_subdir, f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet"
                    ),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{v_exp_id}.parquet"),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
                ]
                for alt_p in alt_paths:
                    if os.path.exists(alt_p):
                        # Use video's current metadata if possible
                        alt_multi_outputs[aq_id] = {
                            "results_dir": aq_subdir,
                            "parquet_files": {"trajectory": alt_p},
                            "group": video_info.get("group")
                            or (video_info.get("metadata", {}).get("group")),
                            "subject_id": video_info.get("subject")
                            or (video_info.get("metadata", {}).get("subject")),
                            "day": video_info.get("day", 1),
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
            v_exp_id,
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
        # Multi-aquarium registration preparation
        outputs_by_aquarium = alt_multi_outputs.copy() if alt_multi_outputs else {}

        # Scan for multi-aquarium outputs if not already found
        if (
            video_results_dir
            and video_results_dir != results_dir
            and os.path.exists(video_results_dir)
        ):
            self._scan_multi_aquarium_outputs(video_results_dir, experiment_id, outputs_by_aquarium)

        # Register single trajectory ONLY if no multi-aquarium outputs found
        # This prevents "Group G0" creation for the main video file in multi-aquarium mode
        if trajectory_exists and not outputs_by_aquarium:
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
        elif not trajectory_exists and not outputs_by_aquarium:
            log.warning(
                "controller.video_completed.trajectory_not_found",
                experiment_id=experiment_id,
                expected_path=trajectory_path,
            )

        if outputs_by_aquarium:
            self.project_manager.register_multi_aquarium_outputs(
                video_path=video_path,
                outputs_by_aquarium=cast(dict[int, dict], outputs_by_aquarium),
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
            # Only generate single report if we registered single trajectory
            self._generate_completion_reports(video_path, experiment_id, False)

    def _scan_multi_aquarium_outputs(self, results_dir, experiment_id, outputs_by_aquarium):
        """Scan directory for multi-aquarium outputs."""
        if not results_dir or not os.path.exists(results_dir):
            return

        # Scan for aquarium_X directories
        import re

        for item in os.listdir(results_dir):
            item_path = os.path.join(results_dir, item)
            if not os.path.isdir(item_path):
                continue

            match = re.match(r"^aquarium_(\d+)$", item)
            if match:
                aq_id = int(match.group(1))
                traj_candidates = [
                    os.path.join(
                        item_path, f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet"
                    ),
                    os.path.join(item_path, f"3_CoordMovimento_{experiment_id}.parquet"),
                ]
                traj_file = next((p for p in traj_candidates if os.path.exists(p)), None)
                if traj_file:
                    outputs_by_aquarium[aq_id] = {
                        "results_dir": item_path,
                        "parquet_files": {"trajectory": traj_file},
                        "day": 1,  # Default
                    }

    def _handle_sequential_multi_aquarium(self, outputs_by_aquarium):
        """Handle advancement in sequential multi-aquarium mode."""
        if hasattr(self, "_sequential_context") and isinstance(self._sequential_context, dict):
            ctx = self._sequential_context
            ctx_outputs = ctx.setdefault("outputs_by_aquarium", {})
            if isinstance(ctx_outputs, dict):
                ctx_outputs.update(outputs_by_aquarium)

            current_idx = ctx.get("current_aquarium_index", 0)
            if isinstance(current_idx, int):
                ctx["current_aquarium_index"] = current_idx + 1

            if self.view and self.root:
                self.root.after(50, self._process_next_aquarium_in_sequence)
            else:
                self._process_next_aquarium_in_sequence()

    def _generate_completion_reports(self, video_path, experiment_id, is_multi):
        """Generate reports after video completion."""
        try:
            self.generate_project_reports([video_path])
        except Exception as e:  # except Exception justified: non-critical fallback
            log.error(
                f"controller.video_completed.report_failed_{'multi' if is_multi else 'single'}",
                video=experiment_id,
                error=str(e),
            )

    def _on_processing_error(self, error: Exception, context: str):
        """Internal handler for processing errors."""
        log.error("controller.processing.worker_error", context=context, error=str(error))
        if self.root and self.view:
            if self._is_batch_processing():
                # In batch mode, update status bar instead of blocking dialog
                self.ui_coordinator.set_status(self.view, f"Erro: {context}: {error}")
            else:
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
            if self._is_batch_processing():
                # In batch mode, update status bar instead of blocking dialog
                self.ui_coordinator.set_status(
                    self.view,
                    f"Erro crítico: {context}"
                    f" — {len(recovery_info['affected_videos'])}"
                    " vídeo(s) afetados",
                )
            else:
                view_ref = self.view
                self.ui_coordinator.schedule(
                    lambda: view_ref.show_error(
                        "Erro Crítico de Processamento",
                        f"{context}\n\nErro: {exc}\n\n"
                        f"Vídeos afetados: {len(recovery_info['affected_videos'])}\n"
                        f"Verifique os logs para detalhes.",
                    )
                )
        self.state_manager.update_processing_state(
            source="worker.fatal_error",
            is_processing=False,
            error=str(exc),
            current_video=None,
            cancel_requested=False,
            is_live_session_active=False,
        )
        if self.view:
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)
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
            is_live_session_active=False,
        )

        # Capture batch state BEFORE finalizing (which clears the context)
        was_batch = (
            self._batch_context is not None and self._batch_context.get("total_videos", 0) > 1
        )

        # Finalize batch context and get summary
        batch_summary = self._finalize_batch_context()
        final_status = "Pronto."

        if was_cancelled:
            if not was_batch:
                self.ui_coordinator.show_info(
                    self.view, "Cancelado", "A análise de vídeo foi cancelada."
                )
            else:
                final_status = "Processamento em lote cancelado."
        elif videos_to_process:
            # Show consolidated batch summary dialog
            if batch_summary and batch_summary["total"] > 1:
                # Multiple videos - show batch summary
                success_count = batch_summary["successful"]
                fail_count = batch_summary["failed"]

                if fail_count == 0:
                    final_status = (
                        f"Lote concluído: {success_count}/{batch_summary['total']} vídeo(s) com "
                        "sucesso."
                    )
                else:
                    final_status = (
                        f"Lote concluído com pendências: {success_count} sucesso, "
                        f"{fail_count} falha(s)."
                    )
            elif not was_batch:
                # Single video (not part of a batch) — show simple message
                msg = f"Análise concluída. Resultados salvos em:\n{output_dir}"
                self.ui_coordinator.show_info(self.view, "Sucesso", msg)
            else:
                # Was part of a batch but only 1 video succeeded — use status bar only
                final_status = f"Análise concluída. Resultados salvos em: {output_dir}"

        self.ui_coordinator.set_status(self.view, final_status)
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
        zone_data: ZoneData | MultiAquariumZoneData,
    ):
        """Start the actual processing for a single video after zone setup."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=str(video_path))

        # 1. Sequential Mode Handle
        is_multi_aq = hasattr(zone_data, "aquariums")

        # Bug fix: Reload zone_data from project_manager to get latest sequential_processing flag
        # and subject_id values that may have been set by the assignment dialog
        if is_multi_aq:
            fresh_zone_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if fresh_zone_data:
                zone_data = fresh_zone_data
                log.debug(
                    "workflow.zone_data_reloaded",
                    video=str(video_path),
                    sequential_processing=getattr(zone_data, "sequential_processing", False),
                )

            # Bug fix: Validate that all aquariums have subject_id defined
            # Bug fix: Validate that all aquariums have subject_id defined
            if isinstance(zone_data, MultiAquariumZoneData):
                for aq in zone_data.aquariums:
                    if not aq.subject_id:
                        log.warning(
                            "processing.missing_subject_id",
                            aquarium_id=aq.id,
                            video=str(video_path),
                        )
                        self._publish_event(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Configuração Incompleta",
                                "message": (
                                    f"Aquário {aq.id} não tem sujeito definido. "
                                    "Configure os aquários antes de processar."
                                ),
                            },
                        )
                        return

        use_seq = is_multi_aq and getattr(zone_data, "sequential_processing", False)

        # 2. Extract Calibration Data
        calib_data = self._extract_calibration_from_config(config)
        n_aq = calib_data["n"]

        if use_seq:
            self._handle_sequential_single_video_start(video_path, config, zone_data, calib_data)
            return

        # 3. Validate
        # 3. Validate
        val = self.validate_can_start_processing(
            check_project_loaded=False, check_zones=False, check_videos_exist=False
        )
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

        single_video_config = config if isinstance(config, dict) else None
        resolved_tracker_pref = self._resolve_single_subject_tracker_preference(single_video_config)
        if (
            resolved_tracker_pref is not None
            and resolved_tracker_pref != self.settings.tracking.use_single_subject_tracker
        ):
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            self.settings.video_processing.single_animal_per_aquarium = resolved_tracker_pref
            log.info(
                "processing_coordinator.single_video_tracker_pref_applied",
                use_single_subject_tracker=resolved_tracker_pref,
            )

        self._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
        effective_mode = (
            ProcessingMode.SINGLE_SUBJECT
            if self.settings.tracking.use_single_subject_tracker
            else ProcessingMode.MULTI_TRACK
        )
        self._publish_processing_mode(
            source="single_video.preflight",
            force=True,
            mode_override=effective_mode,
        )

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
                log.debug("processing_coordinator.parse_num_aquariums.suppressed", exc_info=True)

            try:
                raw_w = config.get("aquarium_width_cm")
                if raw_w is not None and str(raw_w).strip():
                    w_cm = float(raw_w)
            except (TypeError, ValueError):
                log.debug("processing_coordinator.parse_aquarium_width.suppressed", exc_info=True)

            try:
                raw_h = config.get("aquarium_height_cm")
                if raw_h is not None and str(raw_h).strip():
                    h_cm = float(raw_h)
            except (TypeError, ValueError):
                log.debug("processing_coordinator.parse_aquarium_height.suppressed", exc_info=True)

        return {"w": w_cm, "h": h_cm, "n": n_aq}

    def _save_multi_aquarium_config_to_calibration(self, calibration_dict: dict) -> None:
        """
        Convert custom_regex_patterns from wizard to MultiAquariumData format and save.

        This method retrieves custom_regex_patterns from wizard_metadata (if it exists),
        converts it to the MultiAquariumData dict format expected by the assignment
        dialog, and stores it in calibration["multi_aquarium"].

        Args:
            calibration_dict: The calibration dictionary to update (modified in-place)
        """
        # Get wizard_metadata from project_data
        wizard_metadata = (
            self.project_manager.project_data.get("_wizard_metadata", {})
            if self.project_manager.project_data
            else {}
        )

        if not wizard_metadata:
            log.debug("calibration.multi_aquarium.no_wizard_metadata")
            return

        # Extract custom_regex_patterns from wizard_metadata
        custom_patterns = wizard_metadata.get("custom_regex_patterns")

        if not custom_patterns or not isinstance(custom_patterns, dict):
            log.debug(
                "calibration.multi_aquarium.no_custom_patterns",
                has_patterns=bool(custom_patterns),
                patterns_type=type(custom_patterns).__name__ if custom_patterns else "None",
            )
            return

        # Convert custom_regex_patterns dict to MultiAquariumData dict format
        # The wizard stores patterns as {group_pattern, day_pattern, subject_pattern}
        # We need to convert to MultiAquariumData format with regex_pattern field
        from zebtrack.ui.wizard.models import MultiAquariumData

        try:
            # Build combined regex pattern from individual patterns
            combined_pattern = MultiAquariumData.build_combined_regex_pattern(
                group_pattern=custom_patterns.get("group_pattern"),
                day_pattern=custom_patterns.get("day_pattern"),
                subject_pattern=custom_patterns.get("subject_pattern"),
            )

            if combined_pattern:
                # Create MultiAquariumData dict with the combined pattern
                # Note: enabled=False to avoid Pydantic validation error
                # Dialog only needs regex_pattern for auto-fill functionality
                multi_aquarium_dict = {
                    "enabled": False,
                    "regex_pattern": combined_pattern,
                    "regex_group_field": "group",
                    "regex_subject_field": "subject",
                    "regex_day_field": "day",
                    "aquarium_configs": [],  # Empty, will be filled by assignment dialog
                }

                # Save to calibration
                calibration_dict["multi_aquarium"] = multi_aquarium_dict

                log.info(
                    "calibration.multi_aquarium.saved",
                    has_regex=True,
                    regex_pattern_preview=combined_pattern[:80],
                )
            else:
                log.warning(
                    "calibration.multi_aquarium.no_combined_pattern",
                    group_pattern=custom_patterns.get("group_pattern"),
                    day_pattern=custom_patterns.get("day_pattern"),
                    subject_pattern=custom_patterns.get("subject_pattern"),
                )

        except (ValueError, KeyError, TypeError) as e:
            log.error(
                "calibration.multi_aquarium.conversion_failed",
                error=str(e),
                patterns=custom_patterns,
            )

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

            # CRITICAL FIX: Convert custom_regex_patterns from wizard to MultiAquariumData format
            # This enables regex auto-fill in the assignment dialog
            self._save_multi_aquarium_config_to_calibration(c)

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
                "path": Path(video_path).as_posix(),
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
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path, new_m, persist=persist
                )
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

            # CRITICAL FIX: Convert custom_regex_patterns from wizard to MultiAquariumData format
            # This enables regex auto-fill in the assignment dialog
            self._save_multi_aquarium_config_to_calibration(c)

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
                "path": Path(video_path).as_posix(),
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

        video_stem = Path(video_path).stem
        out_dir = self.project_manager.resolve_results_directory(
            video_stem, video_path=str(video_path)
        )
        log.info("controller.single_video.analysing", video=str(video_path), out=out_dir)
        self.process_videos(scanned, out_dir)

    def process_videos(self, videos_to_process: list[dict], output_base_dir: Path | str) -> None:
        """Execute processing for a list of videos (legacy support)."""
        output_dir_str = str(output_base_dir)

        # Define wrapper callbacks to match ProcessingCallbacks signature
        def _on_started_wrapper() -> None:
            self._on_processing_started(videos_to_process)

        def _on_progress_wrapper(
            idx: int, tot: int, eid: str | None, frac: float, msg: str, st: dict | None
        ) -> None:
            self._on_processing_progress(videos_to_process, idx, tot, eid, frac, msg, st)

        def _on_video_completed_wrapper(
            index: int, total: int, exp_id: str | None, success: bool
        ) -> None:
            self._on_video_completed(videos_to_process, index, total, exp_id, success)

        def _on_finished_wrapper(cancelled: bool, o_dir: str, summary: dict | None = None) -> None:
            self._on_processing_complete(videos_to_process, cancelled, o_dir, summary, None)

        def _on_fatal_error_wrapper(exc: Exception, context: str, info: dict) -> None:
            self._on_processing_fatal_error(exc, context, info)

        callbacks = ProcessingCallbacks(
            on_started=_on_started_wrapper,
            on_progress=_on_progress_wrapper,
            on_frame_processed=self._on_frame_processed,
            on_video_completed=_on_video_completed_wrapper,
            on_error=self._on_processing_error,
            on_completed=_on_finished_wrapper,
            on_fatal_error=_on_fatal_error_wrapper,
        )

        context = self.create_processing_context(videos_to_process, output_dir_str)

        if self.cancel_event:
            self.cancel_event.clear()

        # Initialize and start worker
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

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

        # Notify user (only if not in batch mode to avoid interrupting flow)
        aq_count = len(multi_zone_data.aquariums)
        if not self._is_batch_processing():
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

        current_index = cast(int, ctx["current_aquarium_index"])
        total = cast(int, ctx["total_aquariums"])

        if current_index >= total:
            # All aquariums processed - finalize and generate reports
            log.info(
                "workflow.sequential_multi.complete",
                total_aquariums=total,
            )

            video_path = str(ctx["video_path"])
            outputs_by_aquarium = cast(
                dict[int, dict[Any, Any]], ctx.get("outputs_by_aquarium", {})
            )

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
            except Exception as e:  # except Exception justified: non-critical fallback
                log.error(
                    "workflow.sequential_multi.report_failed",
                    error=str(e),
                )

            # Show completion dialog only if not in batch mode
            if not self._is_batch_processing():
                self._publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Concluído",
                        "message": f"Todos os {ctx['total_aquariums']} aquários foram processados "
                        "e relatórios gerados com sucesso.",
                    },
                )

            # Update batch context with successful video
            video_path_str = str(ctx["video_path"])
            self._update_batch_context(video_path_str, success=True)

            # Refresh project views
            self._publish_event(
                Events.UI_REFRESH_PROJECT_VIEWS,
                {"reason": "sequential_multi_complete", "immediate": True},
            )

            self._sequential_context = None
            return

        aquarium_index = cast(int, ctx["current_aquarium_index"])
        multi_zone_data = cast("MultiAquariumZoneData", ctx["multi_zone_data"])
        aquarium = multi_zone_data.aquariums[aquarium_index]

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

        # Resolve correct hierarchical directory for this aquarium
        aq_config = {
            "aquarium_id": aquarium.id,
            "group": aquarium.group,
            "subject_id": aquarium.subject_id,
            "day": int(aquarium.day) if aquarium.day else 1,
        }

        aq_dirs = self.project_manager.resolve_multi_aquarium_results_directories(
            experiment_id=os.path.splitext(os.path.basename(str(ctx["video_path"])))[0],
            aquarium_configs=[aq_config],
        )

        aquarium_output = str(aq_dirs.get(aquarium.id))
        if not aquarium_output:
            # Fallback (should not happen)
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

        if not self._sequential_context:
            return

        # Get aquarium info for output registration
        current_aquarium = self._sequential_context["multi_zone_data"].aquariums[  # type: ignore
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
            is_live_session_active=False,
        )

    def process_pending_project_videos(  # noqa: C901
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

        # CRITICAL FIX: Validate multi-aquarium metadata before processing
        # If any video has empty subject_id, block processing and show warning
        for video_info in eligible_videos:
            video_path = video_info.get("path")
            multi_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if multi_data:
                missing_subjects = []
                for aq in multi_data.aquariums:
                    if not aq.subject_id:
                        missing_subjects.append(f"Aquário {aq.id}")

                if not video_path:
                    continue

                if missing_subjects:
                    log.error(
                        "workflow.multi_aquarium.incomplete_metadata",
                        video=os.path.basename(str(video_path)),
                        missing=missing_subjects,
                    )
                    self._publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Configuração Incompleta",
                            "message": (
                                f"O vídeo '{os.path.basename(str(video_path))}' tem aquários "
                                f"sem sujeito definido:\n\n"
                                f"{', '.join(missing_subjects)}\n\n"
                                f"Por favor:\n"
                                f"1. Vá para a aba 'Zones'\n"
                                f"2. Selecione o vídeo\n"
                                f"3. Clique em 'Auto-Detectar' novamente\n"
                                f"4. Preencha o diálogo de atribuição que aparecerá\n"
                                f"5. Confirme ANTES de processar"
                            ),
                        },
                    )
                    return

        # Load zone data for eligible videos
        self._load_zones_for_eligible_videos(eligible_videos)

        # IMPLEMENTATION: Explode sequential multi-aquarium tasks
        final_tasks = []
        for video_info in eligible_videos:
            zone_data_dict = video_info.get("zone_data")
            # Check if this is a multi-aquarium task with sequential processing enabled
            if (
                zone_data_dict
                and "aquariums" in zone_data_dict
                and zone_data_dict.get("sequential_processing")
            ):
                try:
                    import os as _os  # Local import to avoid scope issues

                    from zebtrack.core.zone_manager import ZoneManager

                    multi_data = ZoneManager.multi_aquarium_zone_data_from_dict(zone_data_dict)

                    video_basename = _os.path.basename(str(video_info.get("path", "")))
                    log.info(
                        "workflow.project_processing.exploding_sequential_task",
                        video=video_basename,
                        aquarium_count=len(multi_data.aquariums),
                    )

                    # Create one task per aquarium
                    aq_configs = []
                    for aq in multi_data.aquariums:
                        aq_configs.append(
                            {
                                "aquarium_id": aq.id,
                                "group": aq.group,
                                "subject_id": aq.subject_id,
                                "day": int(aq.day) if aq.day else 1,
                            }
                        )

                    # Resolve correct hierarchical directories for each aquarium
                    experiment_id = _os.path.splitext(video_basename)[0]
                    aq_dirs = self.project_manager.resolve_multi_aquarium_results_directories(
                        experiment_id=experiment_id, aquarium_configs=aq_configs
                    )

                    for aq in multi_data.aquariums:
                        aq_task = video_info.copy()
                        # Convert MultiAquariumZoneData to single ZoneData
                        aq_zone_data = aq.to_zone_data()
                        aq_task["zone_data"] = ZoneManager.zone_data_to_dict(aq_zone_data)
                        # Mark as NOT multi-aquarium so worker uses single-pass logic
                        aq_task["is_multi_aquarium"] = False

                        # Update results_dir to be the correct hierarchical folder for this subject
                        aq_results_dir = aq_dirs.get(aq.id)
                        if aq_results_dir:
                            aq_task["results_dir"] = str(aq_results_dir)
                        else:
                            # Fallback (should not happen with valid multi_data)
                            base_results_dir = Path(video_info.get("results_dir", ""))
                            aq_task["results_dir"] = str(base_results_dir / f"aquarium_{aq.id}")

                        # Store aquarium ID for completion handling
                        aq_task["aquarium_id"] = aq.id

                        # Ensure individual task metadata reflects the aquarium's metadata
                        aq_task["group"] = aq.group
                        aq_task["subject"] = aq.subject_id
                        aq_task["day"] = aq.day

                        log.info(
                            "workflow.sequential_multi.task_created",
                            aquarium_id=aq.id,
                            subject=aq.subject_id,
                            day=aq.day,
                            results_dir=aq_task["results_dir"],
                        )

                        final_tasks.append(aq_task)
                except Exception as exc:  # except Exception justified: non-critical fallback
                    log.exception(
                        "workflow.project_processing.sequential_explosion_failed",
                        video=video_info.get("path", ""),
                        error=str(exc),
                    )
                    # Fall back to non-sequential mode
                    final_tasks.append(video_info)
            else:
                final_tasks.append(video_info)

        eligible_videos = final_tasks

        self.cancel_event.clear()

        # Pre-initialize batch context BEFORE starting the worker so that
        # _is_batch_processing() returns True from the very start and any
        # early errors (worker creation, context setup) can be checked.
        self._init_batch_context(len(eligible_videos))

        # Enable dialog suppression for multi-video batches to prevent
        # modal messagebox windows from blocking the automated flow.
        if len(eligible_videos) > 1 and self.view:
            self._set_dialog_suppression(True)

        # Create and start processing worker
        try:
            callbacks = self.create_processing_callbacks(eligible_videos)
            # Ensure project_path is a string (it may be Path object)
            output_dir = (
                str(self.project_manager.project_path) if self.project_manager.project_path else ""
            )
            context = self.create_processing_context(
                eligible_videos,
                output_dir,
                single_video_config=None,
            )

            self.processing_worker = ProcessingWorker(context, callbacks)
            self.processing_thread = self.processing_worker.start_in_thread()
        except Exception as exc:  # except Exception justified: service boundary catch-all
            log.exception(
                "workflow.project_processing.worker_creation_failed",
                error=str(exc),
            )
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro ao Iniciar Processamento",
                    "message": f"Falha ao criar worker de processamento: {exc}",
                },
            )
            return

        # Synchronously resolve and publish processing mode BEFORE UI switches
        # to analysis view, so the label shows the correct mode from the start.
        resolved_mode = self._determine_processing_mode()
        self._active_processing_mode = resolved_mode
        self._publish_processing_mode(
            source="batch_pre_start_sync",
            force=True,
            mode_override=resolved_mode,
        )

        try:
            # Update processing state to trigger UI navigation to analysis view
            first_video = eligible_videos[0] if eligible_videos else {}
            self.state_manager.update_processing_state(
                source="controller.process_pending_project_videos",
                is_processing=True,
                current_video=os.path.basename(str(first_video.get("path", ""))),
                processing_start_time=datetime.now(),
                is_live_session_active=False,
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
                os.path.basename(str(video_info.get("path", ""))) or "(arquivo desconhecido)"
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

            # Use non-blocking status bar for multi-video batches to avoid
            # interrupting the automated flow. Show dialog only for single video.
            if len(eligible_videos) > 1:
                self._publish_event(
                    Events.UI_SET_STATUS,
                    {
                        "message": (
                            f"Processamento em lote iniciado: {len(eligible_videos)} vídeo(s)."
                        ),
                    },
                )
            else:
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
        except Exception as e:  # except Exception justified: non-critical fallback
            log.exception("workflow.project_processing.post_worker_error", error=str(e))
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro Pós-Inicialização", "message": f"Erro ao atualizar interface: {e}"},
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

            # Also check project calibration as fallback
            calibration = (
                self.project_manager.project_data.get("calibration", {})
                if self.project_manager.project_data
                else {}
            )
            project_num_aquariums = (
                calibration.get("num_aquariums", 1) if isinstance(calibration, dict) else 1
            )

            # Use project value if settings wasn't synced
            if num_aquariums == 1 and project_num_aquariums > 1:
                log.warning(
                    "run_aquarium_detection.settings_not_synced",
                    settings_value=num_aquariums,
                    project_value=project_num_aquariums,
                    message="Using project calibration value instead",
                )
                num_aquariums = project_num_aquariums
                # Also sync to settings for future calls
                self.settings.analysis_config.num_aquariums = num_aquariums

            log.info(
                "run_aquarium_detection.num_aquariums_resolved",
                num_aquariums=num_aquariums,
                from_settings=self.settings.analysis_config.num_aquariums,
                from_project=project_num_aquariums,
            )

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

                        # Trigger Assignment Dialog for users to assign Group/Subject/Day
                        available_groups = self.project_manager.get_available_groups() or []

                        # Check for "Apply to all" active state from previous assignments
                        if self._auto_assign_aquariums and self._last_assignment_configs:
                            log.info("run_aquarium_detection.auto_assigning", video=str(video_path))
                            self._on_aquarium_assignment_completed(
                                {
                                    "video_path": str(video_path),
                                    "configs": self._last_assignment_configs,
                                    "apply_to_all": True,
                                }
                            )
                        else:
                            # Show dialog for manual assignment
                            log.info(
                                "run_aquarium_detection.showing_assignment_dialog",
                                video_path=str(video_path),
                            )

                            # Get multi_aquarium_config from project calibration for regex auto-fill
                            multi_aquarium_config = None
                            calibration = (
                                self.project_manager.project_data.get("calibration", {})
                                if self.project_manager.project_data
                                else {}
                            )
                            if isinstance(calibration, dict):
                                multi_aquarium_dict = calibration.get("multi_aquarium")
                                if multi_aquarium_dict and isinstance(multi_aquarium_dict, dict):
                                    try:
                                        from zebtrack.ui.wizard.models import MultiAquariumData

                                        if multi_aquarium_dict.get("regex_pattern"):
                                            multi_aquarium_config = MultiAquariumData(
                                                **multi_aquarium_dict
                                            )
                                            log.info(
                                                "run_aquarium_detection.multi_aquarium_config_loaded",
                                                regex_pattern=multi_aquarium_config.regex_pattern[
                                                    :50
                                                ],
                                            )
                                    # except Exception justified: non-critical fallback
                                    except Exception as e:
                                        log.warning(
                                            "run_aquarium_detection.multi_aquarium_config_parse_failed",
                                            error=str(e),
                                        )
                            else:
                                log.warning(
                                    "run_aquarium_detection.no_calibration_config",
                                    calibration_type=type(calibration).__name__,
                                )

                            print(
                                "[DIAGNOSTIC] Publishing ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG event"
                            )
                            print(f"[DIAGNOSTIC] video_path={video_path!s}")
                            print(
                                f"[DIAGNOSTIC] has_multi_aquarium_config="
                                f"{bool(multi_aquarium_config)}"
                            )

                            self._publish_event(
                                Events.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
                                {
                                    "video_path": str(video_path),
                                    "available_groups": available_groups,
                                    "multi_aquarium_config": multi_aquarium_config,
                                },
                            )
                            print("[DIAGNOSTIC] Event published")
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

        except Exception as e:  # except Exception justified: event handler fault isolation
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
                    # Fetch multi_aquarium_config from project calibration for regex auto-fill
                    log.info(
                        "multi_auto_detect.showing_assignment_dialog",
                        video_path=str(video_path),
                    )
                    multi_aquarium_config = None
                    calibration = (
                        self.project_manager.project_data.get("calibration", {})
                        if self.project_manager.project_data
                        else {}
                    )

                    if isinstance(calibration, dict):
                        multi_aquarium_dict = calibration.get("multi_aquarium")
                        if multi_aquarium_dict and isinstance(multi_aquarium_dict, dict):
                            try:
                                from zebtrack.ui.wizard.models import MultiAquariumData

                                # Ensure we only create object if regex_pattern exists
                                if multi_aquarium_dict.get("regex_pattern"):
                                    multi_aquarium_config = MultiAquariumData(**multi_aquarium_dict)
                                    log.info(
                                        "multi_auto_detect.multi_aquarium_config_loaded",
                                        regex_pattern=multi_aquarium_config.regex_pattern[:50],
                                    )
                            # except Exception justified: non-critical fallback
                            except Exception as e:
                                log.warning(
                                    "multi_auto_detect.multi_aquarium_config_parse_failed",
                                    error=str(e),
                                )
                        else:
                            log.warning(
                                "multi_auto_detect.no_multi_aquarium_in_calibration",
                                calibration_keys=list(calibration.keys()),
                            )
                    else:
                        log.warning(
                            "multi_auto_detect.calibration_not_dict",
                            calibration_type=type(calibration).__name__,
                        )

                    self._publish_event(
                        Events.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
                        {
                            "video_path": str(video_path),
                            "available_groups": available_groups,
                            "multi_aquarium_config": multi_aquarium_config,
                        },
                    )
            else:
                reason = f"Encontrados {len(polygons)} aquários, esperados {expected_count}"
                log.warning("multi_auto_detect.count_mismatch", reason=reason)
                self._publish_event(
                    Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                    {"video_path": str(video_path), "reason": reason},
                )

        except Exception as e:  # except Exception justified: event handler fault isolation
            log.error("multi_auto_detect.failed", error=str(e), exc_info=True)
            self._publish_event(
                Events.ZONE_MULTI_AUTO_DETECT_FAILED,
                {"video_path": str(video_path), "reason": str(e)},
            )
        finally:
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def _relocate_multi_aquarium_folders(
        self, video_path: str | Path, zone_data: Any, old_parquet_files: dict | None = None
    ) -> None:
        """
        Relocate existing folder (e.g., Sujeito_Indefinido) to correct subject folders.

        This is called after aquarium assignment to move files from the initial
        "Indefinido" folder to properly named folders based on assigned metadata.

        Args:
            video_path: Path to the video file
            zone_data: MultiAquariumZoneData with updated aquarium metadata
            old_parquet_files: Parquet files dict captured BEFORE
                               save_multi_aquarium_zone_data overwrote them. This is needed
                               to find the original Sujeito_Indefinido folder.
        """
        import shutil
        from pathlib import Path

        video_entry = self.project_manager.find_video_entry(path=video_path)
        if not video_entry:
            log.warning("relocate_folders.no_video_entry", video=str(video_path))
            return

        # CRITICAL FIX: Use old_parquet_files if provided, otherwise fallback to video_entry
        # This is needed because save_multi_aquarium_zone_data already overwrote the paths
        parquet_files = (
            old_parquet_files if old_parquet_files else video_entry.get("parquet_files", {})
        )
        if not parquet_files:
            log.info("relocate_folders.no_parquet_files", video=str(video_path))
            return

        # Get first parquet file to find current folder
        first_parquet = next(iter(parquet_files.values()), None)
        if not first_parquet:
            return

        old_folder = Path(first_parquet).parent
        if not old_folder.exists():
            log.warning("relocate_folders.old_folder_missing", folder=str(old_folder))
            return

        # Only relocate if folder name contains "Indefinido"
        if "Indefinido" not in old_folder.name:
            log.debug(
                "relocate_folders.not_indefinido",
                folder_name=old_folder.name,
                hint="Folder already has a specific subject name, skipping relocation",
            )
            return

        log.info(
            "relocate_folders.starting",
            old_folder=str(old_folder),
            aquarium_count=len(zone_data.aquariums),
        )

        # Calculate new folders for each aquarium
        aquarium_configs = []
        for aq in zone_data.aquariums:
            config = {
                "aquarium_id": aq.id,
                "group": aq.group or "Sem_Grupo",
                "subject_id": aq.subject_id or "",
                "day": int(aq.day) if aq.day else 1,
            }
            aquarium_configs.append(config)

        new_folders = self.project_manager.resolve_multi_aquarium_results_directories(
            experiment_id=Path(video_path).stem,
            aquarium_configs=aquarium_configs,
        )

        # Move files to new folders (but only the initial parquet, not all files!)
        # The arena parquet should be copied to BOTH aquarium folders
        for aq_id, new_folder in new_folders.items():
            # Copy arena parquet to each aquarium folder
            for _key, old_file_path in parquet_files.items():
                old_file = Path(old_file_path)
                if old_file.exists() and old_file.parent == old_folder:
                    new_file = new_folder / old_file.name
                    try:
                        shutil.copy2(old_file, new_file)
                        log.info(
                            "relocate_folders.file_copied",
                            file=old_file.name,
                            aq_id=aq_id,
                            new_folder=str(new_folder),
                        )
                    except OSError as e:
                        log.error(
                            "relocate_folders.copy_failed",
                            file=old_file.name,
                            error=str(e),
                        )

        # CORREÇÃO: Usar shutil.rmtree para remover pasta Sujeito_Indefinido completamente
        # A lógica anterior só funcionava se a pasta estivesse vazia, mas podem haver
        # outros arquivos (como _bg.png) que não são removidos individualmente
        try:
            if old_folder.exists() and "Indefinido" in old_folder.name:
                shutil.rmtree(old_folder, ignore_errors=True)
                log.info("relocate_folders.old_folder_removed", folder=str(old_folder))

                # Also try to remove parent if it becomes empty (e.g., Dia_01 folder)
                parent = old_folder.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    # And group folder
                    group_parent = parent.parent
                    if group_parent.exists() and not any(group_parent.iterdir()):
                        group_parent.rmdir()
        except OSError as e:
            log.warning("relocate_folders.cleanup_failed", folder=str(old_folder), error=str(e))

        # IMPORTANT: Update video entry with new folder paths
        # For multi-aquarium, we'll update the first aquarium's folder as primary
        if 0 in new_folders:
            primary_folder = new_folders[0]
            # Update parquet file paths to point to primary aquarium folder
            updated_parquet_files = {}
            for key, old_file_path in video_entry.get("parquet_files", {}).items():
                # Note: old_file_path might have been deleted, but we need its NAME
                filename = Path(old_file_path).name
                new_file = primary_folder / filename
                updated_parquet_files[key] = str(new_file.as_posix())

            video_entry["parquet_files"] = updated_parquet_files
            self.project_manager.save_project()

        log.info(
            "relocate_folders.completed",
            old_folder=str(old_folder),
            new_folders=[str(f) for f in new_folders.values()],
        )

    def _on_aquarium_assignment_completed(self, data: dict) -> None:
        """Handle completion of aquarium assignment (group/subject/day).

        Updates the MultiAquariumZoneData with the assigned metadata.
        """
        log.info(
            "assignment_complete.handler_called",
            data_type=type(data).__name__,
            has_configs=bool(data.get("configs")) if isinstance(data, dict) else False,
        )

        if not isinstance(data, dict):
            return

        video_path = data.get("video_path")
        configs = data.get("configs")  # List of dicts or AquariumConfig objects
        apply_to_all = data.get("apply_to_all", False)

        log.info(
            "assignment_complete.data_extracted",
            video_path=video_path,
            configs_count=len(configs) if configs else 0,
            apply_to_all=apply_to_all,
        )

        if not video_path or not configs:
            log.warning(
                "assignment_complete.missing_data", video_path=video_path, has_configs=bool(configs)
            )
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
                # Support both dict and AquariumConfig Pydantic objects
                if hasattr(config, "aquarium_id"):
                    # AquariumConfig object
                    aq_id = config.aquarium_id
                    group = config.group
                    subject_id = config.subject_id
                    day = config.day if hasattr(config, "day") else "1"
                else:
                    # dict format
                    aq_id = config.get("aquarium_id")
                    group = config.get("group")
                    subject_id = config.get("subject_id")
                    day = config.get("day", "1")

                log.debug(
                    "assignment_complete.processing_config",
                    aq_id=aq_id,
                    group=group,
                    subject_id=subject_id,
                    day=day,
                )

                # Find matching aquarium
                target_aq = next((aq for aq in zone_data.aquariums if aq.id == aq_id), None)
                if target_aq:
                    target_aq.group = group
                    target_aq.subject_id = subject_id
                    target_aq.day = int(day) if day else 1
                    updated = True
                    log.info(
                        "assignment_complete.aquarium_updated",
                        aq_id=aq_id,
                        group=group,
                        subject_id=subject_id,
                    )
                else:
                    log.warning(
                        "assignment_complete.aquarium_not_found",
                        aq_id=aq_id,
                        available_ids=[aq.id for aq in zone_data.aquariums],
                    )

            # 3. Save updated data
            if updated:
                # SYNC: Update main video entry metadata for multi-subject support
                # This ensures the UI tree shows all subjects for this video
                video_entry = self.project_manager.find_video_entry(path=video_path)

                # FIX: Ensure video is registered in project batches
                # This fixes the bug where multi-aquarium zone configuration saves
                # zone data but doesn't add the video to batches, causing
                # "video not in project" error when trying to process.
                if not video_entry:
                    log.info(
                        "assignment_complete.registering_video",
                        video=os.path.basename(str(video_path)),
                        reason="video_not_in_batches_adding_now",
                    )
                    # Create minimal video entry
                    from pathlib import Path

                    video_dict = {
                        "path": Path(video_path).as_posix(),
                        "status": "pending",
                        "has_arena": True,  # We have multi-aquarium zones
                        "has_rois": any(bool(aq.roi_polygons) for aq in zone_data.aquariums),
                        "is_multi_aquarium": True,
                        "num_aquariums": len(zone_data.aquariums),
                        "zones_finalized": False,
                    }
                    self.project_manager.add_video_batch([video_dict], save_project=False)
                    # Re-fetch the entry after adding
                    video_entry = self.project_manager.find_video_entry(path=video_path)

                    if not video_entry:
                        log.error(
                            "assignment_complete.video_still_not_found",
                            video=video_path,
                        )
                        return

                if video_entry:
                    video_meta = video_entry.get("metadata", {})

                    # Store individual subject entries for tree expansion
                    subject_entries = []
                    for aq in zone_data.aquariums:
                        subject_entries.append(
                            {
                                "aquarium_id": aq.id,
                                "subject": aq.subject_id,
                                "group": aq.group,
                                "day": aq.day,
                            }
                        )

                    video_meta["is_multi_subject"] = True
                    video_meta["subject_entries"] = subject_entries

                    # Also keep primary metadata from first aquarium for top-level labeling
                    if zone_data.aquariums:
                        first_aq = zone_data.aquariums[0]
                        video_meta["group"] = first_aq.group
                        video_meta["day"] = first_aq.day
                        # KEEP subject as the first one to avoid 'Indefinido' fallbacks
                        video_meta["subject"] = first_aq.subject_id

                    video_entry["metadata"] = video_meta
                    log.info(
                        "assignment_complete.multi_subject_metadata_synced",
                        video=os.path.basename(video_path),
                        subject_count=len(subject_entries),
                    )

                # CRITICAL FIX: Capture old parquet files BEFORE save overwrites them
                # This allows _relocate_multi_aquarium_folders to find the Sujeito_Indefinido folder
                old_parquet_files = (
                    dict(video_entry.get("parquet_files", {})) if video_entry else {}
                )

                should_persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path, zone_data, persist=should_persist
                )

                # 3.1. Relocate existing "Sujeito_Indefinido" folder to correct subject folders
                # Pass old_parquet_files so we can find the original folder
                if self.project_manager.project_path:
                    self._relocate_multi_aquarium_folders(video_path, zone_data, old_parquet_files)

                # Mark as assigned (idempotency)
                self._assigned_videos.add(video_key)

                # Mark zones as finalized
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

        except Exception as e:  # except Exception justified: event handler fault isolation
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
        valid_paths = [str(v.get("path")) for v in target_videos if v.get("path")]
        expected_roi_names = self._find_project_roi_names(valid_paths) if valid_paths else None

        for video in target_videos:
            state = None
            try:
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                    expected_roi_names=expected_roi_names,
                )
            except Exception as exc:  # except Exception justified: non-critical fallback
                state, info_msg, _ppath, changed = "failed", str(exc), None, False

            if state == "completed":
                completed.append(info_msg or "(desconhecido)")
                data_changed = data_changed or bool(changed)
            else:
                skipped.append(info_msg.split(":")[0] if info_msg else "(desconhecido)")
                details.append(f"• {info_msg}")

        if data_changed and self.project_manager.project_path:
            self.project_manager.save_project()

        # Capture batch state BEFORE scheduling finalize via root.after,
        # because _finalize_batch_context() may clear _batch_context before
        # finalize() runs on the main thread, causing a race condition.
        is_batch = self._is_batch_processing()

        def finalize() -> None:
            if completed:
                status_msg = f"Σ Sumários atualizados: {len(completed)} vídeo(s)."
                # CORREÇÃO: Suprimir diálogos em modo batch
                if not is_batch:
                    self._publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Sumários Gerados",
                            "message": "Sumários parquet atualizados para "
                            f"{len(completed)} vídeo(s).\n"
                            + "\n".join(f"• {item}" for item in completed),
                        },
                    )
            else:
                status_msg = "Nenhum sumário foi atualizado."

            if details:
                # CORREÇÃO: Suprimir diálogos em modo batch
                if not is_batch:
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
                log.debug(
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

        except Exception as e:  # except Exception justified: non-critical fallback
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
                for apt in adjusted_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(apt), False)
                    if result < 0:
                        points_outside += 1

                # If adjustment worked, use adjusted points
                if points_outside == 0:
                    roi_points = [[int(pt[0]), int(pt[1])] for pt in adjusted_points]

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
            zone_data.roi_polygons = list(zone_data.roi_polygons)
            zone_data.roi_names = list(zone_data.roi_names)
            zone_data.roi_colors = list(zone_data.roi_colors)
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

        except Exception as e:  # except Exception justified: non-critical fallback
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
            except (AttributeError, RuntimeError):
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
            log.debug("processing_coordinator.determine_mode.settings_attr_missing", exc_info=True)
        # resolver returned None and settings were never synced).
        try:
            resolved = self._resolve_single_animal_mode(None)
            if resolved is True:
                log.info(
                    "controller.determine_processing_mode.project_data_fallback",
                    result="SINGLE_SUBJECT",
                )
                return ProcessingMode.SINGLE_SUBJECT
        except Exception:  # except Exception justified: non-critical fallback
            log.warning(
                "processing_coordinator.determine_mode.resolve_fallback_failed", exc_info=True
            )

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

        IMPORTANT (race-condition fix): We set view._active_processing_mode
        SYNCHRONOUSLY here so that any deferred code that reads it (e.g.
        start_analysis_view_mode triggered by StateManager observers) will
        see the correct value immediately.  The full UI update (label text,
        selector state) is still scheduled via the event-bus queue.
        """
        mode = mode_override or self._determine_processing_mode()
        if not force and mode == getattr(self, "_active_processing_mode", None):
            return ProcessingReport(mode=mode, source=source)

        self._active_processing_mode = mode
        report = ProcessingReport(mode=mode, source=source)

        # ── Synchronous attribute set (race-condition fix) ──────────────
        # The deferred schedule (event-bus queue polled every ~50 ms) can
        # arrive AFTER start_analysis_view_mode() reads the field.  Setting
        # the attribute directly ensures the correct value is always
        # available, regardless of scheduling order.
        if self.view and hasattr(self.view, "_active_processing_mode"):
            self.view._active_processing_mode = mode

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
        if resolved_tracker_pref is None and resolved_mode is not None:
            resolved_tracker_pref = bool(resolved_mode)
            log.info(
                "controller.processing.single_subject_tracker.inferred_from_single_animal",
                enabled=resolved_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

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
            worker_running = bool(self.processing_worker and self.processing_worker.is_running)
            thread_running = bool(self.processing_thread and self.processing_thread.is_alive())
            live_session_active = self._is_live_session_currently_active(processing_state)

            if not live_session_active and not worker_running and not thread_running:
                log.warning(
                    "processing_coordinator.validation.stale_processing_state",
                    current_video=processing_state.current_video,
                )
                self.state_manager.update_processing_state(
                    source="processing_coordinator.validation.stale_reset",
                    is_processing=False,
                    current_video=None,
                    cancel_requested=False,
                    is_live_session_active=False,
                )
                if self.view:
                    self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
                    self.ui_coordinator.hide_progress_bar(self.view)
                    self.ui_coordinator.set_status(self.view, "Pronto.")
                self._publish_processing_mode(source="validation.stale_reset", force=True)
            else:
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

    def _is_live_session_currently_active(self, processing_state: Any) -> bool:
        """Return whether a live session is truly active (not only a stale state flag)."""
        state_flag = bool(getattr(processing_state, "is_live_session_active", False))
        if not state_flag:
            return False

        controller = getattr(self.view, "controller", None) if self.view else None
        session_coordinator = (
            getattr(controller, "session_coordinator", None) if controller else None
        )
        if session_coordinator is None:
            return state_flag

        is_active_fn = getattr(session_coordinator, "is_live_session_active", None)
        if callable(is_active_fn):
            try:
                is_active = is_active_fn()
                if isinstance(is_active, bool):
                    return is_active
            except (AttributeError, RuntimeError):
                log.warning(
                    "processing_coordinator.validation.live_session_probe_failed",
                    exc_info=True,
                )

        live_camera_service = getattr(session_coordinator, "live_camera_service", None)
        camera = getattr(live_camera_service, "camera", None) if live_camera_service else None
        return camera is not None

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
            except (OSError, KeyError, ValueError) as e:
                log.debug("processing_coordinator.zone_lookup_failed", video=path, error=str(e))
                continue

        log.warning("processing_coordinator.no_project_rois_found")
        return None

    def generate_unified_report(
        self,
        video_paths: list[str] | None = None,
        *,
        replace_existing: bool = False,
        report_scope: str = "all",
    ) -> None:
        """Generate a unified report aggregating data from multiple videos."""
        if not video_paths:
            return

        scope = "selected" if report_scope == "selected" else "all"
        log.info(
            "workflow.unified_report.start",
            count=len(video_paths),
            scope=scope,
            replace_existing=replace_existing,
        )
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatório unificado..."})

        project_path = self.project_manager.project_path
        if not project_path:
            return

        unified_dir = Path(project_path) / "unified_reports"
        unified_dir.mkdir(parents=True, exist_ok=True)

        if replace_existing:
            self._cleanup_unified_reports(unified_dir)

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
                    for roi_name, color in zip(
                        zone_data.roi_names, zone_data.roi_colors, strict=True
                    ):
                        # Store first color encountered for each ROI name
                        if roi_name not in roi_colors_map:
                            roi_colors_map[roi_name] = color
            except (OSError, KeyError, ValueError) as e:
                log.debug(
                    "workflow.unified_report.color_collection_failed", path=path, error=str(e)
                )

            # Find summary parquet
            # Handle multi-aquarium entries
            multi_outputs = entry.get("multi_aquarium_outputs")

            entries_to_process = []
            if multi_outputs:
                exp_id = entry.get("experiment_id", os.path.splitext(os.path.basename(path))[0])
                fresh_meta = self.project_manager.get_metadata_for_experiment(
                    exp_id, video_path=path
                )
                # Add sub-entries
                for aq_id, out_info in multi_outputs.items():
                    entries_to_process.append(
                        {
                            "parquet_files": out_info.get("parquet_files", {}),
                            "metadata": {
                                "group": out_info.get("group") or fresh_meta.get("group"),
                                "group_id": out_info.get("group") or fresh_meta.get("group_id"),
                                "subject": out_info.get("subject_id") or fresh_meta.get("subject"),
                                "day": out_info.get("day") or fresh_meta.get("day"),
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
                # Standard Single Video Entry
                exp_id = entry.get("experiment_id", os.path.splitext(os.path.basename(path))[0])

                # Retrieve robust metadata (incl. project structure override)
                # This ensures we get group/subject even if not in "metadata" subkey
                fresh_meta = self.project_manager.get_metadata_for_experiment(
                    exp_id, video_path=path
                )

                entries_to_process.append(
                    {
                        "parquet_files": entry.get("parquet_files", {}),
                        "metadata": fresh_meta,
                        "experiment_id": exp_id,
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
                    except Exception as e:  # except Exception justified: non-critical fallback
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
                final_df,
                unified_dir,
                roi_colors_map,
                schema_mismatch,
                all_columns,
                report_scope=scope,
            )
        except Exception as e:  # except Exception justified: complex multi-subsystem pipeline
            log.error("workflow.unified_report.failed", error=str(e), exc_info=True)
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro no Relatório", "message": f"{e}"},
            )
        finally:
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

    def _align_and_concatenate_unified_dfs(self, dfs: list) -> tuple:
        """Align and concatenate multiple summary DataFrames with potentially different schemas.

        Args:
            dfs: List of pandas DataFrames to concatenate.

        Returns:
            Tuple of (final_df, schema_mismatch, all_columns):
            - final_df: Concatenated DataFrame with aligned columns
            - schema_mismatch: True if DFs had different column sets
            - all_columns: List of all unique column names
        """
        import pandas as pd

        if not dfs:
            return pd.DataFrame(), False, []

        if len(dfs) == 1:
            return dfs[0], False, list(dfs[0].columns)

        # Phase 4.1: Standardize columns (Portuguese -> English/Internal) before merging
        # This prevents "schema mismatch" due to mixed language headers and ensures
        # correct aggregation of metrics like 'distancia_total_cm' + 'total_distance_cm'
        from zebtrack.analysis.data_transformer import DataTransformer

        standardized_dfs = []
        for df in dfs:
            # Create rename mapping based on known translations
            # DataTransformer.translate_column_name handles standard metrics
            rename_map = {}
            for col in df.columns:
                translated = DataTransformer.translate_column_name(col)
                if translated != col:
                    rename_map[col] = translated

            # Apply renaming if needed
            if rename_map:
                df = df.rename(columns=rename_map)

            # CRITICAL FIX: After renaming, we might have duplicate columns
            # (e.g., if 'distancia' became 'distance' but 'distance' already existed).
            # We must drop duplicates to avoid
            # "Reindexing only valid with uniquely valued Index objects"
            if df.columns.duplicated().any():
                df = df.loc[:, ~df.columns.duplicated()]

            standardized_dfs.append(df)

        # Update the list to use for concatenation
        dfs = standardized_dfs

        # Collect all unique columns
        all_columns_set: set[str] = set()
        for df in dfs:
            all_columns_set.update(df.columns)

        # Priority columns that should appear first (identification)
        priority_cols = [
            "group",
            "subject",
            "day",
            "experiment_id",
            "aquarium_id",
            "is_multi_aquarium",
        ]

        # Separate priority columns that exist from the rest
        priority_present = [c for c in priority_cols if c in all_columns_set]
        other_cols = sorted(c for c in all_columns_set if c not in priority_cols)

        # Final column order: priority first, then alphabetically sorted rest
        all_columns = priority_present + other_cols

        # Check for schema mismatch
        reference_cols = set(dfs[0].columns)
        schema_mismatch = any(set(df.columns) != reference_cols for df in dfs[1:])

        # Align all DataFrames to have same columns
        aligned_dfs = [df.reindex(columns=all_columns) for df in dfs]

        # Filter out empty dataframes to avoid FutureWarning
        non_empty_dfs = [df for df in aligned_dfs if not df.empty]
        if not non_empty_dfs:
            # If all were empty, return a new empty DF with the expected columns
            final_df = pd.DataFrame(columns=all_columns)
        else:
            import warnings

            with warnings.catch_warnings():
                # Suppress the FutureWarning about all-NA columns in concat
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    message=".*concatenation with empty or all-NA entries.*",
                )
                final_df = pd.concat(non_empty_dfs, ignore_index=True)
        return final_df, schema_mismatch, all_columns

    def _cleanup_unified_reports(self, unified_dir: Path) -> None:
        """Remove previous unified report artifacts before a fresh export run."""
        patterns = [
            "*.docx",
            "*.xlsx",
            "*.parquet",
            "unified_run_*.json",
            "latest_unified_run.json",
        ]

        removed = 0
        for pattern in patterns:
            for artifact in unified_dir.glob(pattern):
                if not artifact.is_file():
                    continue
                try:
                    artifact.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    log.warning(
                        "workflow.unified_report.cleanup_failed",
                        file=str(artifact),
                        exc_info=True,
                    )

        log.info("workflow.unified_report.cleanup_completed", removed=removed, dir=str(unified_dir))

    def _export_unified_reports(
        self,
        final_df,
        unified_dir: Path,
        roi_colors_map: dict,
        schema_mismatch: bool,
        all_columns: list,
        *,
        report_scope: str = "all",
    ) -> None:
        """Export unified reports (Parquet, Excel, and Word) from concatenated DataFrame.

        Args:
            final_df: Concatenated DataFrame with all summaries.
            unified_dir: Directory to save the unified reports.
            roi_colors_map: Dict mapping ROI names to RGB color tuples.
            schema_mismatch: Whether there was a schema mismatch between DataFrames.
            all_columns: List of all column names in the final DataFrame.
        """
        from datetime import datetime

        from zebtrack.analysis.reporter import Reporter

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        scope_prefix = "unified_partial" if report_scope == "selected" else "unified"

        exported_artifacts: list[str] = []
        export_failures: list[str] = []
        exported_paths: dict[str, str] = {}

        # 1. Export Parquet (raw data)
        parquet_path = unified_dir / f"{scope_prefix}_summary_{run_id}.parquet"
        try:
            final_df.to_parquet(parquet_path, index=False)
            exported_artifacts.append(parquet_path.name)
            exported_paths["parquet"] = str(parquet_path)
            log.info("workflow.unified_report.parquet_exported", path=str(parquet_path))
        except (OSError, ValueError) as e:
            export_failures.append(f"Parquet: {e}")
            log.error("workflow.unified_report.parquet_failed", error=str(e), exc_info=True)

        # 2. Export Excel
        excel_path = unified_dir / f"{scope_prefix}_summary_{run_id}.xlsx"
        try:
            # Apply display formatting for Excel
            from zebtrack.analysis.data_transformer import DataTransformer

            display_df = DataTransformer().prepare_for_display(final_df)
            display_df.to_excel(excel_path, index=False, engine="openpyxl")
            exported_artifacts.append(excel_path.name)
            exported_paths["excel"] = str(excel_path)
            log.info("workflow.unified_report.excel_exported", path=str(excel_path))
        except Exception as e:  # except Exception justified: non-critical fallback
            export_failures.append(f"Excel: {e}")
            log.error("workflow.unified_report.excel_failed", error=str(e), exc_info=True)

        # 3. Export Word using Reporter.export_project_report
        word_path = unified_dir / f"{scope_prefix}_report_{run_id}"
        try:
            # BUGFIX: Reporter cannot handle pandas NA values - convert to np.nan
            # This happens when DataFrames with different schemas are merged (schema mismatch)
            import numpy as np

            word_df = final_df.copy()
            # Replace pandas NA with numpy nan which Reporter can handle
            for col in word_df.columns:
                word_df[col] = (
                    word_df[col].where(word_df[col].notna(), np.nan).infer_objects(copy=False)
                )

            Reporter.export_project_report(
                aggregated_df=word_df,
                output_path=word_path,
                roi_colors=roi_colors_map if roi_colors_map else None,
                detector_params=None,
            )
            exported_artifacts.append(f"{word_path.name}.docx")
            exported_paths["word"] = f"{word_path}.docx"
            log.info("workflow.unified_report.word_exported", path=str(word_path) + ".docx")
        except Exception as e:  # except Exception justified: non-critical fallback
            export_failures.append(f"Word: {e}")
            log.error("workflow.unified_report.word_failed", error=str(e), exc_info=True)

        if not exported_artifacts:
            failure_details = "\n".join(f"• {item}" for item in export_failures[:3])
            raise RuntimeError(
                "Não foi possível gerar nenhum arquivo do relatório unificado."
                + (f"\n\nDetalhes:\n{failure_details}" if failure_details else "")
            )

        if export_failures:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Relatório Unificado Parcial",
                    "message": (
                        "Alguns arquivos não puderam ser gerados.\n"
                        "Gerados: "
                        + ", ".join(exported_artifacts)
                        + "\n\nFalhas:\n"
                        + "\n".join(f"• {item}" for item in export_failures[:3])
                    ),
                },
            )

        self._write_unified_run_manifest(
            unified_dir=unified_dir,
            run_id=run_id,
            report_scope=report_scope,
            exported_paths=exported_paths,
            export_failures=export_failures,
            row_count=len(final_df),
        )

        # 4. Log schema mismatch warning if applicable
        if schema_mismatch:
            log.warning(
                "workflow.unified_report.schema_mismatch",
                message="DataFrames had different column sets; missing values filled with NA",
                columns=all_columns,
            )

            # Emit UI warning unless suppressed
            if not self.settings.ui_features.suppress_roi_mismatch_warning:
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "ROIs Diferentes",
                        "message": (
                            "Os vídeos selecionados possuem ROIs diferentes.\n"
                            "Colunas ausentes foram preenchidas com valores vazios (NA)."
                        ),
                    },
                )

        # 5. Show success message (only if not in batch mode)
        if not self._is_batch_processing():
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Relatório Unificado Parcial"
                    if report_scope == "selected"
                    else "Relatório Unificado",
                    "message": (
                        f"Relatório unificado gerado com sucesso em:\n{unified_dir}\n\n"
                        f"Arquivos: {', '.join(exported_artifacts)}"
                    ),
                },
            )

    def _write_unified_run_manifest(
        self,
        *,
        unified_dir: Path,
        run_id: str,
        report_scope: str,
        exported_paths: dict[str, str],
        export_failures: list[str],
        row_count: int,
    ) -> None:
        """Persist a run manifest so UI can open a consistent file set from same generation."""
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "scope": report_scope,
            "row_count": row_count,
            "artifacts": exported_paths,
            "failures": export_failures,
        }

        manifest_path = unified_dir / f"unified_run_{run_id}.json"
        latest_path = unified_dir / "latest_unified_run.json"

        with manifest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)

        with latest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)

        log.info(
            "workflow.unified_report.manifest_written",
            run_id=run_id,
            path=str(manifest_path),
            artifacts=list(exported_paths.keys()),
        )

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Generate reports (Word, Excel, Parquet) for specified videos."""
        if not video_paths:
            return

        log.info("workflow.reports.start", count=len(video_paths))
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatórios detalhados..."})

        # Pre-generate summaries
        entries = [self.project_manager.find_video_entry(path=p) for p in video_paths]
        self.generate_parquet_summaries([e for e in entries if e], self.settings)

        count, errors = 0, []
        self._ensure_analysis_service_ready()

        for path in video_paths:
            try:
                self._generate_single_video_reports(path)
                count += 1
            except Exception as e:  # except Exception justified: non-critical fallback
                log.exception("workflow.reports.video_failed", video=path, error=str(e))
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
                if dim_key in config:
                    val = config.get(dim_key)
                    if val not in (None, ""):
                        try:
                            metadata[dim_key] = float(str(val))
                        except (TypeError, ValueError):
                            log.debug(
                                "processing_coordinator.metadata_dim_parse.suppressed",
                                dim_key=dim_key,
                                exc_info=True,
                            )

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

    def _enrich_unified_report_metadata(
        self, df: pd.DataFrame, entry_meta: dict, process_entry: dict
    ) -> pd.DataFrame:
        """Enrich DataFrame with metadata columns for unified report.

        Args:
            df: The summary DataFrame to enrich.
            entry_meta: Metadata extracted from the video entry.
            process_entry: The full process entry dict containing additional info.

        Returns:
            DataFrame with metadata columns added.
        """
        df = df.copy()

        # Always add identification columns (even if empty, for consistency)
        # Use "N/A" as fallback so rows are identifiable

        # Standardize on 'group_id' to match DataTransformer schema and avoid duplicates
        g_val = entry_meta.get("group") or entry_meta.get("group_id")
        df["group_id"] = g_val or "N/A"

        # Remove 'group' if present to prevent two "Group" columns in Excel (group vs group_id)
        if "group" in df.columns:
            df.drop(columns=["group"], inplace=True)

        df["subject"] = entry_meta.get("subject") or "N/A"
        df["day"] = entry_meta.get("day") or "N/A"

        # Overwrite experiment_id with authoritative value (fixes stale IDs in parquet)
        # Priority: Metadata > Process Entry (filename-based) > Existing DF
        auth_exp_id = entry_meta.get("experiment_id") or process_entry.get("experiment_id")
        if auth_exp_id:
            df["experiment_id"] = auth_exp_id
        elif "experiment_id" not in df.columns:
            df["experiment_id"] = "N/A"

        # Add aquarium_id for multi-aquarium entries
        if "aquarium_id" in entry_meta:
            df["aquarium_id"] = entry_meta["aquarium_id"]

        # Mark if from multi-aquarium entry
        if process_entry.get("is_multi"):
            df["is_multi_aquarium"] = True

        return df

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

        self._ensure_analysis_service_ready()
        if not self.analysis_service:
            log.error("workflow.reports.service_not_ready")
            return

        analysis_params = self.analysis_service.collect_analysis_parameters(project_data)
        calib = project_data.get("calibration", {})
        fps = float(self.settings.video_processing.fps)
        probed_w, probed_h = self._probe_video_dimensions(str(path))

        zone_data: ZoneData | MultiAquariumZoneData | None = (
            self.project_manager.get_multi_aquarium_zone_data(video_path=path)
        )
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
            "experiment_id": exp_id,  # CRITICAL FIX: Add experiment_id to metadata
            "group": output_info.get("group", entry.get("metadata", {}).get("group")),
            "subject": output_info.get("subject_id", entry.get("metadata", {}).get("subject")),
        }

        # Geometry
        arena_polygon: list[tuple[float, float]] = []
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

        # CORREÇÃO: Para PNGs pré-cropped, frame_crop_box deve ser None
        # porque a imagem PNG já está cropped e começa em (0, 0)
        # Passar coordenadas absolutas causa offset incorreto no gráfico
        if video_path_report and video_path_report.endswith(".png"):
            frame_crop_for_viz = None
        else:
            frame_crop_for_viz = frame_crop

        service = self.analysis_service
        if not service:
            return

        analysis_result = service.run_full_analysis_as_dto(
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
            frame_crop_box=frame_crop_for_viz,
            behavioral_config=params.get("behavioral_config"),
        )

        self._export_individual_outputs(analysis_result, aq_results_dir, f"{exp_id}_aq{aq_id}")

    def _generate_standard_report(self, path, exp_id, entry, metadata):
        """Generate report for a standard (single aquarium) video."""
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.setdefault("experiment_id", exp_id)
        metadata.setdefault("video_name", exp_id)
        metadata.setdefault("group", "single_video")
        metadata.setdefault("day", "1")
        metadata.setdefault("subject", "1")

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
        project_data = getattr(self.project_manager, "project_data", {}) or {}

        service = self.analysis_service
        if service:
            analysis_params = service.collect_analysis_parameters(project_data)
        else:
            analysis_params = {}
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

        service = self.analysis_service
        if not service:
            return

        analysis_result = service.run_full_analysis_as_dto(
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
                except OSError:
                    log.warning(
                        "processing_coordinator.save_background_frame.failed", exc_info=True
                    )
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
        """Extract a single cropped frame from video.

        Args:
            video_file: Path to video file
            crop_box: Tuple (x, y, w, h) for cropping region

        Returns:
            Cropped numpy array, or None if crop fails or is empty
        """
        if not crop_box:
            return None
        cap = cv2.VideoCapture(video_file)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            log.warning(
                "workflow.report.frame_read_failed",
                video_file=str(video_file),
            )
            return None

        frame_h, frame_w = frame.shape[:2]
        x, y, w, h = map(int, crop_box)

        # CRITICAL FIX: Validate and clamp crop_box to frame bounds
        original_crop = (x, y, w, h)

        # Clamp starting coordinates to valid range
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))

        # Clamp dimensions to fit within frame
        w = min(w, frame_w - x)
        h = min(h, frame_h - y)

        if w <= 0 or h <= 0:
            log.warning(
                "workflow.report.crop_box_invalid",
                original_crop=original_crop,
                frame_size=(frame_w, frame_h),
                reason="crop_box results in empty region after clamping",
            )
            return None

        if (x, y, w, h) != original_crop:
            log.info(
                "workflow.report.crop_box_adjusted",
                original=original_crop,
                adjusted=(x, y, w, h),
                frame_size=(frame_w, frame_h),
            )

        return frame[y : y + h, x : x + w].copy()

    def _finalize_report_generation(self, count, errors):
        """Finalize report generation UI feedback."""
        self._publish_event(Events.UI_SET_STATUS, {"message": "Relatórios gerados."})

        # CORREÇÃO: Suprimir diálogos individuais em modo batch
        # Diálogo consolidado será mostrado ao final de todo o batch
        if self._is_batch_processing():
            return

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
                # Log detailed info about subject assignments for debugging
                subject_info = []
                for aq in multi_data.aquariums:
                    subject_info.append(f"aq{aq.id}={aq.subject_id or 'EMPTY'}")
                log.info(
                    "workflow.multi_aquarium_zone_data_attached",
                    video=os.path.basename(video_path),
                    aquarium_count=len(multi_data.aquariums),
                    subjects=", ".join(subject_info),
                    sequential_processing=multi_data.sequential_processing,
                )

                # Warn if any aquarium has empty subject_id (will cause "Indefinido" folders)
                for aq in multi_data.aquariums:
                    if not aq.subject_id:
                        log.warning(
                            "workflow.multi_aquarium.empty_subject_id",
                            video=os.path.basename(video_path),
                            aquarium_id=aq.id,
                            group=aq.group,
                            hint="Subject was not assigned in the assignment dialog. "
                            "Output will use 'Sujeito_Indefinido' folder.",
                        )

                video_info["zone_data"] = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)
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
                except Exception as exc:  # except Exception justified: non-critical fallback
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

        # CRITICAL: Create project-specific settings settings_snapshot
        # This ensures that summary generation uses project overrides (ROI, Smoothing, etc.)
        # instead of potentially stale or default global settings.
        settings_snapshot = self._create_project_settings_snapshot()

        if multi_outputs:
            return self._process_multi_summary_video(
                video, experiment_id, path, multi_outputs, settings_snapshot, expected_roi_names
            )

        return self._process_standard_summary_video(
            video, experiment_id, path, settings_snapshot, expected_roi_names
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
        except Exception as e:  # except Exception justified: complex multi-subsystem pipeline
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

        behavioral_config = {}
        if self.analysis_service:
            behavioral_config = self.analysis_service.collect_analysis_parameters(
                self.project_manager.project_data
            ).get("behavioral_config", {})

        # Behavioral parameters are now correctly collected by AnalysisService
        # which respects project overrides (synced from UI) > global defaults.

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

            meta = self.project_manager.get_metadata_for_experiment(exp_id, video_path=path) or {
                "experiment_id": exp_id
            }
            behavioral_config = {}
            service = self.analysis_service
            if service:
                behavioral_config = service.collect_analysis_parameters(
                    self.project_manager.project_data
                ).get("behavioral_config", {})

            # Behavioral parameters are now correctly collected by AnalysisService
            # which respects project overrides (synced from UI) > global defaults.

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
        except Exception as e:  # except Exception justified: complex multi-subsystem pipeline
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
