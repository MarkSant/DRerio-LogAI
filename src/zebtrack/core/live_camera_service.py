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
        self.frame_queue = queue.Queue(maxsize=30)
        self.video_queue = queue.Queue(maxsize=30)
        self.exit_event = threading.Event()
        self.capture_thread: threading.Thread | None = None
        self.processing_thread: threading.Thread | None = None

        # Active session state
        self.camera: Camera | None = None
        self.preview_window: LivePreviewWindow | None = None
        self.analysis_interval_frames = 1
        self.display_interval_frames = 1
        self.is_capturing_for_video = False
        self.timer_id: str | None = None  # ✅ Session timer ID

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

        # Create preview window
        log.info("live_camera_service.about_to_create_preview_window", camera_index=camera_index)
        self._create_preview_window(camera_index, duration_s)
        log.info("live_camera_service.preview_window_creation_complete", camera_index=camera_index)

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
            temp_settings.camera.desired_width = 1280
            temp_settings.camera.desired_height = 720
            log.info(
                "live_camera_service.settings_after_override",
                new_index=temp_settings.camera.index,
                forced_resolution="1280x720",
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

                        # Record detections
                        if self.controller.recorder and self.controller.recorder.start_time:
                            if detections:
                                timestamp = time.time() - self.controller.recorder.start_time
                                self.controller.recorder.write_detection_data(
                                    timestamp, frame_number, detections
                                )

                        # Draw overlay
                        detector.draw_overlay(frame, detections)

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

                    if self.root:
                        self.root.after(0, self.preview_window.update_frame, frame, detections)
                    else:
                        self.preview_window.update_frame(frame, detections)

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
        """Handle session completion."""
        log.info("live_camera_service.session_complete", output_dir=str(output_dir))

        # Stop threads and cleanup
        self.stop_session()

        # Show completion message
        if self.controller.ui_event_bus:
            from zebtrack.ui.events import Events

            self.controller.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Análise Concluída",
                    "message": f"Análise de câmera concluída.\nDados salvos em:\n{output_dir}",
                },
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
            self.stop_session()
        except Exception as e:
            log.warning("live_camera_service.cleanup.failed", error=str(e))
        return False  # Don't suppress exceptions
