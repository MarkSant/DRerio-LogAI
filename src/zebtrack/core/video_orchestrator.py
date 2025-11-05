"""Video processing orchestration service.

This module contains the VideoOrchestrator class, which coordinates video
processing workflows including single video processing, batch processing,
and video preparation.

Phase: REFACTOR-VIEWMODEL-001
Extracted from: MainViewModel (main_view_model.py)
Purpose: Reduce MainViewModel complexity by extracting video processing logic
"""

import os
import threading
from contextlib import contextmanager

import structlog

from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.settings import Settings
from zebtrack.ui.event_bus import EventBus, Events

log = structlog.get_logger()


class VideoOrchestrator:
    """Orchestrates video processing workflows.

    This class handles:
    - Single video workflow setup and processing
    - Batch video processing
    - Video preparation and validation
    - Processing UI coordination
    - Progress tracking and cancellation

    Responsibilities extracted from MainViewModel to follow
    Single Responsibility Principle.
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        video_processing_service: VideoProcessingService,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        root,
        view=None,
    ):
        """Initialize VideoOrchestrator with dependency injection.

        Args:
            project_manager: Project manager for accessing project data
            video_processing_service: Service for video processing operations
            state_manager: Centralized state manager
            ui_coordinator: UI coordinator for scheduling
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            root: Tkinter root window
            view: Reference to GUI (optional, set after GUI creation)
        """
        self.project_manager = project_manager
        self.video_processing_service = video_processing_service
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.root = root
        self.view = view

        # Note: Threading attributes (cancel_event, processing_thread, processing_worker)
        # are managed by MainViewModel and passed to methods as needed.
        # This coordinator provides operations but doesn't own the threading state.

        log.info("video_orchestrator.initialized")

    def set_view(self, view):
        """Set the view reference after GUI creation.

        Args:
            view: Reference to ApplicationGUI instance
        """
        self.view = view

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config: dict | None):
        """Context manager for temporary single-animal mode override.

        Args:
            single_video_config: Single video configuration dict

        Yields:
            None
        """
        if not single_video_config:
            yield
            return

        original_mode = self.settings.tracking.single_animal_mode
        original_tracker = self.settings.tracking.single_subject_tracker_preference

        try:
            config_single_mode = single_video_config.get("single_animal_mode")
            if config_single_mode is not None:
                self.settings.tracking.single_animal_mode = config_single_mode
                log.debug(
                    "video_orchestrator.temp_mode.single_animal",
                    original=original_mode,
                    override=config_single_mode,
                )

            config_tracker = single_video_config.get("single_subject_tracker_preference")
            if config_tracker is not None:
                self.settings.tracking.single_subject_tracker_preference = config_tracker
                log.debug(
                    "video_orchestrator.temp_mode.tracker",
                    original=original_tracker,
                    override=config_tracker,
                )

            yield

        finally:
            # Restore original settings
            if single_video_config.get("single_animal_mode") is not None:
                self.settings.tracking.single_animal_mode = original_mode
                log.debug("video_orchestrator.temp_mode.restored.single_animal")

            if single_video_config.get("single_subject_tracker_preference") is not None:
                self.settings.tracking.single_subject_tracker_preference = original_tracker
                log.debug("video_orchestrator.temp_mode.restored.tracker")

    def _determine_processing_intervals(
        self, single_video_config: dict | None
    ) -> tuple[int, int]:
        """Determine analysis and display intervals from config or defaults.

        Args:
            single_video_config: Single video configuration dict

        Returns:
            Tuple of (analysis_interval_frames, display_interval_frames)
        """
        if single_video_config:
            analysis_interval = single_video_config.get(
                "analysis_interval_frames",
                self.settings.video_processing.analysis_interval_frames,
            )
            display_interval = single_video_config.get(
                "display_interval_frames",
                self.settings.video_processing.display_interval_frames,
            )
        else:
            # Use project settings or global defaults
            project_data = self.project_manager.project_data or {}
            analysis_interval = project_data.get(
                "analysis_interval_frames",
                self.settings.video_processing.analysis_interval_frames,
            )
            display_interval = project_data.get(
                "display_interval_frames",
                self.settings.video_processing.display_interval_frames,
            )

        log.debug(
            "video_orchestrator.intervals_resolved",
            analysis=analysis_interval,
            display=display_interval,
        )
        return analysis_interval, display_interval

    def _prepare_processing_ui(self, total_videos: int) -> None:
        """Prepare UI for processing by showing progress bar.

        Args:
            total_videos: Total number of videos to process
        """
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_UPDATE_STATUS,
                {
                    "message": f"Iniciando processamento de {total_videos} vídeo(s)...",
                    "show_progress": True,
                },
            )
        )

    def _finalize_processing(
        self, success: bool, cancelled: bool, total_videos: int
    ) -> None:
        """Finalize processing by hiding progress UI and showing completion message.

        Args:
            success: Whether processing completed successfully
            cancelled: Whether processing was cancelled
            total_videos: Total number of videos processed
        """
        # Hide progress bar
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_UPDATE_STATUS,
                {
                    "message": "Processamento concluído",
                    "show_progress": False,
                },
            )
        )

        # Show completion or cancellation message
        if cancelled:
            self.ui_coordinator.schedule_on_ui_thread(
                lambda: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Processamento Cancelado",
                        "message": f"O processamento de {total_videos} vídeo(s) foi cancelado.",
                    },
                )
            )
        elif success:
            self.ui_coordinator.schedule_on_ui_thread(
                lambda: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Concluído",
                        "message": f"{total_videos} vídeo(s) processado(s) com sucesso.",
                    },
                )
            )

    def _activate_analysis_view_mode(self) -> None:
        """Switch UI to analysis tab for proper frame scaling."""
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_SWITCH_TAB,
                {"tab": "analysis"},
            )
        )

    def _classify_candidate_videos(
        self, candidate_entries: list[dict], info_by_norm: dict
    ) -> tuple[list, list, list, list, bool]:
        """Classify videos by readiness status.

        Args:
            candidate_entries: List of candidate video entries
            info_by_norm: Video info indexed by normalized path

        Returns:
            Tuple of (ready_with_trajectory, ready_with_zones, arena_only,
                     without_arena, data_changed)
        """
        ready_with_trajectory = []
        ready_with_zones = []
        arena_only = []
        without_arena = []
        data_changed = False

        for entry in candidate_entries:
            path_norm = os.path.normpath(entry.get("path", ""))
            info = info_by_norm.get(path_norm)
            if not info:
                continue

            has_trajectory = info.get("has_trajectory", False)
            has_arena = info.get("has_arena", False)
            has_rois = info.get("has_rois", False)

            # Update entry with current status
            entry.update(info)
            data_changed = True

            # Classify by readiness
            if has_trajectory:
                ready_with_trajectory.append(entry)
            elif has_rois:
                ready_with_zones.append(entry)
            elif has_arena:
                arena_only.append(entry)
            else:
                without_arena.append(entry)

        log.info(
            "video_orchestrator.classification_complete",
            with_trajectory=len(ready_with_trajectory),
            with_zones=len(ready_with_zones),
            arena_only=len(arena_only),
            without_arena=len(without_arena),
        )

        return (
            ready_with_trajectory,
            ready_with_zones,
            arena_only,
            without_arena,
            data_changed,
        )

    def cancel_processing(
        self,
        cancel_event: threading.Event,
        processing_thread: threading.Thread | None,
        processing_worker,
    ) -> None:
        """Request cancellation of active processing.

        Args:
            cancel_event: Cancel event to set
            processing_thread: Processing thread to check
            processing_worker: Processing worker to check

        Sets the cancel event and updates state manager.
        """
        worker_running = bool(processing_worker and hasattr(processing_worker, 'is_running')
                            and processing_worker.is_running)
        thread_running = bool(processing_thread and processing_thread.is_alive())

        if not worker_running and not thread_running:
            log.info("video_orchestrator.cancel.no_active_processing")
            return

        log.info("video_orchestrator.cancel.requested")
        cancel_event.set()

        # Update state
        self.state_manager.update_processing_state(
            source="video_orchestrator.cancel",
            cancel_requested=True,
        )

        # Show feedback
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_UPDATE_STATUS,
                {"message": "Cancelando processamento..."},
            )
        )
