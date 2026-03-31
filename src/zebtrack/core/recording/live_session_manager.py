"""Live Session Manager — session lifecycle, timer, and status methods.

Extracted from LiveCameraService (Phase 2.2 decomposition).
Provides the ``LiveSessionManagerMixin`` mixed into ``LiveCameraService``.
"""

from __future__ import annotations

import datetime
import shutil
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.detection.multi_aquarium_detector import MultiAquariumDetector
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.recording.recording_service import RecordingService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.dialogs import LivePreviewWindow
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class LiveSessionManagerMixin:
    """Mixin providing session lifecycle methods for LiveCameraService.

    Methods:
        start_session, stop_session, _cleanup_existing_session_folders,
        _on_session_active, _setup_session_timer, _update_session_countdown,
        _publish_analysis_lag_status
    """

    # -- Typing stubs for attributes defined by LiveCameraService.__init__ --
    controller: MainViewModel | None
    state_manager: StateManager
    project_manager: ProjectManager
    recording_service: RecordingService
    detector_service: DetectorService
    settings: Any
    recorder: Any
    event_bus: EventBusV2
    root: Any
    _lock: threading.Lock
    frame_queue: Any
    video_queue: Any
    exit_event: threading.Event
    capture_thread: threading.Thread | None
    processing_thread: threading.Thread | None
    video_recording_thread: threading.Thread | None
    analysis_interval_frames: int
    display_interval_frames: int
    _is_capturing_for_video: bool
    _analysis_completed: bool
    _last_detections: list
    _saved_detector_context: str | None
    _session_duration_s: float
    _preview_window_destroyed: bool
    _current_base_name: str
    _actual_fps: float
    _actual_height: int
    _actual_width: int
    _analysis_params: dict
    _dropped_frames_processing: int
    _dropped_frames_video: int
    _use_external_preview: bool
    _animals_per_aquarium: int
    _aquarium_detection_phase: bool
    _aquarium_detection_frames: int
    _aquarium_detection_max_frames: int
    _detected_aquarium_bboxes: list
    _arena_defined_event: threading.Event
    _experiment_id: str
    _session_start_time: float | None
    _video_frames_written: int
    _multi_aq_detector: MultiAquariumDetector | None

    # Properties and methods from other mixins / facade
    camera: Camera | None
    preview_window: LivePreviewWindow | None
    is_capturing_for_video: bool
    timer_id: str | None
    current_output_dir: Path | None
    analysis_completed: bool
    _analysis_lag_frames: int

    # Cross-mixin method stubs — visible to type checkers only so they
    # don't shadow the real implementations resolved through the MRO.
    if TYPE_CHECKING:

        def set_last_detections(self, detections: list) -> None: ...
        def _create_preview_window(self, camera_index: int, duration_s: float) -> None: ...
        def _setup_camera(self, camera_index: int) -> bool: ...
        def _start_threads(self) -> bool: ...
        def _clear_queues(self) -> None: ...
        def _on_session_complete(self, output_dir: Path) -> None: ...

    def _cleanup_existing_session_folders(
        self,
        output_base: Path,
        experiment_id: str,
    ) -> None:
        """Cleanup existing session folders for the same experiment_id.

        v2.3.2: When re-recording a live session, remove all existing folders
        matching the experiment_id pattern to prevent folder accumulation.
        This ensures that recording again overwrites previous data.

        Args:
            output_base: Base directory where session folders are created.
            experiment_id: Experiment identifier used for folder matching.
        """
        if not output_base.exists():
            return

        # Find folders matching pattern: experiment_id_YYYYMMDD_HHMMSS
        pattern = f"{experiment_id}_*"
        matching_folders = list(output_base.glob(pattern))

        if not matching_folders:
            log.debug(
                "live_camera_service.cleanup.no_existing_folders",
                output_base=str(output_base),
                experiment_id=experiment_id,
            )
            return

        log.info(
            "live_camera_service.cleanup.found_existing_folders",
            count=len(matching_folders),
            experiment_id=experiment_id,
            folders=[f.name for f in matching_folders],
        )

        for folder in matching_folders:
            if folder.is_dir():
                try:
                    shutil.rmtree(folder)
                    log.info(
                        "live_camera_service.cleanup.folder_removed",
                        folder=str(folder),
                    )
                except OSError as e:
                    log.warning(
                        "live_camera_service.cleanup.folder_remove_failed",
                        folder=str(folder),
                        error=str(e),
                    )

    def start_session(  # noqa: C901
        self,
        camera_index: int,
        duration_s: float,
        experiment_id: str,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
        output_base_dir: Path | str | None = None,
        animals_per_aquarium: int = 1,
        analysis_config: dict | None = None,
        use_external_preview: bool = False,
    ) -> bool:
        """Start a live camera analysis session.

        Args:
            camera_index: Camera device index
            duration_s: Session duration in seconds
            experiment_id: Identifier for this session
            analysis_interval_frames: Analyze every N frames
            display_interval_frames: Display every N frames
            record_video: Whether to record video
            output_base_dir: Custom output directory (default: live_analysis_sessions/)
            animals_per_aquarium: Number of animals per aquarium (affects tracking mode)
            analysis_config: Configuration for behavioral analysis (thresholds, ROIs, etc.)
            use_external_preview: Whether to use external preview window

        Returns:
            True if session started successfully, False otherwise
        """
        log.info(
            "live_camera_service.start_session",
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval=analysis_interval_frames,
            display_interval=display_interval_frames,
            animals_per_aquarium=animals_per_aquarium,
            has_analysis_config=analysis_config is not None,
        )

        # Store configuration
        self.analysis_interval_frames = analysis_interval_frames
        self.display_interval_frames = display_interval_frames
        self.is_capturing_for_video = record_video
        self.analysis_completed = False
        self.set_last_detections([])
        self._animals_per_aquarium = animals_per_aquarium
        self._experiment_id = experiment_id
        self._preview_window_destroyed = False
        self._dropped_frames_processing = 0
        self._dropped_frames_video = 0
        self._analysis_params = analysis_config or {}
        self._use_external_preview = use_external_preview

        # Create preview window FIRST (so we can show status updates)
        if use_external_preview and not getattr(
            self.controller, "_disable_live_preview_window", False
        ):
            log.info(
                "live_camera_service.about_to_create_preview_window",
                camera_index=camera_index,
            )
            self._create_preview_window(camera_index, duration_s)
            log.info(
                "live_camera_service.preview_window_creation_complete",
                camera_index=camera_index,
            )
        else:
            log.info(
                "live_camera_service.preview_window.skip",
                camera_index=camera_index,
                reason="using_integrated_canvas"
                if not use_external_preview
                else "explicitly_disabled",
            )

        # Show initialization status
        if self.preview_window:
            self.preview_window.update_status_text("⏳ Aquecendo câmera...", color="orange")

        # Setup camera
        if not self._setup_camera(camera_index):
            import os

            if os.environ.get("PYTEST_CURRENT_TEST") is None:
                error_msg = (
                    f"Falha ao abrir câmera {camera_index}.\n\n"
                    f"Possíveis causas:\n"
                    f"• Câmera está em uso por outro programa\n"
                    f"• Hardware com defeito\n"
                    f"• Driver incompatível\n\n"
                    f"Tente:\n"
                    f"• Fechar outros programas de câmera\n"
                    f"• Reconectar o dispositivo USB\n"
                    f"• Selecionar outra câmera"
                )
                import tkinter.messagebox as messagebox

                messagebox.showerror("Erro na Câmera", error_msg)
            return False

        # Store camera properties for later use (post-analysis)
        if self.camera:
            self._actual_fps = self.camera.actual_fps
            self._actual_width = self.camera.actual_width
            self._actual_height = self.camera.actual_height

        # Create output directory
        if output_base_dir:
            output_base = Path(output_base_dir)
        else:
            output_base = Path("live_analysis_sessions")

        output_base.mkdir(exist_ok=True)

        # v2.3.2: Cleanup existing session folders for same experiment_id
        self._cleanup_existing_session_folders(output_base, experiment_id)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{experiment_id}_{timestamp}"
        self._current_base_name = folder_name
        output_dir = output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Store output_dir for post-analysis when session stops
        self.current_output_dir = output_dir

        # Show detector setup status
        if self.preview_window:
            self.preview_window.update_status_text("⏳ Carregando detector...", color="orange")

        # Setup detector if needed
        if not self.detector_service.detector:
            success, _ = self.detector_service.initialize_detector(
                animal_method=self.settings.model_selection.animal_method,
                use_openvino=self.settings.model_selection.use_openvino,
                active_weight_name=self.settings.weights.det_filename
                if self.settings.model_selection.animal_method == "det"
                else self.settings.weights.seg_filename,
            )
            if not success:
                log.error("live_camera_service.detector_setup_failed")
                return False

        # Check if we need aquarium detection phase
        zone_data = self.project_manager.get_zone_data() if self.project_manager else None

        log.info(
            "live_camera_service.zone_data_check",
            has_zone_data=zone_data is not None,
            has_polygon=zone_data.polygon if zone_data else None,
            polygon_points=len(zone_data.polygon) if zone_data and zone_data.polygon else 0,
            has_project=bool(self.project_manager.project_path) if self.project_manager else False,
        )

        if not zone_data or not zone_data.polygon:
            self._aquarium_detection_phase = True
            self._aquarium_detection_frames = 0
            self._detected_aquarium_bboxes = []
            self._arena_defined_event.clear()

            log.info(
                "live_camera_service.aquarium_detection_phase_start",
                max_frames=self._aquarium_detection_max_frames,
                reason="no_predefined_arena",
            )

            if self.detector_service and self.detector_service.detector:
                old_context = getattr(self.detector_service.detector, "_context", "unknown")
                self._saved_detector_context = old_context
                self.detector_service.detector.set_context("tracking")
                self.detector_service.detector.set_aquarium_region_defined(False)

                if self.camera:
                    from zebtrack.core.detection import ZoneData

                    empty_zone = ZoneData()
                    self.detector_service.detector.set_zones(
                        zones=empty_zone,
                        actual_width=self.camera.actual_width,
                        actual_height=self.camera.actual_height,
                    )

                log.info(
                    "live_camera_service.detector_aquarium_detection_mode",
                    context="tracking",
                    aquarium_defined=False,
                    target_class="aquarium(0)",
                )
        else:
            self._aquarium_detection_phase = False
            self._arena_defined_event.set()

            if self.camera:
                self.detector_service.configure_zones(
                    zone_data=zone_data,
                    width=self.camera.actual_width,
                    height=self.camera.actual_height,
                )

            if self.detector_service and self.detector_service.detector:
                old_context = getattr(self.detector_service.detector, "_context", "unknown")
                self._saved_detector_context = old_context
                self.detector_service.detector.set_context("tracking")
                self.detector_service.detector.set_aquarium_region_defined(True)

                use_single_subject = self._animals_per_aquarium == 1
                self.detector_service.detector.set_single_subject_mode(use_single_subject)

                log.info(
                    "live_camera_service.detector_predefined_arena",
                    context="tracking",
                    aquarium_defined=True,
                    single_subject_mode=use_single_subject,
                    animals_per_aquarium=self._animals_per_aquarium,
                )

        # Show thread startup status
        if self.preview_window:
            self.preview_window.update_status_text("⏳ Iniciando captura...", color="orange")

        # Start threads before recording service
        if not self._start_threads():
            return False

        # Update state
        self.state_manager.update_processing_state(
            source="live_camera_service.start",
            is_processing=True,
        )

        # ========================================================================
        # RECORDING START LOGIC — depends on detection phase
        # ========================================================================
        self._session_duration_s = duration_s

        if not self._aquarium_detection_phase:
            if record_video and self.recorder:
                from zebtrack.core.detection import ZoneData

                recorder_zones = zone_data if zone_data else ZoneData()

                try:
                    recorder_started = self.recorder.start_recording(
                        output_folder=str(output_dir),
                        frame_width=self.camera.actual_width if self.camera else 640,
                        frame_height=self.camera.actual_height if self.camera else 480,
                        zones=recorder_zones,
                        is_video_file=False,
                        base_name=f"{experiment_id}_{timestamp}",
                    )

                    if not recorder_started:
                        log.error("live_camera_service.recorder_start_failed")
                        self.stop_session()
                        return False

                    log.info(
                        "live_camera_service.recorder_started",
                        output_dir=str(output_dir),
                        base_name=f"{experiment_id}_{timestamp}",
                    )

                # except Exception justified: recording subsystem boundary
                except Exception as e:
                    log.error(
                        "live_camera_service.recorder_init_error",
                        error=str(e),
                        exc_info=True,
                    )
                    self.stop_session()
                    return False

            log.info("live_camera_service.recorder_ready", aquarium_detection_phase=False)
        else:
            log.info(
                "live_camera_service.recorder_delayed",
                reason="waiting_for_aquarium_detection",
                max_frames=self._aquarium_detection_max_frames,
            )

        # Update status
        if self.preview_window:
            if self._aquarium_detection_phase:
                self.preview_window.update_status_text("🔍 Procurando aquário...", color="yellow")
            else:
                self.preview_window.update_status_text("⏳ Aguardando vídeo...", color="orange")

        log.info("live_camera_service.session_started", output_dir=str(output_dir))
        return True

    def stop_session(self) -> bool:
        """Stop the current live camera analysis session."""
        log.info("live_camera_service.stop_session")

        # Cancel timer if it exists
        if hasattr(self, "timer_id") and self.timer_id and self.root:
            try:
                self.root.after_cancel(self.timer_id)
                log.info("live_camera_service.timer_cancelled")
            except tk.TclError as e:
                log.warning("live_camera_service.timer_cancel_error", error=str(e))

        # Stop recorder directly (not via RecordingService)
        if self.recorder:
            try:
                self.recorder.stop_recording()
                log.info("live_camera_service.recorder_stopped")
            # except Exception justified: graceful shutdown
            except Exception as e:
                log.warning("live_camera_service.recorder_stop_error", error=str(e))

        # Clear queues BEFORE setting exit_event
        self._clear_queues()
        log.info("live_camera_service.queues_cleared_before_exit")

        # Signal threads to exit
        self.exit_event.set()

        # Wait for threads to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5.0)

        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)

        if self.video_recording_thread and self.video_recording_thread.is_alive():
            self.video_recording_thread.join(timeout=5.0)
            log.info(
                "live_camera_service.video_recording_thread_stopped",
                frames_written=self._video_frames_written,
            )

        # Close preview window
        if self.preview_window:
            try:
                self._preview_window_destroyed = True
                self.preview_window.destroy()
            except tk.TclError as e:
                log.warning("live_camera_service.preview_close_error", error=str(e))
            self.preview_window = None

        # Release camera
        if self.camera:
            self.camera.release()
            self.camera = None

        # Restore detector context to original state
        if hasattr(self, "_saved_detector_context") and self._saved_detector_context:
            if self.detector_service and self.detector_service.detector:
                try:
                    self.detector_service.detector.set_context(self._saved_detector_context)
                    log.info(
                        "live_camera_service.detector_context_restored",
                        restored_context=self._saved_detector_context,
                    )
                except (AttributeError, ValueError) as e:
                    log.warning(
                        "live_camera_service.detector_context_restore_failed",
                        saved_context=self._saved_detector_context,
                        error=str(e),
                    )
            self._saved_detector_context = None

        # Update state
        self.state_manager.update_processing_state(
            source="live_camera_service.stop",
            is_processing=False,
        )

        # Clear queues
        self._clear_queues()

        # Restore button state
        if self.event_bus:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_BUTTON_STATE,
                    data={"button_name": "start_rec", "state": "normal"},
                )
            )
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_BUTTON_STATE,
                    data={"button_name": "stop_rec", "state": "disabled"},
                )
            )
            log.info("live_camera_service.buttons_restored_after_session_end")

        log.info("live_camera_service.session_stopped")
        return True

    def _on_session_active(self) -> None:
        """Called when the first frame is processed to start the timer."""
        log.info("live_camera_service.first_frame_active")

        # Only start timer if NOT in aquarium detection phase
        if not self._aquarium_detection_phase:
            if self.current_output_dir and self._session_duration_s > 0:
                self._setup_session_timer(self._session_duration_s, self.current_output_dir)

            if self.preview_window:
                self.preview_window.start_timer()
                self.preview_window.update_status_text("● Gravando", color="red")
        else:
            log.info(
                "live_camera_service.timer_delayed_for_aquarium_detection",
                reason="waiting_for_arena_definition",
            )

    def _setup_session_timer(self, duration_s: float, output_dir: Path) -> None:
        """Setup timer to automatically stop session after duration.

        Args:
            duration_s: Session duration in seconds
            output_dir: Output directory for results
        """
        self._session_start_time = time.time()

        def on_timer_expired() -> None:
            """Called when duration expires."""
            log.info("live_camera_service.timer_expired", duration_s=duration_s)
            self._on_session_complete(output_dir)

        if self.root:
            self.timer_id = self.root.after(int(duration_s * 1000), on_timer_expired)
            log.info("live_camera_service.timer_scheduled", duration_s=duration_s)

            if not self._use_external_preview:
                self._update_session_countdown(duration_s)

    def _update_session_countdown(self, duration_s: float) -> None:
        """Update status bar with session countdown for integrated canvas mode.

        Args:
            duration_s: Total session duration in seconds
        """
        if not self.root or self.exit_event.is_set() or self._session_start_time is None:
            return

        elapsed = time.time() - self._session_start_time
        remaining = max(0, duration_s - elapsed)

        if self.event_bus and remaining > 0:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents
            from zebtrack.ui.payloads import StatusPayload

            status_msg = (
                f"● Gravando: {elapsed:.1f}s / {duration_s:.1f}s (Restante: {remaining:.1f}s)"
            )
            self.event_bus.publish(
                Event(type=UIEvents.UI_SET_STATUS, data=StatusPayload(message=status_msg)),
            )
            self.root.after(1000, self._update_session_countdown, duration_s)

    def _publish_analysis_lag_status(self, lag_seconds: float) -> None:
        """Publish analysis lag status to UI.

        Args:
            lag_seconds: How many seconds behind real-time the analysis is
        """
        if not self.event_bus:
            return

        from zebtrack.ui.event_bus_v2 import Event, UIEvents
        from zebtrack.ui.payloads import StatusPayload

        if lag_seconds < 2.0:
            status_msg = f"⏳ Analisando... ({lag_seconds:.1f}s atrás) - Gravação OK"
        elif lag_seconds < 5.0:
            status_msg = f"⏳ Análise atrasada ({lag_seconds:.1f}s) - Gravação continua normalmente"
        else:
            status_msg = (
                f"⚠️ Análise muito atrasada ({lag_seconds:.1f}s) - Gravação OK, análise em fila"
            )

        log.debug(
            "live_camera_service.analysis_lag_status",
            lag_seconds=lag_seconds,
            lag_frames=self._analysis_lag_frames,
            queue_size=self.frame_queue.qsize(),
        )

        self.event_bus.publish(
            Event(type=UIEvents.UI_SET_STATUS, data=StatusPayload(message=status_msg)),
        )
