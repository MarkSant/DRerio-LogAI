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

import datetime
import glob
import math
import queue
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import pandas as pd
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
        # ✅ ARCHITECTURE v2.3.1: Separate priorities for video vs analysis
        # Video queue: LARGE (600 = 20s @ 30fps) - video recording is CRITICAL, never drop
        # Frame queue: Medium (180 = 6s @ 30fps) - analysis can lag behind real-time
        self.frame_queue = queue.Queue(maxsize=180)
        self.video_queue = queue.Queue(maxsize=600)  # Priority: recording > analysis
        self.exit_event = threading.Event()
        self.capture_thread: threading.Thread | None = None
        self.processing_thread: threading.Thread | None = None
        self.video_recording_thread: threading.Thread | None = None  # ✅ NEW: Dedicated thread

        # ✅ NEW: Analysis lag tracking for UI feedback
        self._analysis_lag_frames: int = 0  # How many frames behind real-time
        self._last_analyzed_frame: int = 0  # Last frame number analyzed
        self._last_captured_frame: int = 0  # Last frame number captured
        self._analysis_lag_warning_threshold: int = 30  # Show warning if >1s behind
        self._video_frames_written: int = 0  # Counter for video frames written

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
        self._current_base_name: str = ""  # Store base name used for files
        self._actual_fps: float = 30.0
        self._actual_height: int = 720
        self._actual_width: int = 1280

        # Storage for analysis parameters (added for full post-analysis)
        self._analysis_params: dict = {}

        # MELHORIA #5: Metrics for dropped frames
        self._dropped_frames_processing: int = 0  # Frames dropped from frame_queue
        self._dropped_frames_video: int = 0  # Frames dropped from video_queue

        # Live Camera v2.2.0: User action tracking
        self._user_disconnect_action: str | None = None  # wait | resume | stop

        # Subscribe to user action events
        if self.event_bus:
            self.event_bus.subscribe(
                "CAMERA_DISCONNECT_USER_ACTION", self._on_disconnect_user_action
            )

        # Camera disconnect detection (v2.2.0)
        self._last_valid_frame_time: float | None = None  # Timestamp of last successful frame
        self._camera_disconnect_threshold_s: float = 2.0  # Gap threshold for disconnect detection
        self._camera_disconnected: bool = False  # Disconnect state flag
        self._disconnect_gaps: list[tuple[float, float]] = []  # List of (start_time, end_time) gaps
        self._recording_paused: bool = False  # Recorder pause state

        # Aquarium detection phase state
        self._aquarium_detection_phase: bool = False
        self._aquarium_detection_frames: int = 0
        self._aquarium_detection_max_frames: int = 300  # Standard: 300 frames (10s)
        self._detected_aquarium_bboxes: list[
            tuple[int, int, int, int]
        ] = []  # Collect multiple detections
        self._arena_defined_event = threading.Event()  # Signal when arena is ready
        self._animals_per_aquarium: int = 1  # Default to single subject
        self._use_external_preview: bool = False  # Track if using external UI (CanvasManager)

        # v2.2.0: Dynamic FPS adjustment
        self._target_fps: float = 30.0  # Default target FPS
        self._current_fps: float = 30.0  # Measured FPS
        self._processing_times: list[float] = []  # Rolling window of processing times
        self._frame_skip_count: int = 0  # Number of frames to skip
        self._fps_adjustment_interval: int = 30  # Adjust every N frames

        # v2.2.0: Mode selection integration
        self._preferred_mode: Any = None  # LiveCameraMode enum value (optional)

        # Session timer for countdown display (v2.3.0)
        self._session_start_time: float | None = None

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
                except Exception as e:
                    log.warning(
                        "live_camera_service.cleanup.folder_remove_failed",
                        folder=str(folder),
                        error=str(e),
                    )

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

    def set_preferred_mode(self, mode: Any) -> None:
        """Set preferred live camera mode from wizard selection.

        Args:
            mode: LiveCameraMode enum value or string name
        """
        if isinstance(mode, str):
            # Convert string to enum
            try:
                from zebtrack.core.live_camera_mode import LiveCameraMode

                self._preferred_mode = LiveCameraMode[mode]
                log.info("live_camera_service.preferred_mode_set", mode=mode)
            except (KeyError, ImportError) as e:
                log.warning(
                    "live_camera_service.preferred_mode_invalid",
                    mode=mode,
                    error=str(e),
                )
                self._preferred_mode = None
        else:
            self._preferred_mode = mode
            log.info(
                "live_camera_service.preferred_mode_set",
                mode=mode.name if hasattr(mode, "name") else str(mode),
            )

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
        analysis_config: dict | None = None,
        use_external_preview: bool = False,
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
            analysis_config: Configuration for behavioral analysis (thresholds, ROIs, etc.)

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
        self.analysis_completed = False  # Reset flag for new session
        self.set_last_detections([])  # Reset cached detections for new session
        self._animals_per_aquarium = animals_per_aquarium
        self._experiment_id = experiment_id  # Store for later use in recorder
        self._preview_window_destroyed = False  # MELHORIA #2: Reset flag for new session
        self._dropped_frames_processing = 0  # MELHORIA #5: Reset dropped frame counters
        self._dropped_frames_video = 0
        self._analysis_params = analysis_config or {}
        self._use_external_preview = use_external_preview

        # Create preview window FIRST (so we can show status updates)
        # Create window when use_external_preview=True (separate window mode)
        # Skip when use_external_preview=False (use integrated canvas in Analysis tab)
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

        # Store camera properties for later use (post-analysis)
        if self.camera:
            self._actual_fps = self.camera.actual_fps
            self._actual_width = self.camera.actual_width
            self._actual_height = self.camera.actual_height

        # Create output directory
        # ✅ FIX: Remove local import that conflicts with module-level datetime import
        # Use datetime.datetime.now() to access the datetime class from the module

        # ✅ Allow custom output directory for projects
        if output_base_dir:
            output_base = Path(output_base_dir)
        else:
            output_base = Path("live_analysis_sessions")

        output_base.mkdir(exist_ok=True)

        # ✅ v2.3.2: Cleanup existing session folders for same experiment_id
        # This prevents accumulating multiple timestamped folders when re-recording
        self._cleanup_existing_session_folders(output_base, experiment_id)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{experiment_id}_{timestamp}"
        self._current_base_name = folder_name
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

        # 🔍 DEBUG: Log zone data status
        log.info(
            "live_camera_service.zone_data_check",
            has_zone_data=zone_data is not None,
            has_polygon=zone_data.polygon if zone_data else None,
            polygon_points=len(zone_data.polygon) if zone_data and zone_data.polygon else 0,
            has_project=bool(self.project_manager.project_path) if self.project_manager else False,
        )

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

        # 🔧 FIX: Limpar filas ANTES de setar exit_event para prevenir processar frames residuais
        self._clear_queues()
        log.info("live_camera_service.queues_cleared_before_exit")

        # Signal threads to exit
        self.exit_event.set()

        # Wait for threads to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5.0)

        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)

        # ✅ NEW: Wait for video recording thread to finish
        if self.video_recording_thread and self.video_recording_thread.is_alive():
            self.video_recording_thread.join(timeout=5.0)
            log.info(
                "live_camera_service.video_recording_thread_stopped",
                frames_written=self._video_frames_written,
            )

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

        # ✅ FIX: Restore button state after session ends
        if self.event_bus:
            from zebtrack.ui.events import Events

            self.event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
            )
            self.event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
            )
            log.info("live_camera_service.buttons_restored_after_session_end")

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

            # ✅ FIX: Increased warmup for ALL cameras (USB cameras often need more time)
            # All cameras get 50 frames (~2.5s at 20fps) to stabilize exposure/white balance
            warmup_frames = 50
            warmup_timeout = 5.0  # Maximum 5 seconds for warmup
            min_success_ratio = 0.3  # Need at least 30% success to proceed

            successful_warmup = 0
            warmup_start = time.time()
            for warmup_count in range(warmup_frames):
                # Check timeout
                if time.time() - warmup_start > warmup_timeout:
                    log.warning(
                        "live_camera_service.camera_warmup_timeout",
                        camera_index=camera_index,
                        elapsed=time.time() - warmup_start,
                    )
                    break

                ret, frame = self.camera.get_frame()
                if ret and frame is not None:
                    successful_warmup += 1
                else:
                    # If frame capture fails, wait a bit longer for camera to initialize
                    time.sleep(0.1)
                time.sleep(0.05)  # 50ms between warmup frames

            # ✅ FIX: Warn if warmup had poor success rate
            success_ratio = successful_warmup / warmup_frames if warmup_frames > 0 else 0
            log.info(
                "live_camera_service.camera_warmup_complete",
                camera_index=camera_index,
                frames_requested=warmup_frames,
                frames_successful=successful_warmup,
                success_ratio=f"{success_ratio:.1%}",
                warmup_duration=f"{time.time() - warmup_start:.2f}s",
            )

            if success_ratio < min_success_ratio:
                log.warning(
                    "live_camera_service.camera_warmup_poor",
                    camera_index=camera_index,
                    success_ratio=f"{success_ratio:.1%}",
                    recommendation="Camera may not be fully ready. Consider longer warmup.",
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
        from zebtrack.core.zone_manager import MultiAquariumZoneData
        from zebtrack.ui.dialogs import LivePreviewWindow
        from zebtrack.ui.dialogs.multi_aquarium_live_preview_window import (
            MultiAquariumLivePreviewWindow,
        )

        def on_stop_callback():
            """Handle manual stop from preview window."""
            log.info("live_camera_service.manual_stop_requested")
            # 🔧 FIX: Call stop_session directly to stop threads immediately
            # Post-analysis happens automatically in stop_session
            self.stop_session()

        # ✅ FIX: Check if multi-aquarium mode and create appropriate window
        zone_data = self.project_manager.get_zone_data() if self.project_manager else None

        if isinstance(zone_data, MultiAquariumZoneData) and zone_data.aquariums:
            # Multi-aquarium mode
            num_aquariums = len(zone_data.aquariums)
            self.preview_window = MultiAquariumLivePreviewWindow(
                parent=self.root,
                camera_index=camera_index,
                num_aquariums=num_aquariums,
                duration_s=duration_s,
                on_stop_callback=on_stop_callback,
            )
            log.info(
                "live_camera_service.multi_aquarium_preview_window_created",
                num_aquariums=num_aquariums,
            )
        else:
            # Standard single-aquarium mode
            self.preview_window = LivePreviewWindow(
                parent=self.root,
                camera_index=camera_index,
                duration_s=duration_s,
                on_stop_callback=on_stop_callback,
            )
            log.info("live_camera_service.preview_window_created")

    def _start_threads(self) -> bool:
        """Start capture, processing, and video recording threads."""
        try:
            # Clear exit event
            self.exit_event.clear()
            self._video_frames_written = 0  # Reset counter

            # Start capture thread
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                name="LiveCameraCaptureThread",
                daemon=True,  # Daemon thread allows Python to exit even if thread is running
            )
            self.capture_thread.start()
            log.info("live_camera_service.capture_thread_started")

            # Start processing thread (detection + display)
            self.processing_thread = threading.Thread(
                target=self._processing_loop,
                name="LiveCameraProcessingThread",
                daemon=True,  # Daemon thread allows Python to exit even if thread is running
            )
            self.processing_thread.start()
            log.info("live_camera_service.processing_thread_started")

            # ✅ NEW: Start dedicated video recording thread
            # Follows pattern from original working code (Integração_Zeb_Arduino)
            # Video recording must be in a separate thread to never drop frames
            self.video_recording_thread = threading.Thread(
                target=self._video_recording_loop,
                name="LiveCameraVideoRecordingThread",
                daemon=True,
            )
            self.video_recording_thread.start()
            log.info("live_camera_service.video_recording_thread_started")

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

                    # Check for camera disconnect
                    self._check_camera_disconnect()

                    time.sleep(0.1)
                    continue

                # Update last valid frame timestamp
                current_time = time.time()
                self._last_valid_frame_time = current_time

                # If we were disconnected, mark reconnection
                if self._camera_disconnected:
                    self._on_camera_reconnected()

                frame_count += 1
                self._last_captured_frame = frame_count  # Track for lag calculation

                # MELHORIA #1: Create single copy of frame to share between queues
                # This reduces memory usage from 5.4MB to 2.7MB per frame (50% reduction)
                frame_copy = frame.copy()

                # ✅ PRIORITY 1: VIDEO RECORDING - NEVER DROP
                # Video recording is critical and must capture every frame
                if self.is_capturing_for_video:
                    try:
                        # Use blocking put with timeout - video is priority
                        self.video_queue.put(frame_copy, timeout=0.5)
                    except queue.Full:
                        # This should rarely happen with 600-frame queue
                        # If it does, log as critical error
                        self._dropped_frames_video += 1
                        log.error(
                            "live_camera_service.video_frame_dropped_critical",
                            frame_count=frame_count,
                            queue_size=self.video_queue.qsize(),
                            note="video_recording_may_have_gaps",
                        )

                # ✅ PRIORITY 2: ANALYSIS FRAMES - Preserve frames at analysis interval
                is_analysis_frame = (frame_count % self.analysis_interval_frames) == 0

                if is_analysis_frame:
                    # Analysis frames are important - wait up to 0.5s
                    try:
                        self.frame_queue.put((frame_count, frame_copy), timeout=0.5)
                    except queue.Full:
                        self._dropped_frames_processing += 1
                        log.warning(
                            "live_camera_service.analysis_frame_dropped",
                            frame_count=frame_count,
                            queue_backlog=self.frame_queue.qsize(),
                        )
                elif not self.frame_queue.full():
                    # Non-analysis frames: add only if space available (no waiting)
                    self.frame_queue.put_nowait((frame_count, frame_copy))
                # else: silently skip non-analysis frames when queue is full

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

    def _video_recording_loop(self):
        """
        ✅ NEW: Dedicated thread for video recording.

        This follows the pattern from the original working code (Integração_Zeb_Arduino).
        Video recording MUST be in a separate thread to ensure ALL frames are recorded
        without drops, regardless of how slow the detection/analysis may be.

        Key design decisions:
        1. Reads from video_queue (separate from frame_queue used by detection)
        2. Blocks waiting for frames (with timeout for clean exit)
        3. Writes EVERY frame to the video file
        4. Independent of detection speed - video is never dropped
        """
        log.info("live_camera_service.video_recording_loop_started")

        while not self.exit_event.is_set():
            # Only record if we're capturing for video AND recorder is ready
            if not self.is_capturing_for_video or not self.recorder:
                time.sleep(0.05)  # Small sleep to prevent busy-wait
                continue

            try:
                # Block waiting for frame with timeout (allows clean exit)
                frame = self.video_queue.get(timeout=0.5)

                # Write frame to video file
                if self.recorder and self.recorder.is_recording and self.recorder.video_writer:
                    try:
                        self.recorder.write_video_frame(frame)
                        self._video_frames_written += 1

                        # Log periodically (every 100 frames)
                        if self._video_frames_written % 100 == 0:
                            log.debug(
                                "live_camera_service.video_frames_written",
                                count=self._video_frames_written,
                                queue_size=self.video_queue.qsize(),
                            )
                    except Exception as e:
                        log.warning(
                            "live_camera_service.video_write_error",
                            error=str(e),
                            frames_written=self._video_frames_written,
                        )

            except queue.Empty:
                # Timeout - check exit condition and continue
                continue
            except Exception as e:
                log.error(
                    "live_camera_service.video_recording_error",
                    error=str(e),
                    exc_info=True,
                )
                time.sleep(0.1)

        # Log final count when thread exits
        log.info(
            "live_camera_service.video_recording_loop_finished",
            total_frames_written=self._video_frames_written,
        )

    def _processing_loop(self):  # noqa: C901
        """Thread loop for processing frames with detection."""
        log.info("live_camera_service.processing_loop_started")
        processed_count = 0
        first_frame_active = False
        # ✅ FIX Bug 1: Track frames received by processing thread, not capture thread
        # When frames are dropped due to queue being full, frame_number can skip
        # (e.g., 40 -> 150). Using a local counter ensures consistent analysis intervals.
        frames_received = 0
        last_lag_update_time = 0.0  # For throttling lag status updates

        while not self.exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            # ✅ FIX Bug 1: Increment local counter for every frame actually received
            frames_received += 1
            self._last_analyzed_frame = frame_number

            # ✅ NEW: Calculate and report analysis lag
            self._analysis_lag_frames = self._last_captured_frame - frame_number
            current_time = time.time()

            # Update UI with lag status (throttled to every 2 seconds)
            if self._analysis_lag_frames > self._analysis_lag_warning_threshold:
                if current_time - last_lag_update_time > 2.0:
                    last_lag_update_time = current_time
                    lag_seconds = self._analysis_lag_frames / 30.0  # Approximate
                    self._publish_analysis_lag_status(lag_seconds)

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
                                f"⏳ Estabilizando imagem... ({frame_number}/30)", color="orange"
                            )
                        continue

                    # MELHORIA: Skip frames during detection to cover more time
                    # Process only every 5th frame. With 10 frames max, this covers ~50 frames (1.6s @ 30fps)
                    # instead of just 10 frames (0.33s). This helps bypass initial camera auto-adjustments.
                    if frame_number % 5 != 0:
                        self._aquarium_detection_frames += (
                            1  # Count skipped frames towards timeout?
                        )
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
                                                area_ratio=f"{bbox_area / frame_area:.2f}",
                                            )

                                        # Publish progress event
                                        if self.event_bus:
                                            self.event_bus.publish_event(
                                                "AQUARIUM_DETECTION_PROGRESS",
                                                {
                                                    "frame_number": self._aquarium_detection_frames,
                                                    "max_frames": self._aquarium_detection_max_frames,
                                                    "frame_image": frame.copy(),
                                                    "detected_bbox": (
                                                        int(x1),
                                                        int(y1),
                                                        int(x2),
                                                        int(y2),
                                                    ),
                                                    "is_valid": True,
                                                    "experiment_id": self._analysis_params.get(
                                                        "experiment_id", "unknown"
                                                    ),
                                                    "valid_count": len(
                                                        self._detected_aquarium_bboxes
                                                    ),
                                                },
                                            )
                                    else:
                                        log.info(
                                            "live_camera_service.aquarium_rejected_area",
                                            frame=frame_number,
                                            area_ratio=f"{bbox_area / frame_area:.2f}",
                                            min_ratio=min_ratio,
                                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                                        )

                                        # Publish progress event for invalid detection
                                        if self.event_bus and frame_number % 5 == 0:
                                            self.event_bus.publish_event(
                                                "AQUARIUM_DETECTION_PROGRESS",
                                                {
                                                    "frame_number": self._aquarium_detection_frames,
                                                    "max_frames": self._aquarium_detection_max_frames,
                                                    "frame_image": frame.copy(),
                                                    "detected_bbox": (
                                                        int(x1),
                                                        int(y1),
                                                        int(x2),
                                                        int(y2),
                                                    ),
                                                    "is_valid": False,
                                                    "experiment_id": self._analysis_params.get(
                                                        "experiment_id", "unknown"
                                                    ),
                                                    "valid_count": len(
                                                        self._detected_aquarium_bboxes
                                                    ),
                                                },
                                            )

                        if not detection_found_in_frame:
                            # Limit "nothing found" logs to avoid flooding info channel
                            if frame_number % 5 == 0:
                                log.info(
                                    "live_camera_service.no_valid_aquarium_in_frame",
                                    frame=frame_number,
                                    num_raw_detections=len(detections),
                                    target_class_id=target_class_id,
                                )

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
                # ✅ FIX Bug 1: Use frames_received (local counter) instead of frame_number
                # This ensures consistent analysis intervals even when frames are dropped.
                # frame_number can skip (e.g., 40 -> 150) when queue is full.
                should_analyze = (frames_received % self.analysis_interval_frames) == 0
                should_display = (frames_received % self.display_interval_frames) == 0

                detections = []

                if should_analyze:
                    # v2.2.0: Start timing for FPS adjustment
                    frame_start_time = time.time()

                    processed_count += 1

                    # Apply calibration if available
                    calib_data = self.project_manager.project_data.get("calibration", {})
                    h_matrix = calib_data.get("homography_matrix")
                    target_dims = calib_data.get("target_dims_px")

                    if h_matrix and target_dims:
                        h_matrix = np.array(h_matrix)
                        frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

                    # Run detection
                    detector = self.detector_service.detector
                    if detector:
                        # v2.2.0: Check for multi-aquarium zone data
                        zone_data = self.project_manager.get_zone_data()
                        is_multi_aquarium = hasattr(zone_data, "aquariums") and zone_data.aquariums

                        # 🔍 DEBUG: Log detection attempt
                        log.debug(
                            "live_camera_service.detection_attempt",
                            frame_number=frame_number,
                            is_multi_aquarium=is_multi_aquarium,
                            has_detector=detector is not None,
                            conf_threshold=getattr(detector.plugin, "conf_threshold", None)
                            if hasattr(detector, "plugin")
                            else None,
                        )

                        if is_multi_aquarium:
                            # Multi-aquarium processing with parallel detection
                            detections = self._run_multi_aquarium_detection(
                                frame, frame_number, zone_data
                            )
                        else:
                            # Standard single aquarium detection
                            # 🔧 FIX: Use low confidence threshold to ensure detections during live sessions
                            detections, _command = detector.detect(
                                frame, "live", conf_threshold=0.05
                            )

                    # v2.2.0: Adjust FPS dynamically based on processing time
                    # ✅ FIX: Use return value to potentially skip next analysis interval
                    frame_processing_time = time.time() - frame_start_time
                    should_continue_processing = self._adjust_fps_dynamically(
                        frame_number, frame_processing_time
                    )

                    # If dynamic FPS says skip, update analysis interval
                    if not should_continue_processing:
                        log.debug(
                            "live_camera_service.fps_skip_triggered",
                            frame_number=frame_number,
                            processing_time=frame_processing_time,
                        )

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
                            self.recorder.write_detection_data(timestamp, frame_number, detections)
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
                            recorder_start_time=self.recorder.start_time if self.recorder else None,
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

                # ✅ VIDEO RECORDING: Now handled by dedicated _video_recording_loop thread
                # This ensures video is recorded from video_queue at full framerate
                # while analysis can run at reduced interval without affecting video quality

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
                    if self.root and not self._preview_window_destroyed:
                        self.root.after(0, self.preview_window.update_frame, frame, detections)

                # ✅ INTEGRATED CANVAS: Emit event for main UI when NOT using external preview
                # When use_external_preview=False, frames go to integrated Analysis tab canvas
                # CRITICAL: This must be OUTSIDE the preview_window check since we don't create
                # preview_window when using integrated canvas!
                # ✅ FIX: Check exit_event before emitting to prevent infinite loop after session ends
                if (
                    should_display
                    and not self._use_external_preview
                    and self.event_bus
                    and not self.exit_event.is_set()
                ):
                    # Emit event to update main UI canvas
                    # We pass a copy of the frame to avoid thread safety issues
                    from zebtrack.ui.events import Events

                    log.debug(
                        "live_camera_service.emitting_ui_update_frame",
                        frame_number=frame_number,
                        has_detections=len(detections) if detections else 0,
                    )

                    self.event_bus.publish_event(
                        Events.UI_UPDATE_LIVE_FRAME,
                        {
                            "frame": frame,  # Numpy array
                            "detections": detections,
                            "fps": self._actual_fps,
                        },
                    )
                elif (
                    should_display
                    and not self._use_external_preview
                    and not self.exit_event.is_set()
                ):
                    log.warning(
                        "live_camera_service.no_event_bus",
                        frame_number=frame_number,
                        has_event_bus=self.event_bus is not None,
                    )

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
        # Store session start time for countdown display
        self._session_start_time = time.time()

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

            # Start periodic countdown updates for integrated canvas mode
            if not self._use_external_preview:
                self._update_session_countdown(duration_s)

    def _update_session_countdown(self, duration_s: float):
        """Update status bar with session countdown for integrated canvas mode.

        Args:
            duration_s: Total session duration in seconds
        """
        if not self.root or self.exit_event.is_set() or not hasattr(self, "_session_start_time"):
            return

        elapsed = time.time() - self._session_start_time
        remaining = max(0, duration_s - elapsed)

        # Update status via event bus
        if self.event_bus and remaining > 0:
            from zebtrack.ui.events import Events

            status_msg = (
                f"● Gravando: {elapsed:.1f}s / {duration_s:.1f}s (Restante: {remaining:.1f}s)"
            )

            self.event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": status_msg},
            )

            # Schedule next update (every 1 second)
            self.root.after(1000, self._update_session_countdown, duration_s)

    def _publish_analysis_lag_status(self, lag_seconds: float):
        """Publish analysis lag status to UI.

        When analysis is behind real-time recording, this updates the status bar
        to inform the user that recording continues but analysis is catching up.

        Args:
            lag_seconds: How many seconds behind real-time the analysis is
        """
        if not self.event_bus:
            return

        from zebtrack.ui.events import Events

        # Format message based on lag severity
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

        self.event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": status_msg},
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
                from zebtrack.analysis.analysis_service import AnalysisService
                from zebtrack.analysis.reporter import Reporter

                # Find generated trajectory parquet
                trajectory_files = glob.glob(str(output_dir / "3_CoordMovimento_*.parquet"))

                if not trajectory_files:
                    log.warning(
                        "live_camera_service.no_trajectory_found", output_dir=str(output_dir)
                    )
                    if self.root:
                        self.root.after(0, self._show_completion_message, output_dir, False)
                    return

                trajectory_file = Path(trajectory_files[0])
                df = pd.read_parquet(trajectory_file)

                if df.empty:
                    log.warning("live_camera_service.empty_trajectory")
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

                # --- NEW: FULL BEHAVIORAL ANALYSIS ---
                log.info("live_camera_service.full_analysis.start")

                # 1. Collect required parameters
                # Use analysis_config stored during start_session if available
                # Fallback to project_manager/settings
                analysis_service = AnalysisService(settings_obj=self.settings)
                params = analysis_service.collect_analysis_parameters(
                    self.project_manager.project_data
                )

                # Update with session-specific overrides if provided
                if self._analysis_params:
                    # Map session keys to internal analysis keys
                    # Dialog: freezing_velocity_threshold -> Internal: freezing_vel_threshold
                    if "freezing_velocity_threshold" in self._analysis_params:
                        params["freezing_vel_threshold"] = self._analysis_params[
                            "freezing_velocity_threshold"
                        ]
                    if "freezing_min_duration_s" in self._analysis_params:
                        params["freezing_min_duration"] = self._analysis_params[
                            "freezing_min_duration_s"
                        ]
                    if "smoothing_window_length" in self._analysis_params:
                        params["smoothing_window_length"] = self._analysis_params[
                            "smoothing_window_length"
                        ]
                    if "smoothing_polyorder" in self._analysis_params:
                        params["smoothing_polyorder"] = self._analysis_params["smoothing_polyorder"]
                    if "behavioral_analysis" in self._analysis_params:
                        params["behavioral_config"].update(
                            self._analysis_params["behavioral_analysis"]
                        )

                # 2. Get calibration and zone data
                calib_data = self.project_manager.project_data.get("calibration", {})
                pixelcm_x = calib_data.get("pixelcm_x", 1.0)
                pixelcm_y = calib_data.get("pixelcm_y", 1.0)
                video_height = self._actual_height

                # Get zones (arena and ROIs)
                zone_data = self.project_manager.get_zone_data()
                arena_polygon = zone_data.polygon or []

                # Build ROI objects
                from zebtrack.analysis.roi import ROI

                rois = []
                roi_colors = {}
                if zone_data.roi_polygons:
                    for i, poly in enumerate(zone_data.roi_polygons):
                        name = (
                            zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                        )
                        color = (
                            zone_data.roi_colors[i]
                            if i < len(zone_data.roi_colors)
                            else (255, 0, 0)
                        )
                        rois.append(ROI(name=name, polygon=poly))
                        roi_colors[name] = color

                # 3. Run full analysis
                fps = self._actual_fps
                video_filename = f"{self._current_base_name}.mp4"
                video_path = output_dir / video_filename

                metadata = {
                    "experiment_id": self._experiment_id,
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "camera_index": self._analysis_params.get("camera_index", "N/A"),
                    "num_aquariums": 1,
                    "animals_per_aquarium": self._animals_per_aquarium,
                }

                # Add extra metadata if provided in analysis_params
                if self._analysis_params:
                    for key in ["group", "day", "subject_id"]:
                        if key in self._analysis_params:
                            metadata[key] = self._analysis_params[key]

                analysis_result = analysis_service.run_full_analysis_as_dto(
                    trajectory_df=df,
                    pixelcm_x=pixelcm_x,
                    pixelcm_y=pixelcm_y,
                    video_height_px=video_height,
                    arena_polygon_px=arena_polygon,
                    rois=rois,
                    fps=fps,
                    metadata=metadata,
                    roi_colors=roi_colors,
                    freezing_vel_threshold=params["freezing_vel_threshold"],
                    freezing_min_duration=params["freezing_min_duration"],
                    smoothing_window_length=params["smoothing_window_length"],
                    smoothing_polyorder=params["smoothing_polyorder"],
                    behavioral_config=params["behavioral_config"],
                    video_path=str(video_path),
                )

                # 4. Generate Reports
                reporter = Reporter.from_analysis(analysis_result)

                # Save Excel summary
                excel_path = output_dir / f"4_RelatorioSumario_{self._experiment_id}.xlsx"
                reporter.export_summary_data(str(excel_path), format="excel")

                # Save Word report
                word_path = output_dir / f"5_RelatorioIndividual_{self._experiment_id}.docx"
                reporter.export_individual_report(str(word_path))

                log.info(
                    "live_camera_service.reports_generated",
                    excel=str(excel_path),
                    word=str(word_path),
                )

                # 5. Register outputs in project if active
                if self.project_manager.project_path:
                    self.project_manager.register_processing_outputs(
                        video_path=str(video_path),
                        results_dir=str(output_dir),
                        trajectory_path=str(trajectory_file),
                        summary_excel=str(excel_path),
                        report_path=str(word_path),
                        experiment_id=self._experiment_id,
                        group=self._analysis_params.get("group"),
                        day=self._analysis_params.get("day"),
                        subject_id=self._analysis_params.get("subject_id"),
                    )

                    # Refresh project views to show the new results
                    if self.event_bus:
                        from zebtrack.ui.events import Events

                        self.event_bus.publish_event(
                            Events.UI_REFRESH_PROJECT_VIEWS, {"reason": "Live analysis complete"}
                        )

                # --- FINALIZE ---
                total_frames = df["frame"].nunique()
                total_detections = len(df)
                unique_tracks = df["track_id"].nunique() if "track_id" in df.columns else 0

                if self.root:
                    stats = {
                        "frames": total_frames,
                        "detections": total_detections,
                        "tracks": unique_tracks,
                    }
                    self.root.after(0, self._show_completion_message, output_dir, True, stats, None)

            except Exception as e:
                log.error("live_camera_service.post_analysis_error", error=str(e), exc_info=True)
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
        from zebtrack.core.zone_manager import MultiAquariumZoneData

        zone_data = self.project_manager.get_zone_data() if self.project_manager else ZoneData()

        # Check if multi-aquarium setup (limit: 2 aquariums max)
        is_multi_aquarium = isinstance(zone_data, MultiAquariumZoneData)

        # Start recorder
        if self.is_capturing_for_video and self.recorder:
            try:
                if is_multi_aquarium and len(zone_data.aquariums) <= 2:
                    # Multi-aquarium recording (max 2 aquariums)
                    zones_by_aquarium = {
                        aq_id: aq_data.zone for aq_id, aq_data in zone_data.aquariums.items()
                    }

                    recorder_started = self.recorder.start_recording_multi_aquarium(
                        output_folder=str(self.current_output_dir),
                        width=self.camera.actual_width if self.camera else 640,
                        height=self.camera.actual_height if self.camera else 480,
                        zones_by_aquarium=zones_by_aquarium,
                        base_name=f"{self._experiment_id}",
                    )

                    log.info(
                        "live_camera_service.recorder_started_multi_aquarium",
                        aquarium_count=len(zones_by_aquarium),
                    )
                elif is_multi_aquarium and len(zone_data.aquariums) > 2:
                    # Exceeds 2-aquarium limit
                    log.error(
                        "live_camera_service.multi_aquarium_limit_exceeded",
                        count=len(zone_data.aquariums),
                        max=2,
                    )
                    return
                else:
                    # Standard single aquarium recording
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
                    multi_aquarium=is_multi_aquarium,
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
        from zebtrack.core.detector import ZoneData

        w = self._actual_width
        h = self._actual_height

        if self._detected_aquarium_bboxes:
            # Use median of detected bboxes to create arena
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

        # Calculate pixel-to-cm ratio if dimensions provided
        if self._analysis_params:
            width_cm = self._analysis_params.get("aquarium_width_cm", 0)
            height_cm = self._analysis_params.get("aquarium_height_cm", 0)

            if width_cm > 0 and height_cm > 0:
                # Get arena bounding box dimensions in pixels
                pts = np.array(arena_polygon)
                min_x, min_y = np.min(pts, axis=0)
                max_x, max_y = np.max(pts, axis=0)
                width_px = max_x - min_x
                height_px = max_y - min_y

                if width_px > 0 and height_px > 0:
                    pixelcm_x = width_px / width_cm
                    pixelcm_y = height_px / height_cm

                    # Store in project calibration data
                    calib = self.project_manager.project_data.setdefault("calibration", {})
                    calib["pixelcm_x"] = pixelcm_x
                    calib["pixelcm_y"] = pixelcm_y
                    calib["aquarium_width_cm"] = width_cm
                    calib["aquarium_height_cm"] = height_cm

                    log.info(
                        "live_camera_service.calibration_calculated",
                        pixelcm_x=f"{pixelcm_x:.2f}",
                        pixelcm_y=f"{pixelcm_y:.2f}",
                        width_cm=width_cm,
                        height_cm=height_cm,
                    )

        # Persist if project exists so future sessions can reuse the arena
        should_persist = bool(self.project_manager.project_path)
        self.project_manager.save_zone_data(zone_data, video_path=None, persist=should_persist)

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

    def _run_multi_aquarium_detection(
        self, frame: np.ndarray, frame_number: int, zone_data: Any
    ) -> list:
        """Run detection for multi-aquarium setup using partitioned processing.

        Args:
            frame: Full camera frame
            frame_number: Current frame number
            zone_data: MultiAquariumZoneData with per-aquarium zones

        Returns:
            List of detections with adjusted track IDs (aquarium_id * 1000 + local_id)
        """
        detector = self.detector_service.detector
        if not detector:
            return []

        try:
            # Use optimized partitioned detection if available
            if hasattr(detector, "detect_partitioned_optimized"):
                all_detections = detector.detect_partitioned_optimized(
                    frame=frame,
                    zone_data=zone_data,
                    context="live",
                )
            elif hasattr(detector, "detect_partitioned_parallel"):
                all_detections = detector.detect_partitioned_parallel(
                    frame=frame,
                    zone_data=zone_data,
                    context="live",
                )
            else:
                # Fallback to sequential processing
                log.warning("live_camera_service.no_partitioned_detection_fallback")
                all_detections, _ = detector.detect(frame, "live")
                return all_detections if isinstance(all_detections, list) else []

            # Record detections per aquarium if recorder supports it
            if self.recorder and self.recorder.start_time:
                timestamp = time.time() - self.recorder.start_time

                if hasattr(self.recorder, "write_partitioned_detection_data"):
                    # Use partitioned writer for multi-aquarium
                    self.recorder.write_partitioned_detection_data(
                        timestamp=timestamp,
                        frame=frame_number,
                        aquarium_detections=all_detections,
                    )
                else:
                    # Fallback: write flattened detections
                    flat_detections = []
                    for aq_id, dets in all_detections.items():
                        flat_detections.extend(dets)

                    if flat_detections:
                        self.recorder.write_detection_data(timestamp, frame_number, flat_detections)

                log.info(
                    "live_camera_service.multi_aquarium_detection_written",
                    frame_number=frame_number,
                    aquariums=len(all_detections),
                    total_detections=sum(len(dets) for dets in all_detections.values()),
                )

            # Flatten detections for preview overlay
            flat_detections = []
            for aq_id, dets in all_detections.items():
                flat_detections.extend(dets)

            return flat_detections

        except Exception as e:
            log.error(
                "live_camera_service.multi_aquarium_detection_failed",
                error=str(e),
                exc_info=True,
            )
            # Fallback to single detection
            detections, _ = detector.detect(frame, "live")
            return detections

    def _check_camera_disconnect(self) -> None:
        """Check if camera has been disconnected based on frame gap.

        Detects disconnects when no valid frames received for > threshold seconds.
        Publishes CAMERA_DISCONNECT_DETECTED event and pauses recorder.
        """
        if self._last_valid_frame_time is None:
            # First frames, no disconnect yet
            return

        current_time = time.time()
        gap_duration = current_time - self._last_valid_frame_time

        if gap_duration > self._camera_disconnect_threshold_s and not self._camera_disconnected:
            # Camera disconnected
            self._camera_disconnected = True
            gap_start_time = self._last_valid_frame_time

            log.error(
                "live_camera_service.camera_disconnected",
                gap_duration=f"{gap_duration:.1f}s",
                threshold=f"{self._camera_disconnect_threshold_s}s",
            )

            # Pause recorder to avoid writing invalid/cached frames
            if self.recorder and not self._recording_paused:
                try:
                    self.recorder.pause_recording()
                    self._recording_paused = True
                    log.info("live_camera_service.recorder_paused")
                except AttributeError:
                    # Recorder doesn't support pause yet (will implement next)
                    log.warning("live_camera_service.recorder_pause_not_supported")
                except Exception as e:
                    log.error("live_camera_service.recorder_pause_failed", error=str(e))

            # Publish disconnect event
            if self.event_bus:
                self.event_bus.publish_event(
                    "CAMERA_DISCONNECT_DETECTED",
                    {
                        "gap_duration_s": gap_duration,
                        "gap_start_time": gap_start_time,
                        "experiment_id": self._analysis_params.get("experiment_id", "unknown"),
                    },
                )

            # Record gap start
            self._disconnect_gaps.append((gap_start_time, None))  # End time TBD

    def _on_camera_reconnected(self) -> None:
        """Handle camera reconnection after disconnect.

        Resumes recorder and logs gap duration for metadata.
        """
        if not self._camera_disconnected:
            return

        current_time = time.time()

        # Find the open gap and close it
        if self._disconnect_gaps and self._disconnect_gaps[-1][1] is None:
            gap_start = self._disconnect_gaps[-1][0]
            gap_duration = current_time - gap_start
            self._disconnect_gaps[-1] = (gap_start, current_time)

            log.info(
                "live_camera_service.camera_reconnected",
                gap_duration=f"{gap_duration:.1f}s",
            )

        # Resume recorder
        if self.recorder and self._recording_paused:
            try:
                self.recorder.resume_recording()
                self._recording_paused = False
                log.info("live_camera_service.recorder_resumed")
            except AttributeError:
                log.warning("live_camera_service.recorder_resume_not_supported")
            except Exception as e:
                log.error("live_camera_service.recorder_resume_failed", error=str(e))

        # Publish reconnect event
        if self.event_bus:
            self.event_bus.publish_event(
                "CAMERA_RECONNECTED",
                {
                    "gap_duration_s": gap_duration if self._disconnect_gaps else 0.0,
                    "total_gaps": len(self._disconnect_gaps),
                },
            )

        self._camera_disconnected = False

    def _on_disconnect_user_action(self, event_data: dict[str, Any]) -> None:
        """Handle user action from disconnect recovery dialog.

        Args:
            event_data: Event payload with 'action' (wait|resume|stop) and 'experiment_id'
        """
        action = event_data.get("action", "wait")
        experiment_id = event_data.get("experiment_id", "unknown")

        log.info(
            "live_camera_service.disconnect_user_action",
            action=action,
            experiment_id=experiment_id,
        )

        with self._lock:
            self._user_disconnect_action = action

        if action == "resume":
            # Force reconnect check on next iteration
            if self._camera_disconnected:
                log.info("live_camera_service.force_resume_attempt")
                # The processing loop will detect valid frames and call _on_camera_reconnected
        elif action == "stop":
            # Stop session gracefully
            log.info("live_camera_service.stop_by_user_action")
            self.stop_session()
        # else action == "wait": Continue monitoring for automatic reconnection

    def _adjust_fps_dynamically(self, frame_number: int, processing_time: float) -> bool:
        """Adjust FPS dynamically based on processing performance.

        Monitors processing time and adjusts frame skip to maintain target FPS.
        Uses exponentially weighted moving average for smoothing.

        Args:
            frame_number: Current frame number
            processing_time: Time taken to process this frame (seconds)

        Returns:
            True if frame should be processed, False if should skip
        """
        # Track processing time
        self._processing_times.append(processing_time)

        # Keep only last N samples for moving average
        max_samples = 30
        if len(self._processing_times) > max_samples:
            self._processing_times = self._processing_times[-max_samples:]

        # Calculate measured FPS every N frames
        if frame_number % self._fps_adjustment_interval == 0 and len(self._processing_times) >= 10:
            avg_processing_time = sum(self._processing_times) / len(self._processing_times)
            self._current_fps = 1.0 / avg_processing_time if avg_processing_time > 0 else 30.0

            # Adjust frame skip based on performance
            if self._current_fps < self._target_fps * 0.7:  # >30% slower than target
                # Processing is too slow, increase skip
                self._frame_skip_count = min(4, self._frame_skip_count + 1)
                log.warning(
                    "live_camera_service.fps_too_low",
                    measured_fps=f"{self._current_fps:.1f}",
                    target_fps=f"{self._target_fps:.1f}",
                    frame_skip=self._frame_skip_count,
                )
            elif (
                self._current_fps > self._target_fps * 1.2 and self._frame_skip_count > 0
            ):  # >20% faster
                # Processing is fast enough, reduce skip
                self._frame_skip_count = max(0, self._frame_skip_count - 1)
                log.info(
                    "live_camera_service.fps_improved",
                    measured_fps=f"{self._current_fps:.1f}",
                    target_fps=f"{self._target_fps:.1f}",
                    frame_skip=self._frame_skip_count,
                )

        # Determine if frame should be processed
        if self._frame_skip_count > 0:
            # Skip every N frames
            should_process = (frame_number % (self._frame_skip_count + 1)) == 0
            if not should_process:
                log.debug(
                    "live_camera_service.frame_skipped",
                    frame_number=frame_number,
                    skip_pattern=self._frame_skip_count + 1,
                )
            return should_process

        return True  # Process all frames when skip=0

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
