"""Video processing coordinator — owns the ProcessingWorker lifecycle.

Phase 4: Extracted from ProcessingCoordinator.
Phase 9: Mixins extracted for single-video and video-completion logic.

Handles the main video processing workflows:
- Project-level batch processing
- Pending-video processing with selection/classification
- Event handler registration (routes to sub-coordinators)
- Validation for processing preconditions

Single-video processing delegated to SingleVideoMixin.
Video completion handling delegated to VideoCompletionMixin.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.coordinators._single_video_mixin import SingleVideoMixin
from zebtrack.coordinators._video_completion_mixin import VideoCompletionMixin
from zebtrack.coordinators._video_selection_mixin import VideoSelectionMixin
from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
    from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
    from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
    from zebtrack.coordinators.sequential_processing_coordinator import (
        SequentialProcessingCoordinator,
    )
    from zebtrack.coordinators.ui_state_coordinator import UIStateController
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.core.video.video_classification_service import VideoClassificationService
    from zebtrack.core.video.video_metadata_service import VideoMetadataService
    from zebtrack.core.video.video_selection_service import VideoSelectionService
    from zebtrack.core.video.video_validation_service import VideoValidationService
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class VideoProcessingCoordinator(
    BaseCoordinator, VideoSelectionMixin, SingleVideoMixin, VideoCompletionMixin
):
    """Central coordinator for video processing workflows.

    Owns the ProcessingWorker and processing thread. Routes events to
    sub-coordinators (progress, multi-aquarium, sequential, reports).

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
    Phase 9: SingleVideoMixin and VideoCompletionMixin extracted.
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
        recorder_factory: RecorderFactory | None = None,
        event_bus: EventBusV2 | None = None,
        dialog_coordinator: DialogCoordinator | None = None,
        video_metadata_service: VideoMetadataService | None = None,
        # UI components
        view: Any = None,
        root: Any = None,
        detector: Any = None,
    ) -> None:
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
        self._video_metadata_service = video_metadata_service

        # Services
        self.video_selection_service = video_selection_service
        self.video_validation_service = video_validation_service
        self.video_classification_service = video_classification_service

        # UI components
        self.view = view
        self.root = root
        self.detector = detector

        # Processing state — this coordinator OWNS the worker lifecycle
        self.processing_worker: ProcessingWorker | None = None
        self.processing_thread: Any = None

        # Cross-coordinator references (set post-construction in __main__.py)
        self._progress_coordinator: ProgressTrackingCoordinator | None = None
        self._multi_aquarium_coordinator: MultiAquariumCoordinator | None = None
        self._sequential_coordinator: SequentialProcessingCoordinator | None = None
        self._report_coordinator: ReportGenerationCoordinator | None = None

        log.info("video_processing_coordinator.initialized")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_video_dimensions(self, video_path: Path | str) -> tuple[int, int] | None:
        """Return (width, height) for a video file, or *None* on failure.

        Delegates to ``VideoMetadataService`` when available; falls back to
        a direct *cv2.VideoCapture* call otherwise.
        """
        if self._video_metadata_service is not None:
            try:
                return self._video_metadata_service.get_video_dimensions(video_path)
            except (OSError, ValueError, RuntimeError):
                log.warning(
                    "video_processing_coordinator.get_dims.service_failed",
                    video_path=video_path,
                )
                return None

        # Fallback: lazy cv2 import  — pragma: no cover
        try:  # pragma: no cover
            import cv2 as _cv2  # pragma: no cover

            cap = _cv2.VideoCapture(video_path)  # pragma: no cover
            if not cap.isOpened():  # pragma: no cover
                return None  # pragma: no cover
            w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))  # pragma: no cover
            h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))  # pragma: no cover
            cap.release()  # pragma: no cover
            return (w, h)  # pragma: no cover
        except Exception:  # pragma: no cover
            return None  # pragma: no cover

    # ========================================================================
    # Event Handler Registration
    # ========================================================================

    def register_event_handlers(self) -> None:
        """Subscribe to video processing events and route to sub-coordinators."""
        if not self.event_bus:
            return

        bus = self.event_bus
        log.info("video_processing_coordinator.register_handlers.start")

        # Video processing events → self
        bus.subscribe(
            UIEvents.VIDEO_START_SINGLE_PROCESSING,
            lambda payload: self.start_single_video_processing(
                video_path=str(_payload_get(payload, "video_path", "")),
                config=_payload_get(payload, "config", {}) or {},
                zone_data=cast(Any, _payload_get(payload, "zone_data")),
            ),
        )

        def _handle_project_process_videos(payload: payloads.EventPayload) -> None:
            self.process_pending_project_videos(_payload_get(payload, "video_paths"))

        bus.subscribe(UIEvents.PROJECT_PROCESS_VIDEOS, _handle_project_process_videos)

        # Aquarium detection → multi-aquarium coordinator
        mac = self._multi_aquarium_coordinator

        def _handle_zone_auto_detect(payload: payloads.EventPayload) -> None:
            if not mac:
                return
            mac.run_aquarium_detection(
                video_path=str(_payload_get(payload, "video_path", "")),
                stabilization_frames=int(_payload_get(payload, "stabilization_frames", 10)),
            )

        bus.subscribe(UIEvents.ZONE_AUTO_DETECT, _handle_zone_auto_detect)

        # Report generation → report coordinator
        rc = self._report_coordinator
        bus.subscribe(
            UIEvents.PROJECT_GENERATE_SUMMARIES,
            lambda payload: (
                rc.generate_project_reports(_payload_get(payload, "video_paths")) if rc else None
            ),
        )

        # Generate trajectories (from Reports tab)
        def _handle_generate_trajectories(payload: payloads.EventPayload) -> None:
            selection = _payload_get(payload, "selection", ())
            if any(
                "_sub_" in str(s) or not str(s).endswith((".mp4", ".avi", ".mov", ".mkv"))
                for s in selection
            ):
                log.debug(
                    "video_processing_coordinator.generate_trajectories.skipped",
                    reason="selection_contains_tree_ids_handled_by_callback",
                )
                return
            paths = [
                s
                for s in selection
                if isinstance(s, str) and s.endswith((".mp4", ".avi", ".mov", ".mkv"))
            ]
            if paths:
                self.process_pending_project_videos(paths)

        bus.subscribe(UIEvents.PROCESSING_GENERATE_TRAJECTORIES, _handle_generate_trajectories)

        # Multi-aquarium events → multi-aquarium coordinator
        bus.subscribe(
            UIEvents.ZONE_MULTI_AUTO_DETECT,
            lambda payload: mac._handle_multi_auto_detect(payload) if mac else None,
        )
        bus.subscribe(
            UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
            lambda payload: mac._on_aquarium_assignment_completed(payload) if mac else None,
        )
        bus.subscribe(
            UIEvents.ZONE_PROCESSING_MODE_CHANGED,
            lambda data: mac._on_processing_mode_changed(data) if mac else None,
        )

        # Unified report generation
        def _handle_report_generate(payload: payloads.EventPayload) -> None:
            if not rc:
                return
            report_type = _payload_get(payload, "report_type")
            videos = _payload_get(payload, "videos", [])
            paths: list[str] = []
            for item in videos:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if isinstance(path, str) and path:
                    paths.append(path)
            replace_existing = bool(_payload_get(payload, "replace_existing", False))
            report_scope = str(_payload_get(payload, "report_scope", "all"))
            if report_type == "unified":
                rc.generate_unified_report(
                    paths, replace_existing=replace_existing, report_scope=report_scope
                )
            else:
                rc.generate_project_reports(paths)

        bus.subscribe(UIEvents.REPORT_GENERATE, _handle_report_generate)

        # Reset multi-aquarium state on project load
        bus.subscribe(
            UIEvents.PROJECT_OPENED,
            lambda data: mac.reset_multi_aquarium_state() if mac else None,
        )

        log.info("video_processing_coordinator.register_handlers.complete", count=9)

    # ========================================================================
    # Project Processing Workflow
    # ========================================================================

    def start_project_processing_workflow(self) -> None:
        """Add and process videos with robust zone validation."""
        log.info("workflow.project_processing.start")
        view = self.view
        dc = self.dialog_coordinator

        if not view:
            log.error("workflow.project_processing.no_view")
            return
        if not dc:
            log.error("workflow.project_processing.no_dialog_coordinator")
            return

        validation_result = self.validate_can_start_processing(
            check_project_loaded=True, check_zones=False, check_videos_exist=False
        )
        if not dc.handle_validation_error(validation_result):
            return
        if not dc.validate_zones_with_ui():
            return

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

        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Nenhum Vídeo Encontrado",
                    message=(
                        "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados."
                    ),
                ),
            )
            return

        videos_to_process = dc.handle_mixed_data_scenario(scanned_videos)
        if videos_to_process is None:
            return
        if not videos_to_process:
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                payloads.MessagePayload(
                    title="Processamento Concluído",
                    message="Nenhum novo vídeo para processar.",
                ),
            )
            return

        self.project_manager.add_video_batch(scanned_videos)
        self.cancel_event.clear()

        callbacks = self.create_processing_callbacks(videos_to_process)
        context = self.create_processing_context(
            videos_to_process, str(self.project_manager.project_path or "")
        )
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        if self.ui_state_controller:
            self.ui_state_controller.activate_analysis_view_mode()

        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "processing")

        self._publish_event(
            UIEvents.UI_SHOW_INFO,
            payloads.MessagePayload(
                title="Sucesso",
                message=f"{len(videos_to_process)} vídeo(s) adicionado(s) para processamento.",
            ),
        )
        log.info("workflow.project_processing.started", videos_count=len(videos_to_process))

    # ========================================================================
    # Processing Context & Callbacks
    # ========================================================================

    def create_processing_context(
        self,
        videos_to_process: list[dict],
        output_base_dir: Path | str,
        single_video_config: dict | None = None,
        zone_data: Any = None,
        process_single_video_func: Callable | None = None,
        apply_project_settings_func: Callable | None = None,
    ) -> ProcessingContext:
        """Create the processing context with all necessary configuration."""
        settings_snapshot = self._create_project_settings_snapshot()
        mac = self._multi_aquarium_coordinator

        # Sync single-subject tracker preference
        use_single_subject = (
            mac._resolve_single_subject_tracker_preference(single_video_config) if mac else None
        )
        if use_single_subject is not None:
            if use_single_subject != settings_snapshot.tracking.use_single_subject_tracker:
                log.info(
                    "video_processing_coordinator.sync_settings",
                    use_single_subject_tracker=use_single_subject,
                    reason="worker_initialization_sync",
                )
                settings_snapshot.tracking.use_single_subject_tracker = use_single_subject
                settings_snapshot.video_processing.single_animal_per_aquarium = use_single_subject

            if use_single_subject != self.settings.tracking.use_single_subject_tracker:
                self.settings.tracking.use_single_subject_tracker = use_single_subject
                self.settings.video_processing.single_animal_per_aquarium = use_single_subject

        analysis_interval, display_interval = (
            mac._determine_processing_intervals(single_video_config) if mac else (10, 10)
        )

        log.info(
            "create_processing_context",
            cancel_event_id=id(self.cancel_event),
            is_set=self.cancel_event.is_set(),
            analysis_interval_frames=analysis_interval,
            display_interval_frames=display_interval,
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
            determine_intervals_func=(mac._determine_processing_intervals if mac else None),
            retry_strategy=settings_snapshot.video_processing.batch_retry_strategy,
        )

    def create_processing_callbacks(
        self,
        videos_to_process: list[dict],
        on_completed_callback: Callable | None = None,
    ) -> ProcessingCallbacks:
        """Create thread-safe callbacks for the processing worker.

        Bridges ProcessingCallbacks signatures to ProgressTrackingCoordinator methods.
        """
        ptc = self._progress_coordinator

        def _on_started_wrapper():
            if ptc:
                # Store the batch video list so PTC can re-publish metadata
                # when the worker switches to a new video (detected via idx change).
                ptc._batch_videos = videos_to_process
                ptc._current_video_idx = 0
                # PTC._on_processing_started expects a video_path: str
                first_video = videos_to_process[0].get("path", "") if videos_to_process else ""
                ptc._on_processing_started(first_video)

        def _on_progress_wrapper(
            idx: int, total: int, exp_id: str | None, fraction: float, msg: str, stats: dict | None
        ) -> None:
            if ptc:
                if stats is None:
                    log.debug(
                        "progress_wrapper.stats_is_none",
                        fraction=fraction,
                        msg=msg,
                        exp_id=exp_id,
                    )
                progress_data = {
                    "idx": idx,
                    "total_videos": total,
                    "exp_id": exp_id,
                    "fraction": fraction,
                    "msg": msg,
                    **(stats or {}),
                }
                ptc._on_processing_progress(progress_data)

        def _on_video_completed_wrapper(
            idx: int, total: int, exp_id: str | None, success: bool
        ) -> None:
            self._on_video_completed(videos_to_process, idx, total, exp_id, success)

        def _on_completed_wrapper(
            cancelled: bool, output_dir: Path | str, summary: dict | None = None
        ):
            if ptc:
                result_data = {
                    "videos_to_process": videos_to_process,
                    "success": not cancelled,
                    "cancelled": cancelled,
                    "output_dir": output_dir,
                    "summary": summary,
                    "on_completed_callback": on_completed_callback,
                }
                ptc._on_processing_complete(result_data)

        def _on_error_wrapper(exc: Exception, msg: str) -> None:
            if ptc:
                ptc._on_processing_error({"error": str(exc), "message": msg})

        def _on_frame_processed_wrapper(frame: Any, detections: Any, frame_number: Any) -> None:
            if ptc:
                ptc._on_frame_processed(
                    {"frame": frame, "detections": detections, "frame_number": frame_number}
                )

        def _on_fatal_error_wrapper(exc: Exception, msg: str, data: dict) -> None:
            if ptc:
                ptc._on_processing_fatal_error({"error": str(exc), "message": msg, **data})

        return ProcessingCallbacks(
            on_started=_on_started_wrapper,
            on_progress=_on_progress_wrapper,
            on_frame_processed=_on_frame_processed_wrapper,
            on_video_completed=_on_video_completed_wrapper,
            on_error=_on_error_wrapper,
            on_completed=_on_completed_wrapper,
            on_fatal_error=_on_fatal_error_wrapper,
        )

    # ========================================================================
    # Video Completion — see _video_completion_mixin.py
    # ========================================================================

    # ========================================================================
    # Single Video Processing (9-step flow) — see _single_video_mixin.py
    # ========================================================================

    def cancel_processing(self) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        if self._progress_coordinator:
            self._progress_coordinator.cancel_processing()

    def set_main_arena_polygon(self, points: list) -> bool:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac.set_main_arena_polygon(points) if mac else False

    def save_manual_arena(self, polygon_list: list) -> bool:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac.save_manual_arena(polygon_list) if mac else False

    def add_roi_polygon(self, points_list: list, name: str, color: tuple[int, int, int]) -> bool:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac.add_roi_polygon(points_list, name, color) if mac else False

    def _publish_processing_mode(self, **kwargs) -> Any:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            return mac._publish_processing_mode(**kwargs)
        return None

    # ========================================================================
    # Pending Project Videos
    # ========================================================================

    def process_pending_project_videos(  # noqa: C901
        self, video_paths: list[str] | None = None
    ) -> None:
        """Process pending videos already added to the project."""
        log.info("workflow.project_processing.resume_requested", targeted=len(video_paths or []))

        validation_result = self.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,
            check_videos_exist=True,
        )
        if not validation_result.is_valid:
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Validação Falhou",
                    message=validation_result.error_message,
                ),
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        skip_dialog = bool(video_paths)

        selection_result = self.video_selection_service.select_candidates(
            all_videos=all_videos, target_paths=video_paths
        )

        if selection_result.selection_mode == "targeted":
            if not self._handle_targeted_selection_errors(selection_result, video_paths):
                return
        else:
            if not self._handle_pending_selection_errors(selection_result):
                return

        candidate_paths = self._extract_and_validate_candidate_paths(
            selection_result.candidate_entries
        )
        if candidate_paths is None:
            return

        scan_result = self.video_validation_service.scan_and_validate_paths(
            candidate_paths, self.project_manager
        )
        self._handle_missing_files_warning(scan_result)

        classification_result = self.video_classification_service.classify_videos(
            selection_result.candidate_entries, scan_result.info_by_norm
        )
        ready_with_trajectory = classification_result.ready_with_trajectory
        ready_with_zones = classification_result.ready_with_zones
        arena_only = classification_result.arena_only
        without_arena = classification_result.without_arena

        if classification_result.data_changed and self.project_manager.project_path:
            self.project_manager.save_project()

        # Recovery for multi-aquarium videos classified as 'without_arena'
        for video in list(without_arena):
            raw_path = video.get("path")
            if not raw_path:
                continue
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
                    break
            if found_data:
                without_arena.remove(video)
                arena_only.append(video)

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                payloads.MessagePayload(
                    title="Processamento",
                    message="Nenhum vídeo elegível foi encontrado com dados para análise.",
                ),
            )
            return

        eligible_videos = self.select_eligible_videos(
            skip_dialog, ready_with_trajectory, ready_with_zones, arena_only, without_arena
        )
        if eligible_videos is None:
            return

        # Validate multi-aquarium metadata
        for video_info in eligible_videos:
            vp = video_info.get("path")
            multi_data = self.project_manager.get_multi_aquarium_zone_data(vp)
            if not multi_data or not vp:
                continue
            missing_subjects = [
                f"Aquário {aq.id}" for aq in multi_data.aquariums if not aq.subject_id
            ]
            if missing_subjects:
                self._publish_event(
                    UIEvents.UI_SHOW_ERROR,
                    payloads.ErrorOccurredPayload(
                        title="Configuração Incompleta",
                        message=(
                            f"O vídeo '{os.path.basename(str(vp))}' tem aquários "
                            f"sem sujeito definido:\n\n{', '.join(missing_subjects)}\n\n"
                            "Configure os aquários antes de processar."
                        ),
                    ),
                )
                return

        self._load_zones_for_eligible_videos(eligible_videos)

        # Explode sequential multi-aquarium tasks
        final_tasks = self._explode_sequential_tasks(eligible_videos)

        self.cancel_event.clear()
        ptc = self._progress_coordinator
        if ptc:
            ptc._init_batch_context(len(final_tasks))
            if len(final_tasks) > 1 and self.view:
                ptc._set_dialog_suppression(True)

        try:
            callbacks = self.create_processing_callbacks(final_tasks)
            output_dir = (
                str(self.project_manager.project_path) if self.project_manager.project_path else ""
            )
            context = self.create_processing_context(final_tasks, output_dir)
            self.processing_worker = ProcessingWorker(context, callbacks)
            self.processing_thread = self.processing_worker.start_in_thread()
        except Exception as exc:  # except Exception justified: worker + multiprocessing + I/O
            log.exception("workflow.project_processing.worker_creation_failed", error=str(exc))
            self._publish_event(
                UIEvents.UI_SHOW_ERROR,
                payloads.ErrorOccurredPayload(
                    title="Erro ao Iniciar Processamento",
                    message=f"Falha ao criar worker de processamento: {exc}",
                ),
            )
            return

        mac = self._multi_aquarium_coordinator
        if mac:
            resolved_mode = mac._determine_processing_mode()
            mac._active_processing_mode = resolved_mode
            mac._publish_processing_mode(source="batch_pre_start_sync", force=True)

        try:
            first_video = final_tasks[0] if final_tasks else {}
            self.state_manager.update_processing_state(
                source="controller.process_pending_project_videos",
                is_processing=True,
                current_video=os.path.basename(str(first_video.get("path", ""))),
                processing_start_time=datetime.now(),
                is_live_session_active=False,
            )
            for video_info in final_tasks:
                pv = video_info.get("path")
                if pv:
                    self.project_manager.update_video_status(pv, "processing")

            if len(final_tasks) > 1:
                self._publish_event(
                    UIEvents.UI_SET_STATUS,
                    payloads.StatusPayload(
                        message=f"Processamento em lote iniciado: {len(final_tasks)} vídeo(s).",
                    ),
                )
            else:
                self._publish_event(
                    UIEvents.UI_SHOW_INFO,
                    payloads.MessagePayload(
                        title="Processamento Iniciado",
                        message=f"O processamento de {len(final_tasks)} vídeo(s) foi iniciado.",
                    ),
                )
            log.info(
                "workflow.project_processing.resume_started",
                total=len(final_tasks),
                targeted=bool(video_paths),
            )
        except Exception as e:  # except Exception justified: post-worker non-critical setup
            log.exception("workflow.project_processing.post_worker_error", error=str(e))

    def _explode_sequential_tasks(self, eligible_videos: list[dict]) -> list[dict]:
        """Explode sequential multi-aquarium tasks into individual per-aquarium tasks."""
        final_tasks: list[dict] = []
        for video_info in eligible_videos:
            zone_data_dict = video_info.get("zone_data")
            if (
                zone_data_dict
                and "aquariums" in zone_data_dict
                and zone_data_dict.get("sequential_processing")
            ):
                try:
                    from zebtrack.core.project.zone_manager import ZoneManager

                    multi_data = ZoneManager.multi_aquarium_zone_data_from_dict(zone_data_dict)
                    video_basename = os.path.basename(str(video_info.get("path", "")))
                    experiment_id = os.path.splitext(video_basename)[0]
                    aq_configs = [
                        {
                            "aquarium_id": aq.id,
                            "group": aq.group,
                            "subject_id": aq.subject_id,
                            "day": int(aq.day) if aq.day else 1,
                        }
                        for aq in multi_data.aquariums
                    ]
                    aq_dirs = self.project_manager.resolve_multi_aquarium_results_directories(
                        experiment_id=experiment_id, aquarium_configs=aq_configs
                    )
                    for aq in multi_data.aquariums:
                        aq_task = video_info.copy()
                        aq_zone_data = aq.to_zone_data()
                        aq_task["zone_data"] = ZoneManager.zone_data_to_dict(aq_zone_data)
                        aq_task["is_multi_aquarium"] = False
                        aq_results_dir = aq_dirs.get(aq.id)
                        aq_task["results_dir"] = (
                            str(aq_results_dir)
                            if aq_results_dir
                            else str(Path(video_info.get("results_dir", "")) / f"aquarium_{aq.id}")
                        )
                        aq_task["aquarium_id"] = aq.id
                        aq_task["group"] = aq.group
                        aq_task["subject"] = aq.subject_id
                        aq_task["day"] = aq.day
                        final_tasks.append(aq_task)
                except (KeyError, AttributeError, ValueError):
                    log.exception("workflow.sequential_explosion_failed")
                    final_tasks.append(video_info)
            else:
                final_tasks.append(video_info)
        return final_tasks
