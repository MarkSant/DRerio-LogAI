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
from typing import TYPE_CHECKING

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

log = structlog.get_logger()


class LiveCameraService:
    """
    Service for managing live camera analysis sessions.

    Coordinates camera capture, detection processing, and preview display
    through dedicated threads, following the service layer pattern.

    Supports context manager protocol for automatic session cleanup.

    Example:
        with LiveCameraService(...) as service:
            service.start_session(...)
        # Session automatically stopped and cleaned up on exit
    """

    def __init__(
        self,
        controller: MainViewModel,
        state_manager: StateManager,
        project_manager: ProjectManager,
        recording_service: RecordingService,
        detector_service: DetectorService,
        root: Misc | None = None,
    ):
        """
        Initialize LiveCameraService.

        Args:
            controller: MainViewModel controller for accessing resources
            state_manager: StateManager for centralized state tracking
            project_manager: ProjectManager for project-specific data
            recording_service: RecordingService for recording coordination
            detector_service: DetectorService for detection operations
            root: Tkinter root for UI updates
        """
        self.controller = controller
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.recording_service = recording_service
        self.detector_service = detector_service
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
        self._saved_detector_context: str | None = None  # Task 2.0b: Store original detector context

    # Thread-safe properties for shared state
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
        """Thread-safe access to timer ID."""
        with self._lock:
            return self._timer_id

    @timer_id.setter
    def timer_id(self, value: str | None) -> None:
        """Thread-safe setter for timer ID."""
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

    def start_session(
        self,
        camera_index: int,
        duration_s: float,
        experiment_id: str,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
        output_base_dir: str | None = None,
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
        )

        # Store configuration
        self.analysis_interval_frames = analysis_interval_frames
        self.display_interval_frames = display_interval_frames
        self.is_capturing_for_video = record_video
        self.analysis_completed = False  # Reset flag for new session
        self.set_last_detections([])  # Reset cached detections for new session

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
            if not self.controller.setup_detector():
                log.error("live_camera_service.detector_setup_failed")
                return False

        # Apply zones to detector if available
        zone_data = self.project_manager.get_zone_data() if self.project_manager else None
        if zone_data and self.camera:
            # CRITICAL: Use actual camera dimensions for correct zone rescaling
            self.detector_service.configure_zones(
                zone_data=zone_data,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )

        # ✅ FIX: Set detector to diagnostic mode for single video analysis
        # This accepts ALL classes (aquarium AND zebrafish) without filtering
        # Critical for default arena which may catch aquarium detections (class_id=0)

        # 🔍 DEBUG: Log detector service status
        log.info(
            "live_camera_service.detector_diagnostic_debug",
            has_detector_service=self.detector_service is not None,
            has_detector=self.detector_service.detector is not None
            if self.detector_service
            else False,
            detector_type=type(self.detector_service.detector).__name__
            if (self.detector_service and self.detector_service.detector)
            else "None",
        )

        if self.detector_service and self.detector_service.detector:
            # Log context BEFORE setting
            old_context = getattr(self.detector_service.detector, "_context", "unknown")
            log.info(
                "live_camera_service.detector_context_before",
                old_context=old_context,
            )

            # Task 2.0b: Save original context for restoration in stop_session()
            self._saved_detector_context = old_context

            # Set diagnostic mode
            self.detector_service.detector.set_context("diagnostic")

            # Verify context AFTER setting
            new_context = getattr(self.detector_service.detector, "_context", "unknown")
            log.info(
                "live_camera_service.detector_context_set",
                context="diagnostic",
                old_context=old_context,
                new_context=new_context,
                verification_passed=(new_context == "diagnostic"),
                reason="accept_all_classes_for_single_video_analysis",
            )
        else:
            # Task 2.0b: No detector, mark as None so we don't try to restore later
            self._saved_detector_context = None
            log.warning(
                "live_camera_service.detector_not_available",
                has_detector_service=self.detector_service is not None,
                has_detector=self.detector_service.detector is not None
                if self.detector_service
                else False,
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
        # ✅ NOVA IMPLEMENTAÇÃO: Gravação leve DENTRO de LiveCameraService
        # ========================================================================
        # Substituiu chamada a RecordingService (linha 209 REMOVIDA)
        # LiveCameraService agora é autossuficiente e não polui estado global

        # Initialize lightweight recorder for standalone analysis
        if record_video and self.controller.recorder:
            # Get zone data for recorder (use empty ZoneData if none available)
            from zebtrack.core.detector import ZoneData

            recorder_zones = zone_data if zone_data else ZoneData()

            # Start recorder directly (no RecordingService intermediary)
            try:
                recorder_started = self.controller.recorder.start_recording(
                    output_folder=str(output_dir),
                    frame_width=self.camera.actual_width if self.camera else 640,
                    frame_height=self.camera.actual_height if self.camera else 480,
                    zones=recorder_zones,
                    is_video_file=False,  # We want to record video
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

        # Setup session completion timer (replaces RecordingService timer)
        self._setup_session_timer(duration_s, output_dir)

        # Update status to recording
        if self.preview_window:
            self.preview_window.update_status_text("● Gravando", color="red")

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
        if self.controller.recorder:
            try:
                self.controller.recorder.stop_recording()
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
            temp_settings = self.controller.settings.model_copy(deep=True)
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

                # Put frame in processing queue
                if not self.frame_queue.full():
                    self.frame_queue.put((frame_count, frame.copy()))

                # Put frame in video queue if recording
                if self.is_capturing_for_video and not self.video_queue.full():
                    self.video_queue.put(frame.copy())

                # Control capture rate
                default_fps = 30.0
                fps = (
                    self.controller.settings.video_processing.fps
                    if self.controller.settings
                    else default_fps
                )
                time.sleep(1 / (fps * 1.5))

            except Exception as e:
                log.error("live_camera_service.capture_error", error=str(e), exc_info=True)
                time.sleep(0.5)

        log.info("live_camera_service.capture_loop_finished", total_frames=frame_count)

    def _processing_loop(self):
        """Thread loop for processing frames with detection."""
        log.info("live_camera_service.processing_loop_started")
        processed_count = 0

        while not self.exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
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

                        # Record detections
                        if self.controller.recorder and self.controller.recorder.start_time:
                            if detections:
                                timestamp = time.time() - self.controller.recorder.start_time
                                self.controller.recorder.write_detection_data(
                                    timestamp, frame_number, detections
                                )
                                # 🔍 DEBUG: Log detection writes
                                log.debug(
                                    "live_camera_service.detection_written",
                                    frame_number=frame_number,
                                    num_detections=len(detections),
                                )
                else:
                    # Use cached detections for overlay on non-analyzed frames
                    # This makes bounding boxes persist instead of flickering
                    detections = self.get_last_detections()

                # ✅ ALWAYS draw overlay when displaying (with current or cached detections)
                detector = self.detector_service.detector
                if detector and should_display and detections:
                    detector.draw_overlay(frame, detections)
                    log.debug(
                        "live_camera_service.overlay_drawn",
                        frame_number=frame_number,
                        num_boxes=len(detections),
                        is_cached=not should_analyze,
                    )

                # ✅ CRITICAL FIX: Write video frame to MP4/AVI
                # Previously frames were queued but never written, causing no video output
                if self.is_capturing_for_video and self.controller.recorder:
                    # Additional check: only write if recorder is still recording
                    if (
                        self.controller.recorder.is_recording
                        and self.controller.recorder.video_writer
                    ):
                        try:
                            self.controller.recorder.write_video_frame(frame)
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

                    # Task 1.1: UI Update Thread Safety - Only update if both preview_window and root exist
                    if self.preview_window and self.root:
                        self.root.after(0, self.preview_window.update_frame, frame, detections)
                    # Do not update if root doesn't exist (prevents crashes in headless/test mode)

            except Exception as e:
                log.error("live_camera_service.processing_error", error=str(e), exc_info=True)

        log.info("live_camera_service.processing_loop_finished", processed=processed_count)

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

        # ✅ CRITICAL FIX: Trigger automatic analysis after recording
        # Previously only showed message, now processes data and generates reports
        log.info("live_camera_service.starting_post_analysis", output_dir=str(output_dir))

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
                self._show_completion_message(output_dir, analysis_success=False)
                return

            trajectory_file = Path(trajectory_files[0])
            log.info("live_camera_service.trajectory_found", file=str(trajectory_file))

            # Load trajectory data and generate reports
            import pandas as pd

            df = pd.read_parquet(trajectory_file)

            if df.empty:
                log.warning("live_camera_service.empty_trajectory")
                self._show_completion_message(
                    output_dir, analysis_success=False, reason="no_detections"
                )
                return

            # Generate basic metrics summary
            total_frames = df["frame"].nunique()
            total_detections = len(df)
            unique_tracks = df["track_id"].nunique() if "track_id" in df.columns else 0

            log.info(
                "live_camera_service.analysis_complete",
                total_frames=total_frames,
                total_detections=total_detections,
                unique_tracks=unique_tracks,
            )

            # Show success message with statistics
            self._show_completion_message(
                output_dir,
                analysis_success=True,
                stats={
                    "frames": total_frames,
                    "detections": total_detections,
                    "tracks": unique_tracks,
                },
            )

        except Exception as e:
            log.error(
                "live_camera_service.post_analysis_error",
                error=str(e),
                exc_info=True,
            )
            self._show_completion_message(output_dir, analysis_success=False, reason="error")

    def _show_completion_message(
        self,
        output_dir: Path,
        analysis_success: bool = True,
        stats: dict | None = None,
        reason: str | None = None,
    ):
        """Show completion message with analysis results."""
        if not self.controller.ui_event_bus:
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

        self.controller.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO,
            {"title": title, "message": message},
        )

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
