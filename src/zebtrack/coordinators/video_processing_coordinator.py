"""Video processing coordinator — owns the ProcessingWorker lifecycle.

Phase 4: Extracted from ProcessingCoordinator.
Handles the main video processing workflows:
- Project-level batch processing
- Single-video processing (9-step flow)
- Pending-video processing with selection/classification
- Event handler registration (routes to sub-coordinators)
- Validation for processing preconditions
- Zone loading and results registration

Estimated size: ~1100 lines (above 800 target due to central orchestration role).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cv2
import structlog

from zebtrack.coordinators._video_selection_mixin import VideoSelectionMixin
from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.ui.events import Events

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
    from zebtrack.core.video.video_selection_service import VideoSelectionService
    from zebtrack.core.video.video_validation_service import VideoValidationService
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class VideoProcessingCoordinator(BaseCoordinator, VideoSelectionMixin):
    """Central coordinator for video processing workflows.

    Owns the ProcessingWorker and processing thread. Routes events to
    sub-coordinators (progress, multi-aquarium, sequential, reports).

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
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
        event_bus: EventBus | None = None,
        dialog_coordinator: DialogCoordinator | None = None,
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

        # Aquarium detection → multi-aquarium coordinator
        mac = self._multi_aquarium_coordinator
        bus.subscribe(
            Events.ZONE_AUTO_DETECT,
            lambda data: (
                mac.run_aquarium_detection(
                    video_path=str(data.get("video_path", "")) if isinstance(data, dict) else "",
                    stabilization_frames=(
                        int(data.get("stabilization_frames", 10)) if isinstance(data, dict) else 10
                    ),
                )
                if mac
                else None
            ),
        )

        # Report generation → report coordinator
        rc = self._report_coordinator
        bus.subscribe(
            Events.PROJECT_GENERATE_SUMMARIES,
            lambda data: (
                rc.generate_project_reports(
                    data.get("video_paths") if isinstance(data, dict) else None
                )
                if rc
                else None
            ),
        )

        # Generate trajectories (from Reports tab)
        def _handle_generate_trajectories(data: dict | None) -> None:
            if not isinstance(data, dict) or "selection" not in data:
                return
            selection = data.get("selection", ())
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

        bus.subscribe(Events.PROCESSING_GENERATE_TRAJECTORIES, _handle_generate_trajectories)

        # Multi-aquarium events → multi-aquarium coordinator
        bus.subscribe(
            Events.ZONE_MULTI_AUTO_DETECT,
            lambda data: mac._handle_multi_auto_detect(data) if mac else None,
        )
        bus.subscribe(
            Events.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
            lambda data: mac._on_aquarium_assignment_completed(data) if mac else None,
        )
        bus.subscribe(
            Events.ZONE_PROCESSING_MODE_CHANGED,
            lambda data: mac._on_processing_mode_changed(data) if mac else None,
        )

        # Unified report generation
        def _handle_report_generate(data):
            if not isinstance(data, dict) or not rc:
                return
            report_type = data.get("report_type")
            videos = data.get("videos", [])
            paths = [v.get("path") for v in videos if v.get("path")]
            replace_existing = bool(data.get("replace_existing", False))
            report_scope = str(data.get("report_scope", "all"))
            if report_type == "unified":
                rc.generate_unified_report(
                    paths, replace_existing=replace_existing, report_scope=report_scope
                )
            else:
                rc.generate_project_reports(paths)

        bus.subscribe(Events.REPORT_GENERATE, _handle_report_generate)

        # Reset multi-aquarium state on project load
        bus.subscribe(
            "PROJECT_LOADED",
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
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Vídeo Encontrado",
                    "message": (
                        "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados."
                    ),
                },
            )
            return

        videos_to_process = dc.handle_mixed_data_scenario(scanned_videos)
        if videos_to_process is None:
            return
        if not videos_to_process:
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento Concluído",
                    "message": "Nenhum novo vídeo para processar.",
                },
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
            self.project_manager.update_video_status(video["path"], "complete")

        self._publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Sucesso",
                "message": f"{len(videos_to_process)} vídeo(s) adicionado(s) para processamento.",
            },
        )
        log.info("workflow.project_processing.started", videos_count=len(videos_to_process))

    # ========================================================================
    # Processing Context & Callbacks
    # ========================================================================

    def create_processing_context(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
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
                # PTC._on_processing_started expects a video_path: str
                first_video = (
                    videos_to_process[0].get("video_path", "") if videos_to_process else ""
                )
                ptc._on_processing_started(first_video)

        def _on_progress_wrapper(
            idx: int, total: int, exp_id: str | None, fraction: float, msg: str, stats: dict | None
        ) -> None:
            if ptc:
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

        def _on_completed_wrapper(cancelled: bool, output_dir: str, summary: dict | None = None):
            if ptc:
                result_data = {
                    "videos_to_process": videos_to_process,
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
    # Video Completion
    # ========================================================================

    def _on_video_completed(self, videos_to_process, index, total, experiment_id, success) -> None:
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

        if 0 <= index < len(videos_to_process):
            video_info = videos_to_process[index]
            video_path = video_info.get("path")
            video_results_dir = video_info.get("results_dir")
            v_exp_id = video_info.get("experiment_id")
            if not v_exp_id and video_path:
                v_exp_id = os.path.splitext(os.path.basename(str(video_path)))[0]
            if not v_exp_id:
                v_exp_id = "Unknown"
        else:
            log.warning("controller.video_completed.index_out_of_bounds", index=index)
            return

        results_dir = video_results_dir or os.path.join(
            os.path.dirname(str(video_path)) if video_path else ".",
            f"{v_exp_id}_results",
        )

        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{v_exp_id}.parquet")
        if not os.path.exists(trajectory_path):
            trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_exists = os.path.exists(trajectory_path)

        alt_multi_outputs: dict[int, dict] = {}

        # Exploded sequential task detection
        aq_id_override = video_info.get("aquarium_id")
        if aq_id_override is not None and trajectory_exists:
            log.info("controller.video_completed.exploded_task_detected", aq_id=aq_id_override)
            alt_multi_outputs[aq_id_override] = {
                "results_dir": results_dir,
                "parquet_files": {"trajectory": trajectory_path},
                "group": video_info.get("group") or (video_info.get("metadata", {}).get("group")),
                "subject_id": (
                    video_info.get("subject") or (video_info.get("metadata", {}).get("subject"))
                ),
                "day": video_info.get("day", 1),
            }
            trajectory_exists = False

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
                        aq_subdir,
                        f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet",
                    ),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{v_exp_id}.parquet"),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
                ]
                for alt_p in alt_paths:
                    if os.path.exists(alt_p):
                        alt_multi_outputs[aq_id] = {
                            "results_dir": aq_subdir,
                            "parquet_files": {"trajectory": alt_p},
                            "group": (
                                video_info.get("group")
                                or (video_info.get("metadata", {}).get("group"))
                            ),
                            "subject_id": (
                                video_info.get("subject")
                                or (video_info.get("metadata", {}).get("subject"))
                            ),
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
    ) -> None:
        """Register outputs after video completion."""
        outputs_by_aquarium = alt_multi_outputs.copy() if alt_multi_outputs else {}

        if (
            video_results_dir
            and video_results_dir != results_dir
            and os.path.exists(video_results_dir)
        ):
            self._scan_multi_aquarium_outputs(video_results_dir, experiment_id, outputs_by_aquarium)

        if trajectory_exists and not outputs_by_aquarium:
            self.project_manager.register_processing_outputs(
                video_path=video_path, results_dir=results_dir, trajectory_path=trajectory_path
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
            # Delegate sequential advancement
            seq = self._sequential_coordinator
            if seq:
                seq._handle_sequential_multi_aquarium(video_path)
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})
            self._generate_completion_reports(video_path, experiment_id, True)
        elif trajectory_exists:
            self._generate_completion_reports(video_path, experiment_id, False)

    def _scan_multi_aquarium_outputs(self, results_dir, experiment_id, outputs_by_aquarium):
        """Scan directory for multi-aquarium outputs."""
        if not results_dir or not os.path.exists(results_dir):
            return
        for item in os.listdir(results_dir):
            item_path = os.path.join(results_dir, item)
            if not os.path.isdir(item_path):
                continue
            match = re.match(r"^aquarium_(\d+)$", item)
            if match:
                aq_id = int(match.group(1))
                traj_candidates = [
                    os.path.join(
                        item_path,
                        f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id}.parquet",
                    ),
                    os.path.join(item_path, f"3_CoordMovimento_{experiment_id}.parquet"),
                ]
                traj_file = next((p for p in traj_candidates if os.path.exists(p)), None)
                if traj_file:
                    outputs_by_aquarium[aq_id] = {
                        "results_dir": item_path,
                        "parquet_files": {"trajectory": traj_file},
                        "day": 1,
                    }

    def _generate_completion_reports(self, video_path, experiment_id, is_multi):
        """Generate reports after video completion."""
        rc = self._report_coordinator
        if not rc:
            return
        try:
            rc.generate_project_reports([video_path])
        except Exception as e:
            log.error(
                f"controller.video_completed.report_failed_{'multi' if is_multi else 'single'}",
                video=experiment_id,
                error=str(e),
            )

    # ========================================================================
    # Single Video Processing (9-step flow)
    # ========================================================================

    def start_single_video_processing(
        self,
        video_path: Path | str,
        config: dict,
        zone_data: ZoneData | MultiAquariumZoneData,
    ) -> None:
        """Start the actual processing for a single video after zone setup."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=str(video_path))

        # 1. Sequential mode check
        is_multi_aq = hasattr(zone_data, "aquariums")
        if is_multi_aq:
            fresh_zone_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if fresh_zone_data:
                zone_data = fresh_zone_data
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

        # 2. Calibration
        calib_data = self._extract_calibration_from_config(config)
        n_aq = calib_data["n"]

        if use_seq:
            seq = self._sequential_coordinator
            if seq:
                seq._handle_sequential_single_video_start(str(video_path), zone_data, config)
            return

        # 3. Validate
        val = self.validate_can_start_processing(
            check_project_loaded=False, check_zones=False, check_videos_exist=False
        )
        if not val.is_valid:
            self._show_validation_error(val)
            return

        self.project_manager.set_active_zone_video(video_path)

        # 4. Multi-aq UI sync
        zone_data = self._sync_multi_aquarium_setup(video_path, n_aq, zone_data)

        # 5. Persist calibration
        self._persist_single_video_calibration(config, calib_data)

        # 6. Register video
        self._ensure_single_video_registered(video_path, config, zone_data, calib_data)

        # 7. Save zones
        self._ensure_single_video_zones_saved(video_path, zone_data)

        # 8. Setup detector
        if not self._setup_detector_for_single_video(video_path, zone_data):
            return

        mac = self._multi_aquarium_coordinator
        single_video_config = config if isinstance(config, dict) else None
        resolved_tracker_pref = (
            mac._resolve_single_subject_tracker_preference(single_video_config) if mac else None
        )
        if (
            resolved_tracker_pref is not None
            and resolved_tracker_pref != self.settings.tracking.use_single_subject_tracker
        ):
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            self.settings.video_processing.single_animal_per_aquarium = resolved_tracker_pref

        if mac:
            mac._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
            effective_mode = (
                ProcessingMode.SINGLE_SUBJECT
                if self.settings.tracking.use_single_subject_tracker
                else ProcessingMode.MULTI_TRACK
            )
            mac._active_processing_mode = effective_mode
            mac._publish_processing_mode(source="single_video.preflight", force=True)

        # 9. Execute
        self._execute_single_video_analysis(video_path)

    def _extract_calibration_from_config(self, config: dict) -> dict:
        """Extract calibration params from config."""
        n_aq, w_cm, h_cm = 1, None, None
        if isinstance(config, dict):
            try:
                n_aq = int(config.get("num_aquariums", 1))
                self.settings.analysis_config.num_aquariums = n_aq
            except (TypeError, ValueError):
                pass
            try:
                raw_w = config.get("aquarium_width_cm")
                if raw_w is not None and str(raw_w).strip():
                    w_cm = float(raw_w)
            except (TypeError, ValueError):
                pass
            try:
                raw_h = config.get("aquarium_height_cm")
                if raw_h is not None and str(raw_h).strip():
                    h_cm = float(raw_h)
            except (TypeError, ValueError):
                pass
        return {"w": w_cm, "h": h_cm, "n": n_aq}

    def _extract_metadata_from_config(self, config: dict) -> dict:
        """Extract metadata from single video config."""
        metadata: dict[str, Any] = {}
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
                            pass
        metadata.setdefault("group", "single_video")
        metadata.setdefault("group_display_name", "Vídeo Único")
        metadata.setdefault("day", "1")
        metadata.setdefault("subject", "1")
        return metadata

    def _save_multi_aquarium_config_to_calibration(self, calibration_dict: dict) -> None:
        """Convert custom_regex_patterns from wizard to MultiAquariumData format."""
        wizard_metadata = (
            self.project_manager.project_data.get("_wizard_metadata", {})
            if self.project_manager.project_data
            else {}
        )
        if not wizard_metadata:
            return
        custom_patterns = wizard_metadata.get("custom_regex_patterns")
        if not custom_patterns or not isinstance(custom_patterns, dict):
            return
        from zebtrack.ui.wizard.models import MultiAquariumData

        try:
            combined_pattern = MultiAquariumData.build_combined_regex_pattern(
                group_pattern=custom_patterns.get("group_pattern"),
                day_pattern=custom_patterns.get("day_pattern"),
                subject_pattern=custom_patterns.get("subject_pattern"),
            )
            if combined_pattern:
                calibration_dict["multi_aquarium"] = {
                    "enabled": False,
                    "regex_pattern": combined_pattern,
                    "regex_group_field": "group",
                    "regex_subject_field": "subject",
                    "regex_day_field": "day",
                    "aquarium_configs": [],
                }
        except (ValueError, KeyError, TypeError) as e:
            log.error("calibration.multi_aquarium.conversion_failed", error=str(e))

    def _sync_multi_aquarium_setup(self, video_path, n_aq, zone_data) -> Any:
        """Sync multi-aquarium setup with UI and model."""
        if n_aq > 1:
            from zebtrack.core.detection import AquariumData

            curr = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if not curr:
                aqs = [AquariumData(id=i) for i in range(n_aq)]
                new_m = MultiAquariumZoneData(aquariums=aqs)
                persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path,
                    new_m,
                    persist=persist,
                )
                zone_data = new_m
            if self.view and hasattr(self.view, "zone_controls"):
                self.view.zone_controls.update_aquarium_count(n_aq)
                self.view.zone_controls.set_active_aquarium(0)
        elif self.view and hasattr(self.view, "zone_controls"):
            self.view.zone_controls.update_aquarium_count(1)
        return zone_data

    def _persist_single_video_calibration(self, config, calib) -> None:
        """Persist calibration and settings for single video."""
        w_cm, h_cm = calib["w"], calib["h"]
        if not (w_cm and h_cm):
            return
        c = self.project_manager.project_data.get("calibration") or {}
        c.setdefault("num_aquariums", c.get("num_aquariums", 1))
        c.setdefault("animals_per_aquarium", c.get("animals_per_aquarium", 1))
        c.update({"aquarium_width_cm": w_cm, "aquarium_height_cm": h_cm})
        self._save_multi_aquarium_config_to_calibration(c)
        self.project_manager.project_data["calibration"] = c

        mac = self._multi_aquarium_coordinator
        a_int, d_int = mac._determine_processing_intervals(config) if mac else (10, 10)
        self.project_manager.project_data["analysis_interval_frames"] = a_int
        self.project_manager.project_data["display_interval_frames"] = d_int

        if "behavioral_analysis" in config:
            self.project_manager.project_data["behavioral_config"] = config["behavioral_analysis"]

        if self.project_manager.project_path:
            self.project_manager.save_project()
        log.info("workflow.single_video.cal_saved", w=w_cm, h=h_cm)

    # ========================================================================
    # Proxy Methods (delegate to sub-coordinators for caller compatibility)
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

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Proxy → ReportGenerationCoordinator."""
        rc = self._report_coordinator
        if rc:
            rc.generate_project_reports(video_paths)

    def generate_unified_report(self, video_paths: list[str], **kwargs) -> None:
        """Proxy → ReportGenerationCoordinator."""
        rc = self._report_coordinator
        if rc:
            rc.generate_unified_report(video_paths, **kwargs)

    def generate_parquet_summaries(self, video_entries: list[dict] | None = None) -> None:
        """Proxy → ReportGenerationCoordinator."""
        rc = self._report_coordinator
        if rc:
            rc.generate_parquet_summaries(video_entries or [])

    def run_aquarium_detection(self, *args, **kwargs) -> None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            mac.run_aquarium_detection(*args, **kwargs)

    def reset_multi_aquarium_state(self) -> None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            mac.reset_multi_aquarium_state()

    def _determine_processing_mode(self) -> Any:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac._determine_processing_mode() if mac else ProcessingMode.MULTI_TRACK

    def _determine_processing_intervals(self, config=None) -> tuple:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac._determine_processing_intervals(config) if mac else (10, 10)

    def _temporary_single_animal_mode(self, config=None):
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            return mac._temporary_single_animal_mode(config)
        from contextlib import nullcontext

        return nullcontext()

    def _resolve_single_subject_tracker_preference(self, config=None) -> bool | None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        return mac._resolve_single_subject_tracker_preference(config) if mac else None

    def _find_project_roi_names(self, video_paths=None) -> list[str] | None:
        """Proxy → ReportGenerationCoordinator."""
        rc = self._report_coordinator
        return rc._find_project_roi_names(video_paths or []) if rc else None

    def _on_processing_started(self, video_path: str) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            ptc._on_processing_started(video_path)

    def make_progress_callback(self, *args, **kwargs):
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            return ptc.make_progress_callback(*args, **kwargs)
        return lambda *a, **k: None

    def _init_batch_context(self, total_videos: int) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            ptc._init_batch_context(total_videos)

    def _is_batch_processing(self) -> bool:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        return ptc._is_batch_processing() if ptc else False

    def _update_batch_context(self, *args, **kwargs) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            ptc._update_batch_context(*args, **kwargs)

    def _finalize_batch_context(self) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            ptc._finalize_batch_context()

    def _set_dialog_suppression(self, value: bool) -> None:
        """Proxy → ProgressTrackingCoordinator."""
        ptc = self._progress_coordinator
        if ptc:
            ptc._set_dialog_suppression(value)

    def _apply_processing_mode_to_video(self, *args, **kwargs) -> None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            mac._apply_processing_mode_to_video(*args, **kwargs)

    def _apply_processing_mode_to_all_videos(self, *args, **kwargs) -> None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            mac._apply_processing_mode_to_all_videos(*args, **kwargs)

    def _on_processing_mode_changed(self, data) -> None:
        """Proxy → MultiAquariumCoordinator."""
        mac = self._multi_aquarium_coordinator
        if mac:
            mac._on_processing_mode_changed(data)

    def _ensure_single_video_registered(self, video_path, config, zone_data, calib) -> None:
        """Ensure single video is registered in project."""
        v_entry = self.project_manager.find_video_entry(path=video_path)
        if v_entry:
            return
        w_cm, h_cm = calib["w"], calib["h"]
        meta = self._extract_metadata_from_config(config)
        if w_cm:
            meta.setdefault("aquarium_width_cm", w_cm)
        if h_cm:
            meta.setdefault("aquarium_height_cm", h_cm)

        has_a, has_r = False, False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                has_a = bool(zone_data.aquariums)
                has_r = any(bool(aq.roi_polygons) for aq in zone_data.aquariums)
            else:
                has_a = bool(zone_data.polygon)
                has_r = bool(zone_data.roi_polygons)

        v_dict: dict[str, Any] = {
            "path": Path(video_path).as_posix(),
            "experiment_id": os.path.splitext(os.path.basename(str(video_path)))[0],
            "status": "processing",
            "has_arena": has_a,
            "has_rois": has_r,
        }
        if meta:
            v_dict["metadata"] = meta
        self.project_manager.add_video_batch([v_dict], save_project=False)
        self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {"reason": "reg", "imm": True})

    def _ensure_single_video_zones_saved(self, video_path, zone_data) -> None:
        """Ensure zones are saved for single video."""
        should_s = False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                should_s = bool(zone_data.aquariums)
            else:
                should_s = bool(zone_data.polygon or zone_data.roi_polygons)
        if should_s:
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
        return True

    def _execute_single_video_analysis(self, video_path) -> None:
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
        self.process_videos(scanned, out_dir)

    # ========================================================================
    # Legacy Process Videos
    # ========================================================================

    def process_videos(self, videos_to_process: list[dict], output_base_dir: Path | str) -> None:
        """Execute processing for a list of videos (legacy support)."""
        output_dir_str = str(output_base_dir)

        # Reuse the unified callback factory
        callbacks = self.create_processing_callbacks(videos_to_process)
        context = self.create_processing_context(videos_to_process, output_dir_str)
        if self.cancel_event:
            self.cancel_event.clear()
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

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
                Events.UI_SHOW_WARNING,
                {"title": "Validação Falhou", "message": validation_result.error_message},
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
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo elegível foi encontrado com dados para análise.",
                },
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
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Incompleta",
                        "message": (
                            f"O vídeo '{os.path.basename(str(vp))}' tem aquários "
                            f"sem sujeito definido:\n\n{', '.join(missing_subjects)}\n\n"
                            "Configure os aquários antes de processar."
                        ),
                    },
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
        except Exception as exc:
            log.exception("workflow.project_processing.worker_creation_failed", error=str(exc))
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro ao Iniciar Processamento",
                    "message": f"Falha ao criar worker de processamento: {exc}",
                },
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
                    self.project_manager.update_video_status(pv, "complete")

            if len(final_tasks) > 1:
                self._publish_event(
                    Events.UI_SET_STATUS,
                    {"message": f"Processamento em lote iniciado: {len(final_tasks)} vídeo(s)."},
                )
            else:
                self._publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Iniciado",
                        "message": f"O processamento de {len(final_tasks)} vídeo(s) foi iniciado.",
                    },
                )
            log.info(
                "workflow.project_processing.resume_started",
                total=len(final_tasks),
                targeted=bool(video_paths),
            )
        except Exception as e:
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
                except Exception:
                    log.exception("workflow.sequential_explosion_failed")
                    final_tasks.append(video_info)
            else:
                final_tasks.append(video_info)
        return final_tasks
