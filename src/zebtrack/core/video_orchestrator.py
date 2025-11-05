"""Video processing orchestration service for ZebTrack-AI.

Extracted from MainViewModel (Task 2.2: REFACTOR-VIEWMODEL-001).
Handles video processing workflows, batch processing, and analysis coordination.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.gui import ApplicationGUI

import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.core.processing_worker import ProcessingCallbacks, ProcessingContext, ProcessingWorker
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.io.recorder import Recorder
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

log = structlog.get_logger()


class VideoOrchestrator:
    """
    Coordinates video processing workflows.

    Responsibilities:
    - Project-based batch processing workflows
    - Single video processing workflows
    - Video selection and validation
    - Processing callbacks and UI coordination
    - Analysis pipeline orchestration

    Phase: Task 2.2 (REFACTOR-VIEWMODEL-001)
    Extracted from: MainViewModel (video processing methods, ~800 lines)
    """

    def __init__(
        self,
        root,
        view: ApplicationGUI,
        state_manager: StateManager,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        project_manager: ProjectManager,
        video_processing_service: VideoProcessingService,
        analysis_service: AnalysisService,
        recorder: Recorder,
    ):
        """Initialize VideoOrchestrator with dependency injection.

        Args:
            root: Tkinter root window
            view: Application GUI instance
            state_manager: Centralized state manager
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            video_processing_service: Video processing service
            analysis_service: Analysis service
            recorder: Recorder for Parquet output
        """
        self.root = root
        self.view = view
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.project_manager = project_manager
        self.video_processing_service = video_processing_service
        self.analysis_service = analysis_service
        self.recorder = recorder

        # Processing state
        self.processing_thread: threading.Thread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.cancel_event = threading.Event()
        self._cancel_feedback_displayed = False

    # =============================================================================
    # PROJECT-BASED WORKFLOW (Main Entry Point)
    # =============================================================================

    def start_project_processing_workflow(self) -> None:
        """Start project-based video processing workflow with zone validation.

        Entry point for processing videos in a project context.
        Validates zones and detector before initiating processing.
        """
        log.info("video_orchestrator.project_workflow.start")

        if self.processing_thread and self.processing_thread.is_alive():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Análise em Andamento",
                    "message": "Uma análise de vídeo já está em andamento. "
                    "Por favor, aguarde ou cancele a análise atual.",
                },
            )
            return

        # Validation 1: Project exists
        if not self.project_manager.project_path:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Nenhum projeto carregado"}
                )
            return

        # Validation 2: Zones defined
        zone_data = self.project_manager.get_zone_data()
        if not zone_data or not zone_data.polygon:
            log.warning("video_orchestrator.project_workflow.no_main_arena")

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É necessário definir a arena principal para análise precisa.\n"
                "Deseja definir agora antes de processar?",
            )

            if response:
                # Switch to zone tab
                self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                # Load frame from first video if available
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )

                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Defina a Arena Principal",
                        "message": "Por favor:\n"
                        "1. Use 'Detectar Aquário (Auto)' ou\n"
                        "2. Desenhe manualmente o polígono principal\n"
                        "3. Depois volte para adicionar vídeos",
                    },
                )
                return
            else:
                # Offer default arena as fallback
                if not self.view.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    log.info("video_orchestrator.project_workflow.cancelled_no_arena")
                    return

                # Create default arena based on first video
                first_video = self.project_manager.get_next_video()
                if first_video:
                    import cv2

                    cap = cv2.VideoCapture(first_video)
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()

                    default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                    # Note: This calls back to MainViewModel's method
                    # TODO: Extract set_main_arena_polygon to ArenaCoordinator
                    success = self._set_main_arena_polygon_callback(default_arena)
                    if success:
                        log.info(
                            "video_orchestrator.project_workflow.default_arena_created",
                            size=f"{width}x{height}",
                        )
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_INFO,
                            {
                                "title": "Arena Padrão Criada",
                                "message": f"Arena padrão criada ({width}x{height})\n"
                                "Recomenda-se ajustar manualmente depois.",
                            },
                        )
                    else:
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {"title": "Erro", "message": "Não foi possível criar arena padrão"},
                        )
                        return
                else:
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Erro",
                            "message": "Não há vídeos no projeto para determinar dimensões.",
                        },
                    )
                    return

        # Proceed to add videos dialog
        # Note: This event is handled by the view
        self.ui_event_bus.publish_event(Events.UI_OPEN_ADD_VIDEOS_DIALOG)

    def set_arena_callback(self, callback) -> None:
        """Set callback for setting main arena polygon.

        This is a temporary solution until ArenaCoordinator is extracted.

        Args:
            callback: Function that accepts polygon and returns success bool
        """
        self._set_main_arena_polygon_callback = callback

    # =============================================================================
    # BATCH PROCESSING (Main Orchestrator)
    # =============================================================================

    def process_pending_project_videos(
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """Process videos in project that have pending data.

        This is the main entry point for batch video processing.
        Handles video selection, validation, and processing orchestration.

        Args:
            video_paths: Optional list of specific video paths to process.
                        If None, processes all pending videos.
        """
        log.info(
            "video_orchestrator.process_pending.start",
            targeted=len(video_paths or []),
        )

        if self.processing_thread and self.processing_thread.is_alive():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Análise em Andamento",
                    "message": "Um processamento já está ativo. Aguarde a conclusão ou "
                    "cancele a análise atual antes de iniciar um novo lote.",
                },
            )
            return

        if not self.project_manager.project_path:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Nenhum projeto carregado"}
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo cadastrado no projeto atualmente.",
                    },
                )
            return

        # Gather candidate videos
        skip_dialog = bool(video_paths)
        candidate_entries = self._gather_candidate_entries(video_paths, all_videos)
        if candidate_entries is None:
            return

        # Scan and validate video files
        info_by_norm, missing_files, scanned_videos = self._scan_and_validate_candidate_paths(
            candidate_entries
        )
        if info_by_norm is None:
            return

        # Classify videos by processing status
        (
            ready_with_trajectory,
            ready_with_zones,
            arena_only,
            without_arena,
            data_changed,
        ) = self._classify_candidate_videos(candidate_entries, info_by_norm)

        if data_changed:
            self.project_manager.save_project()

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo elegível foi encontrado com dados suficientes para análise.",
                },
            )
            return

        # Select videos to process (with optional user dialog)
        eligible_videos = self._select_eligible_videos(
            skip_dialog, ready_with_trajectory, ready_with_zones, arena_only, without_arena
        )
        if eligible_videos is None:
            return

        # Load zones from videos if available
        zones_updated = self._load_zones_from_videos(eligible_videos)
        if zones_updated:
            self.project_manager.save_project()

        # Start processing
        self._start_batch_processing(eligible_videos)

    def _start_batch_processing(self, eligible_videos: list[dict]) -> None:
        """Start batch processing for eligible videos.

        Args:
            eligible_videos: List of video info dicts to process
        """
        self.cancel_event.clear()

        # For project-based processing, single_video_config must be None
        # to ensure hierarchical directory structure (group/day/subject)
        # is used instead of single video fallback path
        callbacks = self._create_processing_callbacks(eligible_videos)
        context = self._create_processing_context(
            eligible_videos,
            self.project_manager.project_path,
            single_video_config=None,  # None = project mode, uses metadata for paths
        )

        self._cancel_feedback_displayed = False
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        # Activate analysis view mode (via UI event or callback)
        if hasattr(self, "_activate_analysis_view_mode_callback"):
            self._activate_analysis_view_mode_callback()

        # Update video statuses
        for video_info in eligible_videos:
            path_value = video_info.get("path")
            if path_value:
                self.project_manager.update_video_status(path_value, "complete")

        # Notify user
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

        message = f"O processamento de {len(eligible_videos)} vídeo(s) foi iniciado em segundo plano."
        if preview_lines:
            message += "\n\nFila:\n" + "\n".join(preview_lines)

        self.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO, {"title": "Processamento Iniciado", "message": message}
        )

        log.info(
            "video_orchestrator.process_pending.started",
            count=len(eligible_videos),
        )

    # =============================================================================
    # HELPER METHODS (Video Selection & Validation)
    # =============================================================================

    def _gather_candidate_entries(
        self,
        video_paths: list[str] | None,
        all_videos: list[dict],
    ) -> list[dict] | None:
        """Gather candidate video entries to process.

        Returns None if should abort (user cancel or invalid selection).

        Args:
            video_paths: Optional list of specific paths to target
            all_videos: All videos in project

        Returns:
            List of candidate video entries or None to abort
        """
        videos_by_norm: dict[str, dict] = {}
        for video in all_videos:
            path_value = video.get("path")
            if isinstance(path_value, str) and path_value:
                videos_by_norm[os.path.normpath(path_value)] = video

        if video_paths:
            # Specific videos targeted
            normalized_targets: list[str] = []
            raw_lookup: dict[str, str] = {}
            for raw_path in video_paths:
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                norm_path = os.path.normpath(raw_path)
                normalized_targets.append(norm_path)
                raw_lookup.setdefault(norm_path, raw_path)

            if not normalized_targets:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo selecionado para processamento.",
                    },
                )
                return None

            candidate_entries = [
                videos_by_norm[norm_path]
                for norm_path in normalized_targets
                if norm_path in videos_by_norm
            ]

            missing_targets = [
                norm_path for norm_path in normalized_targets if norm_path not in videos_by_norm
            ]
            if missing_targets:
                sample = [os.path.basename(raw_lookup[norm]) for norm in missing_targets[:5]]
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

            if not candidate_entries:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                    },
                )
                return None

            return candidate_entries
        else:
            # All pending videos
            candidate_entries = [
                video
                for video in all_videos
                if video.get("status") not in {"processed", "complete"}
            ]
            if not candidate_entries:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo pendente para ser processado.",
                    },
                )
                return None
            return candidate_entries

    def _scan_and_validate_candidate_paths(
        self, candidate_entries: list[dict]
    ) -> tuple[dict | None, list, list]:
        """Scan and validate candidate video file paths.

        Args:
            candidate_entries: List of candidate video dicts

        Returns:
            Tuple of (info_by_norm dict or None, missing_files list, scanned_videos list)
        """
        # Placeholder: In actual implementation, this would:
        # - Check file existence
        # - Read video metadata (dimensions, fps, frames)
        # - Validate parquet files
        # - Return video info indexed by normalized path

        # For now, return simple validation
        info_by_norm = {}
        missing_files = []
        scanned_videos = []

        for video in candidate_entries:
            path = video.get("path")
            if not path or not os.path.exists(path):
                missing_files.append(path)
            else:
                norm_path = os.path.normpath(path)
                info_by_norm[norm_path] = video
                scanned_videos.append(video)

        if missing_files:
            log.warning(
                "video_orchestrator.validation.missing_files",
                count=len(missing_files),
            )

        return info_by_norm, missing_files, scanned_videos

    def _classify_candidate_videos(
        self, candidate_entries: list[dict], info_by_norm: dict
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], bool]:
        """Classify candidate videos by processing status.

        Returns:
            Tuple of (ready_with_trajectory, ready_with_zones, arena_only, without_arena, data_changed)
        """
        # Placeholder: In actual implementation, this would classify videos by:
        # - Has trajectory data
        # - Has zone data
        # - Has arena only
        # - No arena/zone data

        # For now, return simple classification
        ready_with_trajectory = []
        ready_with_zones = []
        arena_only = []
        without_arena = []
        data_changed = False

        for video in candidate_entries:
            # Simplified classification
            ready_with_zones.append(video)

        return ready_with_trajectory, ready_with_zones, arena_only, without_arena, data_changed

    def _select_eligible_videos(
        self,
        skip_dialog: bool,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> list[dict] | None:
        """Select eligible videos for processing.

        Args:
            skip_dialog: Whether to skip user dialog
            ready_with_trajectory: Videos with trajectory data
            ready_with_zones: Videos with zone data
            arena_only: Videos with arena only
            without_arena: Videos without arena

        Returns:
            List of selected videos or None to abort
        """
        # Combine all eligible categories
        eligible_videos = ready_with_trajectory + ready_with_zones + arena_only

        if not eligible_videos:
            return None

        # TODO: If not skip_dialog, show PendingVideosDialog for user selection
        # For now, return all eligible
        return eligible_videos

    def _load_zones_from_videos(self, eligible_videos: list[dict]) -> bool:
        """Load zone data from video parquet files if available.

        Args:
            eligible_videos: List of video info dicts

        Returns:
            True if any zones were loaded and project was updated
        """
        zones_updated = False
        for video_info in eligible_videos:
            if video_info.get("has_arena") or video_info.get("has_rois"):
                try:
                    zone_data = ProjectManager.load_zones_from_parquet(video_info)
                except Exception as exc:
                    log.warning(
                        "video_orchestrator.zone_load.failed",
                        video=os.path.basename(video_info.get("path", "")),
                        error=str(exc),
                    )
                    zone_data = None
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True

        return zones_updated

    # =============================================================================
    # PROCESSING CONTEXT & CALLBACKS
    # =============================================================================

    def _create_processing_callbacks(self, eligible_videos: list[dict]) -> ProcessingCallbacks:
        """Create processing callbacks for worker.

        Args:
            eligible_videos: List of videos being processed

        Returns:
            ProcessingCallbacks instance
        """
        # Placeholder: Create actual callbacks
        # This would include progress updates, completion handlers, error handlers, etc.
        return ProcessingCallbacks(
            on_progress=lambda *args: None,
            on_complete=lambda *args: None,
            on_error=lambda *args: None,
        )

    def _create_processing_context(
        self,
        eligible_videos: list[dict],
        project_path: str,
        single_video_config: dict | None,
    ) -> ProcessingContext:
        """Create processing context for worker.

        Args:
            eligible_videos: List of videos to process
            project_path: Project directory path
            single_video_config: Single video config or None for project mode

        Returns:
            ProcessingContext instance
        """
        # Placeholder: Create actual context
        # This would include all necessary config for processing
        return ProcessingContext(
            videos=eligible_videos,
            project_path=project_path,
            single_video_config=single_video_config,
        )

    # =============================================================================
    # CANCELLATION
    # =============================================================================

    def cancel_current_analysis(self) -> None:
        """Cancel currently running video analysis."""
        log.info("video_orchestrator.cancel_requested")
        self.cancel_event.set()

        if self.processing_worker:
            self.processing_worker.cancel()

    def set_analysis_view_mode_callback(self, callback) -> None:
        """Set callback for activating analysis view mode.

        Args:
            callback: Function to call to activate analysis view mode
        """
        self._activate_analysis_view_mode_callback = callback
