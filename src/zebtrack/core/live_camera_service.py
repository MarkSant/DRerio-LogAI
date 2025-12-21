"""
Live Camera Service - Camera Analysis Session Management.

Manages live camera analysis sessions including:
- Thread coordination for frame capture and processing
- Camera feed management
- Detection processing
- Live preview window updates
- Integration with RecordingService

Follows the service pattern established by RecordingService and DetectorService.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

import cv2
import structlog

if TYPE_CHECKING:
    from tkinter import Misc

    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.recording_service import RecordingService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.dialogs import LivePreviewWindow
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


# MELHORIA #3: Context manager for detector context restoration
class DetectorContextManager:
    """
    Context manager to ensure detector context is always restored, even on exceptions.

    Usage:
        with DetectorContextManager(detector, "tracking") as manager:
            # Do processing with new context
            pass
        # Context is automatically restored here
    """

    def __init__(self, detector_service: DetectorService | None, new_context: str):
        """
        Initialize context manager.

        Args:
            detector_service: DetectorService instance (can be None)
            new_context: New context to set temporarily
        """
        self.detector_service = detector_service
        self.new_context = new_context
        self.saved_context: str | None = None

    def __enter__(self) -> DetectorContextManager:
        """Save current context and set new context."""
        if self.detector_service and self.detector_service.detector:
            self.saved_context = getattr(self.detector_service.detector, "_context", "unknown")
            log.debug(
                "detector_context.saved",
                saved=self.saved_context,
                new=self.new_context,
            )
            self.detector_service.detector.set_context(self.new_context)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Restore original context, even if exception occurred."""
        if self.detector_service and self.detector_service.detector and self.saved_context:
            try:
                self.detector_service.detector.set_context(self.saved_context)
                log.debug("detector_context.restored", context=self.saved_context)
            except Exception as e:
                log.warning(
                    "detector_context.restore_failed",
                    saved_context=self.saved_context,
                    error=str(e),
                )


