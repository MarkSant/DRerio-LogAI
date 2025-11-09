"""
Live Camera Service - Camera Analysis Session Management

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

    def start_session(
        self,
        camera_index: int,
        duration_s: float,
        experiment_id: str,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
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
            return False

        # Create output directory
        from datetime import datetime

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
        self._create_preview_window(camera_index, duration_s)

        # Start threads before recording service
        if not self._start_threads():
            return False

        # Update state
        self.state_manager.update_processing_state(
            source="live_camera_service.start",
            is_processing=True,
        )

        # Build context and start recording through RecordingService
        context = {
            "day": 1,
            "group": "live_analysis",
            "cobaia": experiment_id,
            "folder_name": folder_name,
            "output_folder": str(output_dir),
            "camera_width": self.camera.actual_width if self.camera else 640,
            "camera_height": self.camera.actual_height if self.camera else 480,
            "arduino_enabled": False,
        }

        project_data = {
            "use_timed_recording": True,
            "recording_duration_s": duration_s,
            "use_countdown": False,
            "use_arduino": False,
        }

        # Register completion callback
        def on_complete():
            self._on_session_complete(output_dir)

        # Register UI callbacks for timed recording completion
        self.recording_service.set_ui_callbacks(
            {
                "stop_recording_callback": on_complete,
            }
        )

        # Start recording session
        self.recording_service.start_session(
            context=context,
            project_data=project_data,
            trigger_source="live_analysis",
        )

        log.info("live_camera_service.session_started", output_dir=str(output_dir))
        return True

    def stop_session(self):
        """Stop the current live camera analysis session."""
        log.info("live_camera_service.stop_session")

        # Stop recording
        if self.recording_service:
            self.recording_service.stop_session()

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
        """Setup camera with given index."""
        try:
            from zebtrack.io.camera import Camera

            # Create temporary settings with desired camera index
            temp_settings = self.controller.settings.model_copy(deep=True)
            temp_settings.camera.index = camera_index
            self.camera = Camera(settings_obj=temp_settings)

            if not self.camera.is_opened():
                log.error("live_camera_service.camera_not_opened", camera_index=camera_index)
                return False

            log.info(
                "live_camera_service.camera_ready",
                camera_index=camera_index,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )
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
        frame_count = 0

        while not self.exit_event.is_set():
            if not self.camera:
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.camera.get_frame()
                if not ret or frame is None:
                    log.warning("live_camera_service.frame_capture_failed")
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

                # Update preview window if exists (respect display interval)
                if self.preview_window and should_display:
                    try:
                        # CRITICAL: Schedule on main thread for Tkinter thread safety
                        if self.root:
                            self.root.after(0, self.preview_window.update_frame, frame, detections)
                        else:
                            # Fallback if root not available (edge case)
                            self.preview_window.update_frame(frame, detections)
                    except Exception as e:
                        log.error("live_camera_service.preview_update_error", error=str(e))

            except Exception as e:
                log.error("live_camera_service.processing_error", error=str(e), exc_info=True)

        log.info("live_camera_service.processing_loop_finished", processed=processed_count)

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
