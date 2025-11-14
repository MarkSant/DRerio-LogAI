"""Video processing orchestration service for ZebTrack-AI.

Extracted from MainViewModel (Task 2.2: REFACTOR-VIEWMODEL-001).
Handles video processing workflows, batch processing, and analysis coordination.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.gui import ApplicationGUI

import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.core.processing_worker import ProcessingCallbacks, ProcessingContext, ProcessingWorker
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_coordinator import UICoordinator
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
    Extracted from: MainViewModel (video processing methods, ~859 lines)
    """

    def __init__(
        self,
        root,
        state_manager: StateManager,
        ui_event_bus: EventBus,
        ui_coordinator: UICoordinator,
        settings_obj: Settings,
        project_manager: ProjectManager,
        video_processing_service: VideoProcessingService,
        analysis_service: AnalysisService,
        recorder: Recorder,
        view: ApplicationGUI | None = None,
    ):
        """Initialize VideoOrchestrator with dependency injection.

        Args:
            root: Tkinter root window
            state_manager: Centralized state manager
            ui_event_bus: Event bus for UI events
            ui_coordinator: UI coordinator for scheduling UI updates
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            video_processing_service: Video processing service
            analysis_service: Analysis service
            recorder: Recorder for Parquet output
            view: Application GUI instance (optional, can be set later via set_view())
        """
        self.root = root
        self.view = view
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
        self.ui_coordinator = ui_coordinator
        self.settings = settings_obj
        self.project_manager = project_manager
        self.video_processing_service = video_processing_service
        self.analysis_service = analysis_service
        self.recorder = recorder

        # Callbacks for MainViewModel (set later)
        self._set_main_arena_polygon_callback = None
        self._activate_analysis_view_mode_callback = None
        self._refresh_project_views_callback = None
        self._publish_processing_mode_callback = None

        # Processing state
        self.processing_thread: threading.Thread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.cancel_event = threading.Event()
        self._cancel_feedback_displayed = False

    def set_view(self, view: ApplicationGUI) -> None:
        """Set the view reference after initialization.

        Args:
            view: Application GUI instance
        """
        self.view = view

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
                    from zebtrack.utils.video import get_video_dimensions

                    dimensions = get_video_dimensions(first_video)
                    if not dimensions:
                        log.error("video_orchestrator.project_workflow.failed_to_get_dimensions")
                        return

                    width, height = dimensions
                    default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                    # Note: This calls back to MainViewModel's method
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

    def set_arena_callback(self, callback: Callable[[list], bool] | None) -> None:
        """Set callback for setting main arena polygon.

        This is a temporary solution until ArenaCoordinator is extracted.

        Args:
            callback: Function that accepts polygon list and returns success bool
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
        info_by_norm, _, _ = self._scan_and_validate_candidate_paths(candidate_entries)
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
                    "message": (
                        "Nenhum vídeo elegível foi encontrado com dados suficientes para análise."
                    ),
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

        message = (
            f"O processamento de {len(eligible_videos)} vídeo(s) foi iniciado em segundo plano."
        )
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

        Uses ProjectManager.scan_input_paths to read video metadata (dimensions, fps, frames)
        and validate parquet files existence.

        Args:
            candidate_entries: List of candidate video dicts

        Returns:
            Tuple of (info_by_norm dict or None, missing_files list, scanned_videos list)
            Returns (None, None, None) if there are no valid candidate paths.
        """
        candidate_paths = [
            video.get("path")
            for video in candidate_entries
            if isinstance(video.get("path"), str) and video.get("path")
        ]
        if not candidate_paths:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro",
                    "message": (
                        "Não foi possível localizar caminhos válidos para os vídeos selecionados."
                    ),
                },
            )
            return None, None, None

        # Use ProjectManager to scan input paths and read metadata
        scanned_videos = ProjectManager.scan_input_paths(candidate_paths)
        info_by_norm = {
            os.path.normpath(info["path"]): info
            for info in scanned_videos
            if isinstance(info.get("path"), str)
        }

        missing_files = [
            path for path in candidate_paths if os.path.normpath(path) not in info_by_norm
        ]
        if missing_files:
            sample_names = [os.path.basename(path) for path in missing_files[:5]]
            if len(missing_files) > 5:
                sample_names.append(f"... (+{len(missing_files) - 5})")
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos Não Encontrados",
                    "message": "Alguns vídeos foram ignorados porque não foram localizados:\n"
                    + "\n".join(sample_names),
                },
            )
            log.warning(
                "video_orchestrator.validation.missing_files",
                count=len(missing_files),
            )

        return info_by_norm, missing_files, scanned_videos

    def _classify_candidate_videos(
        self, candidate_entries: list[dict], info_by_norm: dict
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], bool]:
        """Classify candidate videos by processing status.

        Uses scanned video info to determine:
        - ready_with_trajectory: Videos with complete trajectory data (3_CoordMovimento_*.parquet)
        - ready_with_zones: Videos with zone/ROI data (1_ArenaROI_*.parquet, 2_Zones_*.parquet)
        - arena_only: Videos with arena defined but no zones/trajectory
        - without_arena: Videos without arena configuration

        Returns:
            Tuple of (ready_with_trajectory, ready_with_zones, arena_only,
                      without_arena, data_changed)
        """
        ready_with_trajectory: list[dict] = []
        ready_with_zones: list[dict] = []
        arena_only: list[dict] = []
        without_arena: list[dict] = []

        data_changed = False

        for video in candidate_entries:
            path = video.get("path")
            if not isinstance(path, str) or not path:
                continue

            info = info_by_norm.get(os.path.normpath(path))
            if not info:
                continue

            # Sync video dict with scanned info flags
            for key in ("has_arena", "has_rois", "has_trajectory", "has_complete_data"):
                new_value = info.get(key, False)
                if video.get(key) != new_value:
                    video[key] = new_value
                    data_changed = True

            # Classify based on what data exists
            if info.get("has_arena"):
                if info.get("has_trajectory"):
                    ready_with_trajectory.append(info)
                elif info.get("has_rois"):
                    ready_with_zones.append(info)
                else:
                    arena_only.append(info)
            else:
                without_arena.append(info)

        return (
            ready_with_trajectory,
            ready_with_zones,
            arena_only,
            without_arena,
            data_changed,
        )

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

        # Return all eligible videos for processing
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
        """Create thread-safe processing callbacks for worker.

        All callbacks schedule UI updates via root.after() to ensure thread safety.

        Args:
            eligible_videos: List of videos being processed

        Returns:
            ProcessingCallbacks instance with all necessary callbacks
        """

        def on_started():
            """Call when processing starts."""
            self.ui_coordinator.show_progress_bar(self.view)
            self.ui_coordinator.set_status(
                self.view,
                f"Iniciando processamento para {len(eligible_videos)} vídeos...",
            )
            self.project_manager.set_active_zone_video(None)
            if self._publish_processing_mode_callback:
                self._publish_processing_mode_callback(source="worker.started", force=True)

        def on_progress(fraction: float, message: str, stats: dict | None):
            """Call with progress updates."""
            if self.cancel_event.is_set():
                return

            self.ui_coordinator.set_status(self.view, message)
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, message
            )

            if stats:
                # Update processing state in StateManager
                self.state_manager.update_processing_state(
                    source="video_orchestrator.processing_progress",
                    current_frame=stats.get("current_frame", 0),
                    total_frames=stats.get("total_frames", 0),
                )

                self.ui_event_bus.publish_event(Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats})

        def on_frame_processed(frame, detections, processing_info):
            """Call when a frame is ready for display."""
            if frame is not None:
                self.ui_event_bus.publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

            if detections is not None and processing_info:
                self.ui_event_bus.publish_event(
                    Events.UI_UPDATE_DETECTION_OVERLAY,
                    {"detections": detections, "report": processing_info},
                )

        def on_video_completed(index: int, total: int, experiment_id: str, success: bool):
            """Call when a single video completes."""
            log.info(
                "video_orchestrator.video_completed",
                index=index,
                total=total,
                experiment_id=experiment_id,
                success=success,
            )

        def on_error(error: Exception, context: str):
            """Call when an error occurs."""
            log.error(
                "video_orchestrator.processing.worker_error", context=context, error=str(error)
            )
            self.root.after(
                0,
                lambda: self.view.show_error("Erro na Análise", f"{context}: {error}"),
            )

        def on_fatal_error(exc, context, recovery_info):
            """Call on fatal processing errors."""
            log.error(
                "video_orchestrator.processing.fatal_error",
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
            self.project_manager.set_active_zone_video(None)
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)

            # Update processing state in StateManager
            self.state_manager.update_processing_state(
                source="video_orchestrator.processing_completed",
                is_processing=False,
                cancel_requested=was_cancelled,
                current_video=None,
            )

            if was_cancelled:
                if self._cancel_feedback_displayed:
                    self._cancel_feedback_displayed = False
                else:
                    self.ui_coordinator.show_info(
                        self.view, "Cancelado", "A análise de vídeo foi cancelada."
                    )
            elif eligible_videos:
                msg = f"Análise concluída. Resultados salvos em:\n{output_dir}"
                self.ui_coordinator.show_info(self.view, "Sucesso", msg)
                self._cancel_feedback_displayed = False
            else:
                self._cancel_feedback_displayed = False

            self.ui_coordinator.set_status(self.view, "Pronto.")
            if self._publish_processing_mode_callback:
                self._publish_processing_mode_callback(source="worker.completed", force=True)
            if self._refresh_project_views_callback:
                self._refresh_project_views_callback()

        return ProcessingCallbacks(
            on_started=on_started,
            on_progress=on_progress,
            on_frame_processed=on_frame_processed,
            on_video_completed=on_video_completed,
            on_error=on_error,
            on_completed=on_completed,
            on_fatal_error=on_fatal_error,
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

    def set_analysis_view_mode_callback(self, callback: Callable[[], None] | None) -> None:
        """Set callback for activating analysis view mode.

        Args:
            callback: Function to call to activate analysis view mode (no parameters)
        """
        self._activate_analysis_view_mode_callback = callback

    def set_refresh_callback(self, callback: Callable[..., None] | None) -> None:
        """Set callback for refreshing project views.

        Args:
            callback: Function to call to refresh project views.
                     Accepts optional keyword arguments (reason, append_summary, etc.)
        """
        self._refresh_project_views_callback = callback

    def set_publish_processing_mode_callback(self, callback: Callable[[str], None] | None) -> None:
        """Set callback for publishing processing mode.

        Args:
            callback: Function to call to publish processing mode.
                     Accepts mode string as parameter.
        """
        self._publish_processing_mode_callback = callback