class LiveCameraService:
    """
    Service for managing live camera analysis sessions.

    Coordinates camera capture, detection processing, and preview display
    through dedicated threads, following the service layer pattern.

    Supports context manager protocol for automatic session cleanup.

    Architecture Note (ADR-004):
        This service intentionally uses a different display mechanism than
        recorded video analysis:

        - Recorded Video: Uses `CanvasManager` via `Events.UI_DISPLAY_FRAME`
        - Live Camera: Uses `LivePreviewWindow` via direct `root.after()` calls

        This divergence exists because:
        1. Live camera requires daemon threads for capture + processing
        2. Preview window lifecycle is tied to camera session, not main canvas
        3. Different threading model than ProcessingWorker's queue-based approach

        See `docs/decisions/ADR-004-live-camera-divergence.md` for details.

    Example:
        with LiveCameraService(...) as service:
            service.start_session(...)
        # Session automatically stopped and cleaned up on exit
    """

    def __init__(
        self,
        controller: MainViewModel | None,
        state_manager: StateManager,
        project_manager: ProjectManager,
        recording_service: RecordingService,
        detector_service: DetectorService,
        settings_obj: Any,  # Settings
        recorder: Any,  # Recorder
        event_bus: EventBus,  # Injected EventBus
        root: Misc | None = None,
    ):
        """
        Initialize LiveCameraService.

        Args:
            controller: MainViewModel controller (optional/legacy)
            state_manager: StateManager for centralized state tracking
            project_manager: ProjectManager for project-specific data
            recording_service: RecordingService for recording coordination
            detector_service: DetectorService for detection operations
            settings_obj: Settings object
            recorder: Recorder instance
            event_bus: EventBus for UI notifications
            root: Tkinter root for UI updates
        """
        self.controller = controller
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.recording_service = recording_service
        self.detector_service = detector_service
        self.settings = settings_obj
        self.recorder = recorder
        self.event_bus = event_bus
        self.root = root

        # Threading infrastructure
        self._lock = threading.Lock()  # Protects all shared state below
        self.frame_queue = queue.Queue(maxsize=30)
        self.video_queue = queue.Queue(maxsize=30)
        self.exit_event = threading.Event()
        self.capture_thread: threading.Thread | None = None
        self.processing_thread: threading.Thread | None = None

        # Active session state (protected by self._lock)
        self._camera: Camera | None = None
        self._preview_window: LivePreviewWindow | None = None
        self.analysis_interval_frames = 1
        self.display_interval_frames = 1
        self._is_capturing_for_video = False
        self._timer_id: str | None = None
        self._current_output_dir: Path | None = None
        self._analysis_completed = False
        self._last_detections: list = []
        self._saved_detector_context: str | None = (
            None  # Task 2.0b: Store original detector context
        )
        self._session_duration_s: float = 0.0
        self._preview_window_destroyed: bool = False  # MELHORIA #2: Flag to prevent race condition

        # MELHORIA #5: Metrics for dropped frames
        self._dropped_frames_processing: int = 0  # Frames dropped from frame_queue
        self._dropped_frames_video: int = 0  # Frames dropped from video_queue

        # Aquarium detection phase state
        self._aquarium_detection_phase: bool = False
        self._aquarium_detection_frames: int = 0
        self._aquarium_detection_max_frames: int = 300  # Standard: 300 frames (10s)
        self._detected_aquarium_bboxes: list[
            tuple[int, int, int, int]
        ] = []  # Collect multiple detections
        self._arena_defined_event = threading.Event()  # Signal when arena is ready
        self._animals_per_aquarium: int = 1  # Default to single subject

    @property
    def camera(self) -> Camera | None:
        """Thread-safe access to camera instance."""
        with self._lock:
            return self._camera

    @camera.setter
    def camera(self, value: Camera | None) -> None:
        """Thread-safe setter for camera instance."""
        with self._lock:
            self._camera = value

    @property
    def preview_window(self) -> LivePreviewWindow | None:
        """Thread-safe access to preview window."""
        with self._lock:
            return self._preview_window

    @preview_window.setter
    def preview_window(self, value: LivePreviewWindow | None) -> None:
        """Thread-safe setter for preview window."""
        with self._lock:
            self._preview_window = value

    @property
    def is_capturing_for_video(self) -> bool:
        """Thread-safe access to video capture flag."""
        with self._lock:
            return self._is_capturing_for_video

    @is_capturing_for_video.setter
    def is_capturing_for_video(self, value: bool) -> None:
        """Thread-safe setter for video capture flag."""
        with self._lock:
            self._is_capturing_for_video = value

    @property
    def timer_id(self) -> str | None:
        """
        Thread-safe access to timer ID.

        MELHORIA #6: Atomic timer ID management to prevent race conditions
        when multiple threads access timer state.
        """
        with self._lock:
            return self._timer_id

    @timer_id.setter
    def timer_id(self, value: str | None) -> None:
        """
        Thread-safe setter for timer ID.

        MELHORIA #6: Atomic timer ID management to prevent race conditions
        when multiple threads set timer state.
        """
        with self._lock:
            self._timer_id = value

    @property
    def current_output_dir(self) -> Path | None:
        """Thread-safe access to output directory."""
        with self._lock:
            return self._current_output_dir

    @current_output_dir.setter
    def current_output_dir(self, value: Path | None) -> None:
        """Thread-safe setter for output directory."""
        with self._lock:
            self._current_output_dir = value

    @property
    def analysis_completed(self) -> bool:
        """Thread-safe access to analysis completed flag."""
        with self._lock:
            return self._analysis_completed

    @analysis_completed.setter
    def analysis_completed(self, value: bool) -> None:
        """Thread-safe setter for analysis completed flag."""
        with self._lock:
            self._analysis_completed = value

    def get_last_detections(self) -> list:
        """Thread-safe getter for last detections (returns a copy)."""
        with self._lock:
            return list(self._last_detections)

    def set_last_detections(self, detections: list) -> None:
        """Thread-safe setter for last detections."""
        with self._lock:
            self._last_detections = list(detections)

    def start_session(  # noqa: C901
        self,
        camera_index: int,
        duration_s: float,
        experiment_id: str,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
        output_base_dir: str | None = None,
        animals_per_aquarium: int = 1,
    ) -> bool:
        """
        Start a live camera analysis session.

        Args:
            camera_index: Camera device index
            duration_s: Session duration in seconds
            experiment_id: Identifier for this session
            analysis_interval_frames: Analyze every N frames
            display_interval_frames: Display every N frames
            record_video: Whether to record video
            output_base_dir: Custom output directory (default: live_analysis_sessions/)
            animals_per_aquarium: Number of animals per aquarium (affects tracking mode)

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
        )

        # Store configuration
        self.analysis_interval_frames = analysis_interval_frames
        self.display_interval_frames = display_interval_frames
        self.is_capturing_for_video = record_video
        self.analysis_completed = False  # Reset flag for new session
        self.set_last_detections([])  # Reset cached detections for new session
        self._animals_per_aquarium = animals_per_aquarium
        self._experiment_id = experiment_id  # Store for later use in recorder
        self._preview_window_destroyed = False  # MELHORIA #2: Reset flag for new session
        self._dropped_frames_processing = 0  # MELHORIA #5: Reset dropped frame counters
        self._dropped_frames_video = 0

        # Create preview window FIRST (so we can show status updates)
        if not getattr(self.controller, "_disable_live_preview_window", False):
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
                reason="controller_requested_skip",
            )

        # Show initialization status
        if self.preview_window:
            self.preview_window.update_status_text("⏳ Aquecendo câmera...", color="orange")

        # Setup camera
        if not self._setup_camera(camera_index):
            # Show user-friendly error message (skip in test environments)
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

        # Create output directory
        from datetime import datetime

        # ✅ Allow custom output directory for projects
        if output_base_dir:
            output_base = Path(output_base_dir)
        else:
            output_base = Path("live_analysis_sessions")

        output_base.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{experiment_id}_{timestamp}"
        output_dir = output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # ✅ Store output_dir for post-analysis when session stops
        self.current_output_dir = output_dir

        # Show detector setup status
        if self.preview_window:
            self.preview_window.update_status_text("⏳ Carregando detector...", color="orange")

        # Setup detector if needed
        if not self.detector_service.detector:
            # Initialize detector directly using service
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

        # ✅ Check if we need aquarium detection phase
        zone_data = self.project_manager.get_zone_data() if self.project_manager else None

        if not zone_data or not zone_data.polygon:
            # No predefined arena - enter aquarium detection phase
            self._aquarium_detection_phase = True
            self._aquarium_detection_frames = 0
            self._detected_aquarium_bboxes = []
            self._arena_defined_event.clear()

            log.info(
                "live_camera_service.aquarium_detection_phase_start",
                max_frames=self._aquarium_detection_max_frames,
                reason="no_predefined_arena",
            )

            # Set detector to TRACKING mode but aquarium NOT defined yet
            # This makes it detect only aquarium (class_id=0)
            if self.detector_service and self.detector_service.detector:
                old_context = getattr(self.detector_service.detector, "_context", "unknown")
                self._saved_detector_context = old_context

                self.detector_service.detector.set_context("tracking")
                self.detector_service.detector.set_aquarium_region_defined(
                    False
                )  # Will detect class 0

                # ✅ CRITICAL: Must call set_zones() before detect() to avoid RuntimeError
                # Use empty zone for now - will be defined after aquarium detection
                if self.camera:
                    from zebtrack.core.detector import ZoneData

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
            # Predefined arena exists - skip detection phase
            self._aquarium_detection_phase = False
            self._arena_defined_event.set()

            # Apply predefined zones
            if self.camera:
                self.detector_service.configure_zones(
                    zone_data=zone_data,
                    width=self.camera.actual_width,
                    height=self.camera.actual_height,
                )

            # Set detector to tracking mode with aquarium defined
            if self.detector_service and self.detector_service.detector:
                old_context = getattr(self.detector_service.detector, "_context", "unknown")
                self._saved_detector_context = old_context

                self.detector_service.detector.set_context("tracking")
                self.detector_service.detector.set_aquarium_region_defined(True)

                # Configure tracking based on animals count
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
        # ✅ RECORDING START LOGIC - depends on detection phase
        # ========================================================================
        # Store session duration for later use
        self._session_duration_s = duration_s

        # If aquarium detection phase: DON'T start recorder yet (wait for arena)
        # If predefined arena: Start recorder immediately
        if not self._aquarium_detection_phase:
            # Arena already defined - start recording immediately
            if record_video and self.recorder:
                from zebtrack.core.detector import ZoneData

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

                except Exception as e:
                    log.error(
                        "live_camera_service.recorder_init_error",
                        error=str(e),
                        exc_info=True,
                    )
                    self.stop_session()
                    return False

            # Timer will be started by _on_session_active when first frame arrives
            log.info("live_camera_service.recorder_ready", aquarium_detection_phase=False)
        else:
            # Aquarium detection phase - recorder will start AFTER arena is defined
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

    def stop_session(self):
        """Stop the current live camera analysis session."""
        log.info("live_camera_service.stop_session")

        # ✅ NOVO: Cancelar timer se existir
        if hasattr(self, "timer_id") and self.timer_id and self.root:
            try:
                self.root.after_cancel(self.timer_id)
                log.info("live_camera_service.timer_cancelled")
            except Exception as e:
                log.warning("live_camera_service.timer_cancel_error", error=str(e))

        # ✅ NOVO: Parar recorder diretamente (não via RecordingService)
        if self.recorder:
            try:
                self.recorder.stop_recording()
                log.info("live_camera_service.recorder_stopped")
            except Exception as e:
                log.warning("live_camera_service.recorder_stop_error", error=str(e))

        # Signal threads to exit
        self.exit_event.set()

        # Wait for threads to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)

        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2.0)

        # Close preview window
        if self.preview_window:
            try:
                # MELHORIA #2: Set flag before destroying to prevent race conditions
                self._preview_window_destroyed = True
                self.preview_window.destroy()
            except Exception as e:
                log.warning("live_camera_service.preview_close_error", error=str(e))
            self.preview_window = None

        # Release camera
        if self.camera:
            self.camera.release()
            self.camera = None

        # Task 2.0b: Restore detector context to original state
        if hasattr(self, "_saved_detector_context") and self._saved_detector_context:
            if self.detector_service and self.detector_service.detector:
                try:
                    self.detector_service.detector.set_context(self._saved_detector_context)
                    log.info(
                        "live_camera_service.detector_context_restored",
                        restored_context=self._saved_detector_context,
                    )
                except Exception as e:
                    log.warning(
                        "live_camera_service.detector_context_restore_failed",
                        saved_context=self._saved_detector_context,
                        error=str(e),
                    )
            # Clear saved context
            self._saved_detector_context = None

        # Update state
        self.state_manager.update_processing_state(
            source="live_camera_service.stop",
            is_processing=False,
        )

        # Clear queues
        self._clear_queues()

        log.info("live_camera_service.session_stopped")

    def _setup_camera(self, camera_index: int) -> bool:
        """Set up camera with given index."""
        try:
            from zebtrack.io.camera import Camera

            log.info("live_camera_service.setting_up_camera", camera_index=camera_index)

            # Create temporary settings with desired camera index and force 720p resolution
            temp_settings = self.settings.model_copy(deep=True)
            log.info(
                "live_camera_service.settings_before_override",
                original_index=temp_settings.camera.index,
                requested_index=camera_index,
            )
            temp_settings.camera.index = camera_index

            # Force 1280x720 resolution for consistent performance across all cameras
            # This ensures:
            # - Consistent frame processing time across different camera hardware
            # - Reduced memory usage for live analysis sessions
            # - Better real-time performance for detection algorithms
            # - Compatibility with cameras that may struggle at higher resolutions
            # NOTE: This overrides user's desired_width/desired_height from config
            # If higher resolution is needed, modify these values or make them configurable
            temp_settings.camera.desired_width = 1280
            temp_settings.camera.desired_height = 720
            log.info(
                "live_camera_service.settings_after_override",
                new_index=temp_settings.camera.index,
                forced_resolution="1280x720",
                reason="consistent_performance",
            )

            self.camera = Camera(settings_obj=temp_settings)

            if not self.camera.is_opened():
                log.error("live_camera_service.camera_not_opened", camera_index=camera_index)
                return False

            # CRITICAL: Warm up camera by discarding first frames
            # Webcams often need time to adjust exposure/white balance
            # Notebook cameras may need MORE warmup time than external webcams
            log.info("live_camera_service.camera_warmup_start", camera_index=camera_index)

            # Adaptive warmup: more frames for low-index cameras (usually integrated cameras)
            # Index 0-1: 30 frames (~1.5s at 20fps), Index 2+: 10 frames (~0.5s)
            warmup_frames = 30 if camera_index <= 1 else 10

            successful_warmup = 0
            for warmup_count in range(warmup_frames):
                ret, frame = self.camera.get_frame()
                if ret and frame is not None:
                    successful_warmup += 1
                time.sleep(0.05)  # 50ms between warmup frames

            log.info(
                "live_camera_service.camera_warmup_complete",
                camera_index=camera_index,
                frames_requested=warmup_frames,
                frames_successful=successful_warmup,
            )

            # Verify the camera is using the correct index
            actual_camera_index = self.camera._camera_index
            log.info(
                "live_camera_service.camera_ready",
                requested_camera_index=camera_index,
                actual_camera_index=actual_camera_index,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )

            if actual_camera_index != camera_index:
                log.error(
                    "live_camera_service.camera_index_mismatch",
                    requested=camera_index,
                    actual=actual_camera_index,
                )
                return False

            return True

        except Exception as e:
            log.error(
                "live_camera_service.camera_setup_failed",
                camera_index=camera_index,
                error=str(e),
                exc_info=True,
            )
            return False

    def _create_preview_window(self, camera_index: int, duration_s: float):
        """Create the live preview window."""
        from zebtrack.ui.dialogs import LivePreviewWindow

        def on_stop_callback():
            """Handle manual stop from preview window."""
            log.info("live_camera_service.manual_stop_requested")
            # ✅ FIX: Call _on_session_complete to trigger post-analysis
            # Previously only called stop_session(), which skipped analysis
            if self.current_output_dir:
                self._on_session_complete(self.current_output_dir)
            else:
                # Fallback if output_dir not available
                self.stop_session()

        self.preview_window = LivePreviewWindow(
            parent=self.root,
            camera_index=camera_index,
            duration_s=duration_s,
            on_stop_callback=on_stop_callback,
        )

        log.info("live_camera_service.preview_window_created")

    def _start_threads(self) -> bool:
        """Start capture and processing threads."""
        try:
            # Clear exit event
            self.exit_event.clear()

            # Start capture thread
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                name="LiveCameraCaptureThread",
                daemon=True,  # Daemon thread allows Python to exit even if thread is running
            )
            self.capture_thread.start()
            log.info("live_camera_service.capture_thread_started")

            # Start processing thread
            self.processing_thread = threading.Thread(
                target=self._processing_loop,
                name="LiveCameraProcessingThread",
                daemon=True,  # Daemon thread allows Python to exit even if thread is running
            )
            self.processing_thread.start()
            log.info("live_camera_service.processing_thread_started")

            return True

        except Exception as e:
            log.error("live_camera_service.thread_start_failed", error=str(e), exc_info=True)
            return False

    def _capture_loop(self):
        """Thread loop for capturing frames from camera."""
        log.info("live_camera_service.capture_loop_started")

        # Log which camera we're actually using
        if self.camera:
            log.info(
                "live_camera_service.capture_loop_using_camera",
                camera_index=self.camera._camera_index,
            )

        frame_count = 0

        while not self.exit_event.is_set():
            if not self.camera:
                log.warning("live_camera_service.camera_not_initialized")
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.camera.get_frame()
                if not ret or frame is None:
                    log.warning("live_camera_service.frame_capture_failed", frame_count=frame_count)
                    time.sleep(0.1)
                    continue

                frame_count += 1

                # MELHORIA #1: Create single copy of frame to share between queues
                # This reduces memory usage from 5.4MB to 2.7MB per frame (50% reduction)
                frame_copy = frame.copy()

                # Put frame in processing queue
                if not self.frame_queue.full():
                    self.frame_queue.put((frame_count, frame_copy))
                else:
                    # MELHORIA #5: Track dropped frames for visibility
                    self._dropped_frames_processing += 1
                    if self._dropped_frames_processing % 10 == 1:  # Log every 10th drop
                        log.warning(
                            "live_camera_service.frame_dropped_processing",
                            frame_count=frame_count,
                            total_dropped=self._dropped_frames_processing,
                        )

                # Put same frame in video queue if recording (reuse same copy)
                if self.is_capturing_for_video:
                    if not self.video_queue.full():
                        self.video_queue.put(frame_copy)
                    else:
                        # MELHORIA #5: Track dropped frames for video recording
                        self._dropped_frames_video += 1
                        if self._dropped_frames_video % 10 == 1:  # Log every 10th drop
                            log.warning(
                                "live_camera_service.frame_dropped_video",
                                frame_count=frame_count,
                                total_dropped=self._dropped_frames_video,
                            )

                # Control capture rate
                default_fps = 30.0
                fps = self.settings.video_processing.fps if self.settings else default_fps
                time.sleep(1 / (fps * 1.5))

            except Exception as e:
                log.error("live_camera_service.capture_error", error=str(e), exc_info=True)
                time.sleep(0.5)

        # MELHORIA #5: Log final metrics including dropped frames
        drop_rate_proc = (self._dropped_frames_processing / max(frame_count, 1)) * 100
        drop_rate_vid = (self._dropped_frames_video / max(frame_count, 1)) * 100
        log.info(
            "live_camera_service.capture_loop_finished",
            total_frames=frame_count,
            dropped_frames_processing=self._dropped_frames_processing,
            dropped_frames_video=self._dropped_frames_video,
            drop_rate_processing=f"{drop_rate_proc:.1f}%",
            drop_rate_video=f"{drop_rate_vid:.1f}%",
        )

    def _processing_loop(self):  # noqa: C901
        """Thread loop for processing frames with detection."""
        log.info("live_camera_service.processing_loop_started")
        processed_count = 0
        first_frame_active = False

        while not self.exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                # Trigger session timer on first frame
                if not first_frame_active:
                    first_frame_active = True
                    if self.root:
                        self.root.after(0, self._on_session_active)

                # ✅ PHASE 1: Aquarium Detection (if needed)
                if self._aquarium_detection_phase:
                    # MELHORIA: Warmup period (skip first 30 frames ~1.5s) to allow auto-exposure
                    if frame_number < 30:
                        if self.preview_window and frame_number % 5 == 0:
                            self.preview_window.update_status_text(
                                f"⏳ Estabilizando imagem... ({frame_number}/30)",
                                color="orange"
                            )
                        continue

                    # MELHORIA: Skip frames during detection to cover more time
                    # Process only every 5th frame. With 10 frames max, this covers ~50 frames (1.6s @ 30fps)
                    # instead of just 10 frames (0.33s). This helps bypass initial camera auto-adjustments.
                    if frame_number % 5 != 0:
                        self._aquarium_detection_frames += 1 # Count skipped frames towards timeout?
                        # actually, user said "diminua para 10 frames".
                        # If we count skipped, we stop immediately.
                        # Let's count "analyzed" frames vs "elapsed" frames.
                        # The variable self._aquarium_detection_frames currently counts iterations.
                        # Let's NOT increment it here, so we analyze 10 ACTUAL frames.
                        continue

                    # Update preview status
                    if self.preview_window and frame_number % 5 == 0:
                        self.preview_window.update_status_text(
                            f"🔍 Detectando aquário... ({self._aquarium_detection_frames}/{self._aquarium_detection_max_frames})",
                            color="yellow",
                        )

                    # Run detection to find aquarium (class_id=0)
                    detector = self.detector_service.detector
                    if detector:
                        # MELHORIA: Force low confidence threshold (0.05) to match AquariumDetector robustness
                        # This ensures we see the aquarium even if the model is unsure, and rely on AREA validation.
                        detections, _ = detector.detect(frame, "live", conf_threshold=0.05)

                        # Collect aquarium bboxes (class_id=0)
                        # Dynamically get aquarium class ID (usually 0, but safest to ask detector)
                        target_class_id = detector.aquarium_class_id

                        h, w = frame.shape[:2]
                        frame_area = w * h
                        # MELHORIA: Use configurable threshold
                        min_ratio = 0.10
                        if hasattr(self.settings, "detection_zones"):
                            min_ratio = self.settings.detection_zones.min_aquarium_area_ratio

                        min_aquarium_area = frame_area * min_ratio

                        detection_found_in_frame = False
                        for det in detections:
                            if len(det) >= 7:
                                x1, y1, x2, y2, conf, track_id, class_id = det

                                # Verify class (allow target class OR huge fish fallback which detector might have swapped)
                                if class_id == target_class_id:
                                    bbox_area = (x2 - x1) * (y2 - y1)
                                    if bbox_area >= min_aquarium_area:
                                        self._detected_aquarium_bboxes.append(
                                            (int(x1), int(y1), int(x2), int(y2))
                                        )
                                        detection_found_in_frame = True
                                        # Log only periodically or on first detection to reduce spam
                                        if (
                                            len(self._detected_aquarium_bboxes) == 1
                                            or len(self._detected_aquarium_bboxes) % 5 == 0
                                        ):
                                            log.info(
                                                "live_camera_service.aquarium_detected",
                                                frame=frame_number,
                                                total_collected=len(self._detected_aquarium_bboxes),
                                                area_ratio=f"{bbox_area/frame_area:.2f}",
                                            )
                                    else:
                                        log.info(
                                            "live_camera_service.aquarium_rejected_area",
                                            frame=frame_number,
                                            area_ratio=f"{bbox_area/frame_area:.2f}",
                                            min_ratio=min_ratio,
                                            bbox=(int(x1), int(y1), int(x2), int(y2))
                                        )

                        if not detection_found_in_frame:
                             # Limit "nothing found" logs to avoid flooding info channel
                             if frame_number % 5 == 0:
                                 log.info(
                                    "live_camera_service.no_valid_aquarium_in_frame",
                                    frame=frame_number,
                                    num_raw_detections=len(detections),
                                    target_class_id=target_class_id
                                )
                                 # DEBUG: Save frame to inspect visibility
                                 try:
                                     from pathlib import Path
                                     import cv2
                                     debug_path = Path.home() / f"zebtrack_debug_frame_{frame_number}.jpg"
                                     cv2.imwrite(str(debug_path), frame)
                                     log.info("live_camera_service.debug_frame_saved", path=str(debug_path))
                                 except Exception as e:
                                     log.error("live_camera_service.debug_frame_save_failed", error=str(e))

                    self._aquarium_detection_frames += 1

                    # Check if detection phase is complete
                    # MELHORIA: User requested faster detection (10 frames max, 4 for consensus)
                    if (
                        self._aquarium_detection_frames >= 10
                        or len(self._detected_aquarium_bboxes) >= 4
                    ):
                        log.info(
                            "live_camera_service.aquarium_detection_complete",
                            frames_analyzed=self._aquarium_detection_frames,
                            detections_collected=len(self._detected_aquarium_bboxes),
                        )

                        # Define arena and switch to animal tracking
                        self._define_arena_from_detections()

                        # NOW start recording (after arena is defined)
                        self._start_recording_after_arena()

                        # Update preview status
                        if self.preview_window:
                            self.preview_window.update_status_text("● Gravando", color="red")

                    # Skip rest of processing during detection phase
                    continue

                # ✅ PHASE 2: Normal Processing (after arena is defined)
                # Determine if we should process/display this frame
                should_analyze = (frame_number % self.analysis_interval_frames) == 0
                should_display = (frame_number % self.display_interval_frames) == 0

                detections = []

                if should_analyze:
                    processed_count += 1

                    # Apply calibration if available
                    calib_data = self.project_manager.project_data.get("calibration", {})
                    h_matrix = calib_data.get("homography_matrix")
                    target_dims = calib_data.get("target_dims_px")

                    if h_matrix and target_dims:
                        import numpy as np

                        h_matrix = np.array(h_matrix)
                        frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

                    # Run detection
                    detector = self.detector_service.detector
                    if detector:
                        detections, _command = detector.detect(frame, "live")

                        # Cache detections for persistent overlay on non-analyzed frames
                        self.set_last_detections(detections)

                        # 🔍 DEBUG: Log detection result
                        log.info(
                            "live_camera_service.detection_result",
                            frame_number=frame_number,
                            num_detections=len(detections),
                            has_recorder=self.recorder is not None,
                            recorder_start_time=self.recorder.start_time if self.recorder else None,
                        )

                        # Record detections
                        if self.recorder and self.recorder.start_time:
                            if detections:
                                timestamp = time.time() - self.recorder.start_time
                                self.recorder.write_detection_data(
                                    timestamp, frame_number, detections
                                )
                                # 🔍 INFO: Log detection writes (changed from DEBUG to INFO)
                                log.info(
                                    "live_camera_service.detection_written",
                                    frame_number=frame_number,
                                    num_detections=len(detections),
                                    timestamp=timestamp,
                                )
                            else:
                                log.info(
                                    "live_camera_service.detection_skipped_empty",
                                    frame_number=frame_number,
                                )
                        else:
                            log.warning(
                                "live_camera_service.detection_skipped_no_recorder",
                                frame_number=frame_number,
                                has_recorder=self.recorder is not None,
                                recorder_start_time=self.recorder.start_time
                                if self.recorder
                                else None,
                            )
                else:
                    # Use cached detections for overlay on non-analyzed frames
                    # This makes bounding boxes persist instead of flickering
                    detections = self.get_last_detections()

                # ✅ ALWAYS draw overlay when displaying (even if no detections, so we see the arena)
                detector = self.detector_service.detector
                if detector and should_display:
                    detector.draw_overlay(frame, detections)
                    log.debug(
                        "live_camera_service.overlay_drawn",
                        frame_number=frame_number,
                        num_boxes=len(detections),
                        is_cached=not should_analyze,
                    )

                # ✅ CRITICAL FIX: Write video frame to MP4/AVI
                # Previously frames were queued but never written, causing no video output
                if self.is_capturing_for_video and self.recorder:
                    # Additional check: only write if recorder is still recording
                    if self.recorder.is_recording and self.recorder.video_writer:
                        try:
                            self.recorder.write_video_frame(frame)
                            log.debug(
                                "live_camera_service.frame_written",
                                frame_number=frame_number,
                            )
                        except Exception as e:
                            log.warning(
                                "live_camera_service.frame_write_failed",
                                frame_number=frame_number,
                                error=str(e),
                            )

                # Update preview window if exists
                if self.preview_window and should_display:
                    # Add camera index overlay for debugging
                    if self.camera:
                        camera_idx = self.camera._camera_index
                        cv2.putText(
                            frame,
                            f"CAMERA INDEX: {camera_idx}",
                            (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            2.0,
                            (0, 255, 0),  # Green color
                            4,
                            cv2.LINE_AA,
                        )

                    # Task 1.1: UI Update Thread Safety - preview_window and root exist
                    # MELHORIA #2: Check if preview window not destroyed (race condition)
                    if self.preview_window and self.root and not self._preview_window_destroyed:
                        self.root.after(0, self.preview_window.update_frame, frame, detections)
                    # Do not update if root doesn't exist (prevents crashes in headless/test mode)

                # MELHORIA #4: Explicit frame cleanup to hint garbage collector
                del frame

            except Exception as e:
                log.error("live_camera_service.processing_error", error=str(e), exc_info=True)
                # MELHORIA #4: Clean up frame even on exception
                if "frame" in locals():
                    del frame

        log.info("live_camera_service.processing_loop_finished", processed=processed_count)

    def _on_session_active(self):
        """Called when the first frame is processed to start the timer."""
        log.info("live_camera_service.first_frame_active")

        # ✅ FIX: Only start timer if NOT in aquarium detection phase
        # Timer will be started in _start_recording_after_arena() instead
        if not self._aquarium_detection_phase:
            # Start the session timer now that we have video
            if self.current_output_dir and self._session_duration_s > 0:
                self._setup_session_timer(self._session_duration_s, self.current_output_dir)

            # Update UI status
            if self.preview_window:
                self.preview_window.start_timer()
                self.preview_window.update_status_text("● Gravando", color="red")
        else:
            log.info(
                "live_camera_service.timer_delayed_for_aquarium_detection",
                reason="waiting_for_arena_definition",
            )

    def _setup_session_timer(self, duration_s: float, output_dir: Path):
        """
        Setup timer to automatically stop session after duration.

        Replaces RecordingService's timed recording logic.

        Args:
            duration_s: Session duration in seconds
            output_dir: Output directory for results
        """

        def on_timer_expired():
            """Called when duration expires."""
            log.info(
                "live_camera_service.timer_expired",
                duration_s=duration_s,
            )
            self._on_session_complete(output_dir)

        # Schedule timer (in milliseconds)
        if self.root:
            self.timer_id = self.root.after(
                int(duration_s * 1000),
                on_timer_expired,
            )
            log.info(
                "live_camera_service.timer_scheduled",
                duration_s=duration_s,
            )

    def _on_session_complete(self, output_dir: Path):
        """Handle session completion and trigger post-processing analysis.

        Task 1.4: Thread-safe check-and-set pattern to prevent race conditions.
        """
        # Task 1.4: Atomic check-and-set of _analysis_completed flag
        with self._lock:
            if self._analysis_completed:
                log.info(
                    "live_camera_service.analysis_already_completed",
                    output_dir=str(output_dir),
                )
                return
            # Mark as completed atomically to prevent duplicate calls
            self._analysis_completed = True

        # Continue processing outside lock to avoid blocking other threads
        log.info("live_camera_service.session_complete", output_dir=str(output_dir))

        # Stop threads and cleanup
        self.stop_session()

        # Task 2.0c: Move post-processing analysis to background thread
        # This prevents blocking the main UI thread during heavy I/O and DataFrame operations
        log.info("live_camera_service.starting_post_analysis", output_dir=str(output_dir))

        def _run_post_analysis():
            """Background thread worker for post-processing analysis."""
            try:
                # Find generated trajectory parquet
                # File is saved as: 3_CoordMovimento_{base_name}.parquet
                import glob

                # 🔍 DEBUG: List all files in output_dir
                all_files = list(output_dir.glob("*"))
                log.info(
                    "live_camera_service.output_files_check",
                    output_dir=str(output_dir),
                    all_files=[f.name for f in all_files],
                    num_files=len(all_files),
                )

                trajectory_files = glob.glob(str(output_dir / "3_CoordMovimento_*.parquet"))

                if not trajectory_files:
                    log.warning(
                        "live_camera_service.no_trajectory_found",
                        output_dir=str(output_dir),
                        searched_pattern="3_CoordMovimento_*.parquet",
                    )
                    # Task 2.0c: Schedule UI update in main thread
                    if self.root:
                        self.root.after(
                            0, self._show_completion_message, output_dir, False, None, None
                        )
                    return

                trajectory_file = Path(trajectory_files[0])
                log.info("live_camera_service.trajectory_found", file=str(trajectory_file))

                # Load trajectory data and generate reports
                # Task 2.0c: Heavy I/O operation now runs in background thread
                import pandas as pd

                df = pd.read_parquet(trajectory_file)

                # 🔍 INFO: Log DataFrame info
                log.info(
                    "live_camera_service.trajectory_loaded",
                    file=str(trajectory_file),
                    num_rows=len(df),
                    is_empty=df.empty,
                    columns=list(df.columns) if not df.empty else [],
                )

                if df.empty:
                    log.warning("live_camera_service.empty_trajectory")
                    # Task 2.0c: Schedule UI update in main thread
                    if self.root:
                        self.root.after(
                            0,
                            self._show_completion_message,
                            output_dir,
                            False,
                            None,
                            "no_detections",
                        )
                    return

                # Generate basic metrics summary
                # Task 2.0c: DataFrame operations now in background thread
                total_frames = df["frame"].nunique()
                total_detections = len(df)
                unique_tracks = df["track_id"].nunique() if "track_id" in df.columns else 0

                log.info(
                    "live_camera_service.analysis_complete",
                    total_frames=total_frames,
                    total_detections=total_detections,
                    unique_tracks=unique_tracks,
                )

                # Task 2.0c: Schedule success message in main thread
                if self.root:
                    stats = {
                        "frames": total_frames,
                        "detections": total_detections,
                        "tracks": unique_tracks,
                    }
                    self.root.after(0, self._show_completion_message, output_dir, True, stats, None)

            except Exception as e:
                log.error(
                    "live_camera_service.post_analysis_error",
                    error=str(e),
                    exc_info=True,
                )
                # Task 2.0c: Schedule error message in main thread
                if self.root:
                    self.root.after(
                        0, self._show_completion_message, output_dir, False, None, "error"
                    )

        # Task 2.0c: Start background thread for post-analysis
        analysis_thread = threading.Thread(
            target=_run_post_analysis,
            name="PostAnalysisThread",
            daemon=True,  # Allow Python to exit even if thread is running
        )
        analysis_thread.start()
        log.info("live_camera_service.post_analysis_thread_started")

    def _show_completion_message(
        self,
        output_dir: Path,
        analysis_success: bool = True,
        stats: dict | None = None,
        reason: str | None = None,
    ):
        """Show completion message with analysis results."""
        if not self.event_bus:
            return

        from zebtrack.ui.events import Events

        if analysis_success and stats:
            message = (
                f"✅ Análise de câmera concluída com sucesso!\n\n"
                f"📊 Estatísticas:\n"
                f"  • Frames processados: {stats['frames']}\n"
                f"  • Detecções totais: {stats['detections']}\n"
                f"  • Trilhas únicas: {stats['tracks']}\n\n"
                f"📁 Dados salvos em:\n{output_dir}\n\n"
                f"💡 Arquivos gerados:\n"
                f"  • *_trajectory.parquet (trajetória)\n"
                f"  • *_zones.parquet (zonas)\n"
                f"  • *.mp4/.avi (vídeo gravado)"
            )
            title = "Análise Concluída"
        elif reason == "no_detections":
            message = (
                f"⚠️ Gravação concluída, mas nenhuma detecção foi encontrada.\n\n"
                f"Possíveis causas:\n"
                f"  • Nenhum objeto detectável no campo de visão\n"
                f"  • Arena muito restritiva\n"
                f"  • Limiar de confiança muito alto\n\n"
                f"📁 Dados salvos em:\n{output_dir}"
            )
            title = "Análise Concluída - Sem Detecções"
        else:
            message = (
                f"⚠️ Gravação concluída, mas a análise automática falhou.\n\n"
                f"📁 Dados brutos salvos em:\n{output_dir}\n\n"
                f"Você pode analisar manualmente pela interface."
            )
            title = "Gravação Concluída"

        self.event_bus.publish_event(
            Events.UI_SHOW_INFO,
            {"title": title, "message": message},
        )

    def _start_recording_after_arena(self):
        """
        Start recorder and timer AFTER arena has been defined.

        This ensures we only record animal detections, not the aquarium detection phase.
        """
        # Get zone data for recorder
        from zebtrack.core.detector import ZoneData

        zone_data = self.project_manager.get_zone_data() if self.project_manager else ZoneData()

        # Start recorder
        if self.is_capturing_for_video and self.recorder:
            try:
                recorder_started = self.recorder.start_recording(
                    output_folder=str(self.current_output_dir),
                    frame_width=self.camera.actual_width if self.camera else 640,
                    frame_height=self.camera.actual_height if self.camera else 480,
                    zones=zone_data,
                    is_video_file=False,  # We want to record video
                    base_name=f"{self._experiment_id}",
                )

                if not recorder_started:
                    log.error("live_camera_service.recorder_start_failed_after_arena")
                    return

                log.info(
                    "live_camera_service.recorder_started_after_arena",
                    output_dir=str(self.current_output_dir),
                )

            except Exception as e:
                log.error(
                    "live_camera_service.recorder_init_error_after_arena",
                    error=str(e),
                    exc_info=True,
                )
                return

        # Start session timer NOW (after arena defined)
        if self.current_output_dir and self._session_duration_s > 0:
            self._setup_session_timer(self._session_duration_s, self.current_output_dir)
            log.info(
                "live_camera_service.timer_started_after_arena",
                duration_s=self._session_duration_s,
            )

            # Start UI timer
            if self.preview_window:
                self.preview_window.start_timer()

    def _define_arena_from_detections(self):
        """
        Define arena based on collected aquarium detections or fallback to default.

        Called after aquarium detection phase completes (30 frames or manual stop).
        """
        import math

        from zebtrack.core.detector import ZoneData

        w = self.camera.actual_width if self.camera else 1280
        h = self.camera.actual_height if self.camera else 720

        if self._detected_aquarium_bboxes:
            # Use median of detected bboxes to create arena
            import numpy as np

            bboxes_array = np.array(self._detected_aquarium_bboxes)
            x1 = int(np.median(bboxes_array[:, 0]))
            y1 = int(np.median(bboxes_array[:, 1]))
            x2 = int(np.median(bboxes_array[:, 2]))
            y2 = int(np.median(bboxes_array[:, 3]))

            # Create polygon from bbox
            arena_polygon = [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2],
            ]

            log.info(
                "live_camera_service.arena_from_aquarium_detection",
                num_detections=len(self._detected_aquarium_bboxes),
                bbox=(x1, y1, x2, y2),
            )
        else:
            # Fallback: Create default arena 2x larger than old default (User requested 2x logic)
            area_ratio = 3.0  # 2x larger than old 6.0
            side = math.sqrt((w * h) / area_ratio)
            cx, cy = w / 2, h / 2
            half = side / 2

            arena_polygon = [
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half],
            ]

            log.info(
                "live_camera_service.arena_fallback_2x",
                width=w,
                height=h,
                side=side,
                reason="no_aquarium_detected",
            )

        # Save and apply zone
        zone_data = ZoneData(polygon=arena_polygon)
        self.project_manager.save_zone_data(zone_data, video_path=None, persist=False)

        if self.camera:
            self.detector_service.configure_zones(
                zone_data=zone_data,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )

        # Switch detector to detect animals (class_id=1)
        if self.detector_service and self.detector_service.detector:
            self.detector_service.detector.set_aquarium_region_defined(True)

            # Configure tracking mode
            use_single_subject = self._animals_per_aquarium == 1
            self.detector_service.detector.set_single_subject_mode(use_single_subject)

            log.info(
                "live_camera_service.detector_switched_to_animals",
                aquarium_defined=True,
                single_subject_mode=use_single_subject,
                animals_per_aquarium=self._animals_per_aquarium,
            )

        # Signal that arena is ready
        self._arena_defined_event.set()
        self._aquarium_detection_phase = False

    def _clear_queues(self):
        """Clear all queues."""
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        while not self.video_queue.empty():
            try:
                self.video_queue.get_nowait()
            except queue.Empty:
                break

    def __enter__(self) -> LiveCameraService:
        """Enter context manager - service is ready for session start."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """
        Exit context manager - cleanup session resources.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            # FIX: Trigger post-analysis on context manager exit
            # This handles cases where session ends via exception or context exit
            if self.current_output_dir:
                self._on_session_complete(self.current_output_dir)
            else:
                self.stop_session()
        except Exception as e:
            # Context managers should always clean up gracefully
            # Log but don't raise - prevents masking original exception
            log.warning("live_camera_service.cleanup.failed", error=str(e), exc_info=True)
        return False  # Don't suppress exceptions from context body
