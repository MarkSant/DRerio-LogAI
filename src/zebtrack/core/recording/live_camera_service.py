"""Live Camera Service — Facade over extracted mixin modules.

Manages live camera analysis sessions including:
- Thread coordination for frame capture and processing
- Camera feed management
- Detection processing
- Live preview window updates

Decomposed via mixin pattern (Phase 2.2):
  - ``LiveSessionManagerMixin``  (live_session_manager.py)
  - ``CameraConnectionMixin``    (camera_connection_handler.py)
  - ``FrameProcessingMixin``     (frame_processing_pipeline.py)
  - ``LiveAnalysisPostProcessorMixin`` (live_analysis_post_processor.py)
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal

import structlog

from zebtrack.core.recording.camera_connection_handler import CameraConnectionMixin
from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin
from zebtrack.core.recording.live_analysis_post_processor import LiveAnalysisPostProcessorMixin
from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin

if TYPE_CHECKING:
    from tkinter import Misc

    from zebtrack.core.detection.multi_aquarium_detector import MultiAquariumDetector
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.recording.recording_service import RecordingService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.dialogs import LivePreviewWindow
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class DetectorContextManager:
    """Context manager to ensure detector context is always restored, even on exceptions.

    Usage:
        with DetectorContextManager(detector, "tracking") as manager:
            # Do processing with new context
            pass
        # Context is automatically restored here
    """

    def __init__(self, detector_service: DetectorService | None, new_context: str):
        """Initialize context manager.

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
            except (AttributeError, ValueError) as e:
                log.warning(
                    "detector_context.restore_failed",
                    saved_context=self.saved_context,
                    error=str(e),
                )


class LiveCameraService(
    LiveSessionManagerMixin,
    CameraConnectionMixin,
    FrameProcessingMixin,
    LiveAnalysisPostProcessorMixin,
):
    """
    Service for managing live camera analysis sessions.

    Coordinates camera capture, detection processing, and preview display
    through dedicated threads, following the service layer pattern.

    Supports context manager protocol for automatic session cleanup.

    Architecture Note (ADR-004):
        This service intentionally uses a different display mechanism than
        recorded video analysis:

        - Recorded Video: Uses `CanvasManager` via `UIEvents.UI_DISPLAY_FRAME`
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
        event_bus: EventBusV2,  # Injected EventBusV2
        root: Misc | None = None,
        project_workflow_service: ProjectWorkflowService | None = None,
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
            event_bus: EventBusV2 for UI notifications
            root: Tkinter root for UI updates
            project_workflow_service: ProjectWorkflowService used to resolve
                project-specific model settings (active weight / use_openvino)
                before starting a live session. Optional to keep older callers
                working — fallback uses global ``settings.model_selection``.
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
        self.project_workflow_service = project_workflow_service

        # Threading infrastructure
        self._lock = threading.Lock()  # Protects all shared state below
        # ✅ ARCHITECTURE v2.3.1: Separate priorities for video vs analysis
        # Video queue: LARGE (600 = 20s @ 30fps) - video recording is CRITICAL, never drop
        # Frame queue: Medium (180 = 6s @ 30fps) - analysis can lag behind real-time
        self.frame_queue: queue.Queue[Any] = queue.Queue(maxsize=180)
        self.video_queue: queue.Queue[Any] = queue.Queue(
            maxsize=600
        )  # Priority: recording > analysis
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
        # Frames com pelo menos uma detecção na sessão live. Antes era criado
        # implicitamente via getattr() no _processing_loop e NUNCA zerado entre
        # sessões — fazendo a 2ª gravação somar sobre a 1ª. Inicializado aqui e
        # zerado em start_session para reiniciar a cada sessão.
        self._live_detected_frames: int = 0  # Counter for frames with detections

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
        self.on_session_stopped: Callable[[bool], None] | None = None

        # Subscribe to user action events
        if self.event_bus:
            from zebtrack.ui.event_bus_v2 import UIEvents

            self.event_bus.subscribe(
                UIEvents.CAMERA_DISCONNECT_USER_ACTION, self._on_disconnect_user_action
            )

        # Camera disconnect detection (v2.2.0)
        self._last_valid_frame_time: float | None = None  # Timestamp of last successful frame
        self._camera_disconnect_threshold_s: float = 2.0  # Gap threshold for disconnect detection
        self._camera_disconnected: bool = False  # Disconnect state flag
        self._disconnect_gaps: list[
            tuple[float, float | None]
        ] = []  # List of (start_time, end_time) gaps
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

        # Phase 4.3: Lazily-created MultiAquariumDetector (shares plugin w/ SingleDetector)
        self._multi_aq_detector: MultiAquariumDetector | None = None

        # Closed-loop latency logging (per live session; built lazily on the
        # first tracked Arduino trigger, finalized at session end).
        self._closed_loop_log: Any = None
        self._closed_loop_event_seq: int = 0

    # ── Thread-safe properties ──────────────────────────────────────────

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
                from zebtrack.core.recording.live_camera_mode import LiveCameraMode

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

    # ── Context-manager protocol ────────────────────────────────────────

    def __enter__(self) -> LiveCameraService:
        """Enter context manager - service is ready for session start."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        """Exit context manager - cleanup session resources.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            self.exit_event.set()
            if self.current_output_dir:
                log.info(
                    "live_camera_service.exit.session_complete",
                    output_dir=str(self.current_output_dir),
                )
            else:
                log.info("live_camera_service.exit.no_active_session")
        # except Exception justified: graceful shutdown — cleanup must not propagate
        except Exception as e:
            log.warning("live_camera_service.cleanup.failed", error=str(e), exc_info=True)
        return False
