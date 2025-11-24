"""Video Processing Service for ZebTrack-AI.

Phase 7.2: Extracts video processing logic from MainViewModel to dedicated service.

This service handles:
- Video tracking orchestration (_run_tracking_if_needed)
- Single video processing workflow (_process_single_video)
- Progress callbacks and UI notifications
- Result path resolution and metadata handling

Responsibilities:
- Coordinate detector, recorder, and project_manager for video processing
- Manage progress callbacks and cancellation events
- Handle initial frame display and trajectory validation
- Resolve output directories based on project context

Dependencies (injected):
- detector: Detector instance for object detection
- recorder: Recorder instance for trajectory writing
- project_manager: ProjectManager for project state
- state_manager: StateManager for centralized state
- ui_coordinator: UICoordinator for UI updates
- root: Tkinter root for scheduling UI updates
- view: ApplicationGUI for direct UI access (minimized)
- cancel_event: threading.Event for cancellation signaling
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

if TYPE_CHECKING:
    from zebtrack.core.detector import Detector
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_coordinator import UICoordinator
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import ZoneData
from zebtrack.ui.events import Events

log = structlog.get_logger()


@dataclass
class VideoContext:
    """Shared video capture metadata to avoid redundant I/O.

    v2.2: Added skip_threshold for dynamic frame skip calibration.
    """

    path: str
    cap: cv2.VideoCapture
    width: int
    height: int
    fps: float
    first_frame: np.ndarray | None = None
    skip_threshold: int = 60  # v2.2: Calibrated frame skip threshold (default fallback)

    def reset(self) -> None:
        """Seek capture back to the first frame if still open."""
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def release(self) -> None:
        """Release underlying capture safely."""
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        self.cap = None


class VideoProcessingService:
    """Service for video processing orchestration.

    Phase 7.2: Consolidates video processing logic previously scattered
    in MainViewModel into a cohesive service layer.
    """

    def __init__(
        self,
        *,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        ui_event_bus: EventBus,
        cancel_event,  # threading.Event
        settings_obj: Settings,
        detector: Detector | None = None,
        recorder: Recorder | None = None,
    ):
        """Initialize VideoProcessingService with injected dependencies.

        v2.2: Removed view and root parameters for event-driven decoupling.

        Args:
            project_manager: ProjectManager for project state
            state_manager: StateManager for centralized state
            ui_coordinator: UICoordinator for UI updates
            ui_event_bus: Event bus for UI events (publishes ERROR_OCCURRED, etc.)
            cancel_event: Threading event for cancellation signaling
            settings_obj: Settings instance for configuration access
        """
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.ui_event_bus = ui_event_bus
        self.cancel_event = cancel_event
        self.settings = settings_obj
        # Legacy attributes kept for backward compatibility with orchestrators/tests
        self.detector = detector
        self.recorder = recorder

        log.info("video_processing_service.init.complete")

    def _create_video_context(self, video_path: Path | str) -> VideoContext | None:
        """Open a video once and cache metadata/first frame for downstream steps.

        v2.2: Dynamic frame skip calibration with warm-up + 1 seek measurement.
        """
        import time

        normalized_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        cap = cv2.VideoCapture(normalized_path)
        if not cap.isOpened():
            log.error("video_processing.video_open_failed", path=normalized_path)
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or getattr(self.settings.video_processing, "fps", 30.0)

        # v2.2: Dynamic frame skip calibration
        # Warm-up seek to reset internal state
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        cap.read()  # Discard warm-up frame

        # Measure single seek to frame 100
        t0 = time.perf_counter()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
        cap.read()  # Execute seek
        seek_time_ms = (time.perf_counter() - t0) * 1000

        # Calculate optimal skip threshold
        if seek_time_ms < 10:
            skip_threshold = 120  # Fast seek - use larger skip
        elif seek_time_ms < 50:
            skip_threshold = 80   # Medium seek
        else:
            skip_threshold = 60   # Slow seek - conservative skip

        log.info(
            "video_processing.frame_skip_calibrated",
            path=Path(normalized_path).name,
            seek_time_ms=round(seek_time_ms, 2),
            skip_threshold=skip_threshold,
        )

        # Reset to beginning for first frame capture
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        first_frame = None
        ret, frame = cap.read()
        if ret:
            first_frame = frame.copy()
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        else:
            log.debug("video_processing.initial_frame_missing", path=normalized_path)

        return VideoContext(
            path=normalized_path,
            cap=cap,
            width=width,
            height=height,
            fps=fps,
            first_frame=first_frame,
            skip_threshold=skip_threshold,  # v2.2: Add calibrated threshold
        )

    def _seek_to_frame(
        self,
        cap: cv2.VideoCapture,
        target_frame: int,
        current_frame: int,
        skip_threshold: int = 60,
    ) -> bool:
        """Optimized frame seeking using hybrid grab()/set() strategy.

        v2.2: Uses calibrated skip_threshold to choose between:
        - grab() for small sequential gaps (< threshold)
        - set() for large jumps (>= threshold)

        Args:
            cap: OpenCV VideoCapture object
            target_frame: Destination frame number
            current_frame: Current position
            skip_threshold: Gap threshold for set() vs grab() decision

        Returns:
            True if seek succeeded, False otherwise
        """
        gap = target_frame - current_frame

        if gap <= 0:
            # Backward seek always uses set()
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            return True
        elif gap < skip_threshold:
            # Small gap - use grab() for sequential advance
            for _ in range(gap):
                if not cap.grab():
                    return False
            return True
        else:
            # Large gap - use set() for direct seek
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            return True

    def display_initial_frame(self, video_path: Path | str, frame: np.ndarray | None = None) -> None:
        """Display first frame of video in UI.

        Args:
            video_path: Path to video file
        """
        if frame is not None:
            self.ui_coordinator.display_frame(self.view, frame)
            return

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                self.ui_coordinator.display_frame(self.view, frame)
        except Exception as exc:
            log.warning("video_processing.frame_display_error", error=str(exc))
        finally:
            if cap is not None:
                cap.release()

    def resolve_results_path(
        self,
        *,
        experiment_id: str,
        video_path: str,
        metadata_context: dict | None,
        single_video_config: dict | None,
        output_base_dir: str,
    ) -> tuple[Path, bool]:
        """Resolve output directory for processing results.

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to source video
            metadata_context: Optional metadata dictionary
            single_video_config: Config for single video mode (non-project)
            output_base_dir: Base directory for output (fallback)

        Returns:
            Tuple with the resolved path and whether it existed prior to the call.
        """
        if self.project_manager.project_path and not single_video_config:
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_context,
            )
        else:
            results_path = Path(output_base_dir)

        existed_before = results_path.exists()
        results_path.mkdir(parents=True, exist_ok=True)
        return results_path, existed_before

    def ensure_arena_polygon(
        self,
        arena_polygon_px: list | None,
        video_path: Path | str | None = None,
        video_context: VideoContext | None = None,
    ) -> list | None:
        """Ensure arena polygon exists, using full frame as fallback.

        Args:
            arena_polygon_px: Existing polygon or None
            video_path: Path to video (for extracting dimensions)

        Returns:
            Arena polygon (existing or full-frame fallback)
        """
        if arena_polygon_px:
            return arena_polygon_px

        if video_context is not None:
            return [
                [0, 0],
                [video_context.width, 0],
                [video_context.width, video_context.height],
                [0, video_context.height],
            ]

        if video_path is None:
            return None

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)

        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return [[0, 0], [width, 0], [width, height], [0, height]]
        finally:
            if cap is not None and cap.isOpened():
                cap.release()

    def load_trajectory_dataframe(
        self, trajectory_path: Path | str, experiment_id: str
    ) -> pd.DataFrame | None:
        """Load trajectory parquet file with error handling.

        Args:
            trajectory_path: Path to parquet file
            experiment_id: Experiment ID (for error messages)

        Returns:
            DataFrame or None if load failed
        """
        trajectory_path = (
            Path(trajectory_path) if isinstance(trajectory_path, str) else trajectory_path
        )
        if not trajectory_path.exists():
            # v2.2: Publish event instead of calling view directly
            if self.ui_event_bus is not None:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents
                self.ui_event_bus.publish(Event(
                    UIEvents.ERROR_OCCURRED,
                    {
                        'title': 'Erro de Processamento',
                        'message': f'Falha ao gerar arquivo de trajetória para {experiment_id}.',
                        'details': f'Arquivo não encontrado: {trajectory_path}'
                    }
                ))
            return None

        try:
            return pd.read_parquet(trajectory_path)
        except Exception as exc:
            log.error(
                "video_processing.trajectory_read_failed",
                path=trajectory_path,
                error=str(exc),
            )
            # v2.2: Publish event instead of calling view directly
            if self.ui_event_bus is not None:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents
                self.ui_event_bus.publish(Event(
                    UIEvents.ERROR_OCCURRED,
                    {
                        'title': 'Erro de Processamento',
                        'message': f'Falha ao ler arquivo de trajetória para {experiment_id}.',
                        'details': str(exc)
                    }
                ))
            return None

    def _setup_tracking_session(
        self,
        *,
        video_path: Path,
        results_dir: str,
        experiment_id: str,
        calibration_data: dict | None,
        recorder: Recorder,
        detector: Detector,
        video_context: VideoContext | None = None,
    ) -> tuple[
        cv2.VideoCapture | None,
        Recorder,
        ZoneData,
        list,
        Calibration | None,
        tuple | None,
    ]:
        """Set up tracking session: open video, prepare recorder, zones, and calibration.

        Args:
            video_path: Path to video file
            results_dir: Output directory for results
            experiment_id: Unique experiment identifier
            calibration_data: Optional calibration configuration
            recorder: Recorder instance or factory
            detector: Detector instance

        Returns:
            Tuple of (cap, recorder, zone_data, arena_polygon, calibration, pixel_per_cm_ratio)
        """
        # Task 2.2: Create new recorder instance from passed recorder (factory/prototype)
        # Using __class__ assumes recorder is an instance. If factory, might need .create()
        # Existing code used self.recorder.__class__, so we stick to that pattern for now
        # assuming 'recorder' passed is an instance serving as a prototype.
        session_recorder = recorder.__class__(settings_obj=self.settings)

        cap: cv2.VideoCapture | None
        if video_context is not None and video_context.cap is not None:
            cap = video_context.cap
            if cap.isOpened():
                video_context.reset()
            else:
                log.error("controller.tracking.video_context_closed", path=video_context.path)
                return None, None, None, None, None, None
        else:
            cap = cv2.VideoCapture(str(video_path))

        if cap is None or not cap.isOpened():
            log.error("controller.tracking.video_open_failed", path=video_path)
            return None, None, None, None, None, None

        if video_context is not None:
            frame_width = video_context.width
            frame_height = video_context.height
        else:
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        zone_data, arena_polygon = self._prepare_zone_data_for_tracking(
            frame_width, frame_height, detector
        )

        cal, pixel_per_cm_ratio = self._build_calibration_context(arena_polygon, calibration_data)

        session_recorder.start_recording(
            output_folder=results_dir,
            frame_width=frame_width,
            frame_height=frame_height,
            zones=zone_data,
            is_video_file=True,
            base_name=experiment_id,
            pixel_per_cm_ratio=pixel_per_cm_ratio,
            calibration=cal,
        )

        return cap, session_recorder, zone_data, arena_polygon, cal, pixel_per_cm_ratio

    def _reset_detector_tracking_state(self, detector: Detector) -> None:
        """Reset detector tracking state if supported."""
        if detector and hasattr(detector, "reset_tracking_state"):
            try:
                detector.reset_tracking_state()
            except Exception:  # pragma: no cover - defensive
                plugin_obj = getattr(detector, "plugin", None)
                plugin_class = getattr(plugin_obj, "__class__", type(detector))
                log.warning(
                    "controller.tracking.reset_tracker_failed",
                    plugin=plugin_class,
                    exc_info=True,
                )

    def _process_tracking_frame(
        self,
        *,
        frame,
        frame_num: int,
        analysis_interval_frames: int,
        cap: cv2.VideoCapture,
        recorder: Recorder,
        detector: Detector,
    ) -> tuple[list, int, bool]:
        """Process a single frame for tracking.

        Args:
            frame: Video frame
            frame_num: Current frame number
            analysis_interval_frames: Interval for running detection
            cap: Video capture object
            recorder: Recorder instance
            detector: Detector instance

        Returns:
            Tuple of (detections, detected_count_increment, should_process)
        """
        should_process = frame_num % analysis_interval_frames == 0
        detections = []
        detected_count_increment = 0

        if should_process:
            detections, _ = detector.detect(frame, project_type="pre-recorded")
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            recorder.write_detection_data(timestamp, frame_num, detections)

            if detections:
                detected_count_increment = 1

        return detections, detected_count_increment, should_process

    def _calculate_tracking_progress_stats(
        self,
        *,
        frame_num: int,
        processed_frames_count: int,
        detected_frames_count: int,
        start_time: float,
        cap: cv2.VideoCapture,
    ) -> tuple[float, dict]:
        """Calculate tracking progress statistics.

        Args:
            frame_num: Current frame number
            processed_frames_count: Number of processed frames
            detected_frames_count: Number of frames with detections
            start_time: Processing start time
            cap: Video capture object

        Returns:
            Tuple of (progress_fraction, stats_dict)
        """
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        progress_fraction = (frame_num + 1) / total_frames if total_frames > 0 else 0

        elapsed_time = time.time() - start_time
        if frame_num > 0 and progress_fraction > 0:
            estimated_total_time = elapsed_time / progress_fraction
            eta_time = estimated_total_time - elapsed_time
        else:
            eta_time = -1  # Unknown

        stats = {
            "total_frames": total_frames,
            "current_frame": frame_num + 1,
            "processed_frames": processed_frames_count,
            "detected_frames": detected_frames_count,
            "start_time": start_time,
            "elapsed": elapsed_time,
            "eta": eta_time,
            "percent": progress_fraction * 100,
        }

        return progress_fraction, stats

    def _finalize_tracking_session(
        self,
        *,
        recorder: any,
        cancel_requested: bool,
        experiment_id: str,
        trajectory_path: str,
        arena_polygon: list,
    ) -> tuple[bool, list]:
        """Finalize tracking session: stop recording, log results, publish events.

        Args:
            recorder: Recorder instance
            cancel_requested: Whether cancellation was requested
            experiment_id: Unique experiment identifier
            trajectory_path: Path to trajectory file
            arena_polygon: Arena polygon coordinates

        Returns:
            Tuple of (success, arena_polygon)
        """
        stop_reason = "Cancelled by user" if cancel_requested else None
        recorder.stop_recording(force_stop=cancel_requested, reason=stop_reason)

        if cancel_requested:
            log.info("controller.tracking.cancelled", video=experiment_id)
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": f"Cancelamento solicitado para {experiment_id}."},
                )
            else:
                self.ui_coordinator.set_status(
                    self.view, f"Cancelamento solicitado para {experiment_id}."
                )
            return False, arena_polygon

        log.info("controller.tracking.success", path=trajectory_path)
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Trajetória para {experiment_id} gerada."},
        )
        return True, arena_polygon

    def create_progress_callback(
        self, *, index: int, total_videos: int, experiment_id: str
    ) -> Callable:
        """Create progress callback for video processing.

        Phase 3: Moved from MainViewModel._make_progress_callback

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            experiment_id: Experiment identifier

        Returns:
            Callable that accepts progress stats dict
        """

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"

            # Use UICoordinator for UI updates
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, progress_fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", progress_fraction, step_status
            )

            # Publish task status event
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {
                    "payload": {
                        "index": index,
                        "total": total_videos,
                        "experiment_id": experiment_id,
                        "step": status_message,
                    }
                },
            )

            # Publish stats if available
            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats}
                    )

            # Note: processing_report requires access to processing_mode which is in MainViewModel
            # This will be handled by MainViewModel after service returns

            # Publish detections if available
            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_DETECTION_OVERLAY,
                        {"detections": detections, "report": None},
                    )

            # Publish frame for display
            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_FRAME,
                        {"frame": frame},
                    )

        return progress_callback

    def run_tracking_if_needed(
        self,
        video_path: Path | str,
        results_dir: str,
        experiment_id: str,
        detector: Detector | None = None,
        recorder: Recorder | None = None,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
        video_context: VideoContext | None = None,
    ) -> tuple[bool, list | None]:
        """Run tracking process if trajectory doesn't exist.

        Phase 3: Moved from MainViewModel._run_tracking_if_needed
        Phase 4 Refactoring: Simplified by extracting helper methods

        Args:
            video_path: Path to video file
            results_dir: Output directory for results
            experiment_id: Unique experiment identifier
            detector: Optional detector override (defaults to injected instance)
            recorder: Optional recorder override (defaults to injected instance)
            progress_callback: Optional progress update callback
            calibration_data: Optional calibration configuration
            analysis_interval_frames: Frame interval for analysis
            display_interval_frames: Frame interval for display
            video_context: Optional cached capture metadata to avoid reopening

        Returns:
            Tuple of (success: bool, arena_polygon: list | None)
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        arena_polygon = self.project_manager.get_zone_data().polygon

        detector = detector or self.detector
        recorder = recorder or self.recorder

        # Early return if trajectory already exists
        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            return True, arena_polygon

        if detector is None:
            log.error("controller.tracking.no_detector")
            return False, None

        if recorder is None:
            log.error("controller.tracking.no_recorder")
            return False, None

        log.info("controller.tracking.generating", video=experiment_id)
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Gerando trajetória para {experiment_id}..."},
        )

        cap = None
        session_recorder: Recorder | None = None
        try:
            # Setup tracking session
            setup_result = self._setup_tracking_session(
                video_path=video_path,
                results_dir=results_dir,
                experiment_id=experiment_id,
                calibration_data=calibration_data,
                recorder=recorder,
                detector=detector,
                video_context=video_context,
            )
            (
                cap,
                session_recorder,
                _zone_data,
                arena_polygon,
                _cal,
                _pixel_per_cm_ratio,
            ) = setup_result

            if cap is None:
                return False, None

            # Reset detector tracking state
            self._reset_detector_tracking_state(detector)

            # Process frames loop
            frame_num = 0
            processed_frames_count = 0
            detected_frames_count = 0
            start_time = time.time()
            cancel_requested = False

            log.info("controller.tracking.loop.start", video=experiment_id)

            while True:
                if self._tracking_cancelled(
                    experiment_id, frame_num, "controller.tracking.cancelled.event_detected"
                ):
                    cancel_requested = True
                    break

                # Optimized frame reading: use grab() for skipped frames (10-20x faster)
                # Only decode frames that will be processed (analysis_interval_frames)
                should_process = frame_num % analysis_interval_frames == 0

                if should_process:
                    # Decode this frame for processing
                    ret, frame = cap.read()
                else:
                    # Skip decoding - just advance video position (fast seek)
                    ret = cap.grab()
                    frame = None

                if not ret:
                    log.info("controller.tracking.loop.end_of_video", frame=frame_num)
                    break

                if self._tracking_cancelled(
                    experiment_id, frame_num, "controller.tracking.cancelled.after_read"
                ):
                    cancel_requested = True
                    break

                # Process frame (only if decoded)
                if should_process:
                    detections, detected_increment, was_processed = self._process_tracking_frame(
                        frame=frame,
                        frame_num=frame_num,
                        analysis_interval_frames=analysis_interval_frames,
                        cap=cap,
                        recorder=session_recorder,
                        detector=detector,
                    )

                    if was_processed:
                        processed_frames_count += 1
                        detected_frames_count += detected_increment

                    if self._tracking_cancelled(
                        experiment_id,
                        frame_num,
                        "controller.tracking.cancelled.before_progress",
                    ):
                        cancel_requested = True
                        break

                    # Update progress
                    if progress_callback:
                        progress_fraction, stats = self._calculate_tracking_progress_stats(
                            frame_num=frame_num,
                            processed_frames_count=processed_frames_count,
                            detected_frames_count=detected_frames_count,
                            start_time=start_time,
                            cap=cap,
                        )

                        detector.draw_overlay(frame, detections)
                        progress_callback(
                            progress_fraction,
                            "Gerando trajetória...",
                            frame,
                            stats,
                            detections=detections,
                        )

                frame_num += 1

            # Finalize session
            return self._finalize_tracking_session(
                recorder=session_recorder,
                cancel_requested=cancel_requested,
                experiment_id=experiment_id,
                trajectory_path=trajectory_path,
                arena_polygon=arena_polygon,
            )

        # Task 2.5: Specific exception handling instead of generic Exception
        except (FileNotFoundError, PermissionError) as e:
            # File system errors: missing video, no write permissions, etc.
            log.error(
                "controller.tracking.filesystem_error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Acesso ao Arquivo",
                    "message": (
                        f"Erro ao acessar arquivos para {experiment_id}:\n"
                        f"{e}\n\n"
                        f"Verifique:\n"
                        f"• O vídeo existe e está acessível\n"
                        f"• Você tem permissão de escrita no diretório\n"
                        f"• O disco não está cheio"
                    ),
                },
            )
            return False, None
        except OSError as e:
            # I/O errors: disk full, network drive disconnected, etc.
            log.error(
                "controller.tracking.io_error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de I/O",
                    "message": (
                        f"Erro de entrada/saída para {experiment_id}:\n"
                        f"{e}\n\n"
                        f"Possíveis causas:\n"
                        f"• Disco cheio\n"
                        f"• Dispositivo de rede desconectado\n"
                        f"• Hardware com problemas"
                    ),
                },
            )
            return False, None
        except cv2.error as e:
            # OpenCV errors: corrupted video, unsupported codec, etc.
            log.error(
                "controller.tracking.opencv_error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro no Vídeo",
                    "message": (
                        f"Erro ao processar vídeo {experiment_id}:\n"
                        f"{e}\n\n"
                        f"Possíveis causas:\n"
                        f"• Vídeo corrompido\n"
                        f"• Codec não suportado\n"
                        f"• Formato de vídeo inválido"
                    ),
                },
            )
            return False, None
        except (ValueError, TypeError) as e:
            # Data validation errors: invalid parameters, wrong data types
            log.error(
                "controller.tracking.validation_error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Validação",
                    "message": (
                        f"Dados inválidos para {experiment_id}:\n"
                        f"{e}\n\n"
                        f"Verifique a configuração do experimento."
                    ),
                },
            )
            return False, None
        except Exception as e:
            # Fallback for truly unexpected errors
            # Task 2.5: This should be rare - log with high severity
            log.critical(
                "controller.tracking.unexpected_error",
                video=experiment_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro Inesperado de Rastreamento",
                    "message": (
                        f"Erro inesperado ({type(e).__name__}) ao processar {experiment_id}:\n"
                        f"{e}\n\n"
                        f"Por favor, reporte este erro aos desenvolvedores."
                    ),
                },
            )
            return False, None
        finally:
            if cap is not None and cap.isOpened():
                cap.release()
            if video_context is not None:
                video_context.cap = None
            if session_recorder is not None and getattr(session_recorder, "is_recording", False):
                try:
                    session_recorder.stop_recording(force_stop=True, reason="Exception cleanup")
                except Exception:
                    log.warning(
                        "controller.tracking.recorder_cleanup_failed",
                        video=experiment_id,
                        exc_info=True,
                    )

    def _prepare_zone_data_for_tracking(
        self, frame_width: int, frame_height: int, detector: Detector | None = None
    ) -> tuple[ZoneData, list[list[int]]]:
        """Ensure zone data is ready for tracking and inform plugins.

        Phase 3: Moved from MainViewModel._prepare_zone_data_for_tracking
        """
        detector = detector or self.detector
        if detector is None:
            raise RuntimeError("Detector not available for zone preparation")

        zone_data = self.project_manager.get_zone_data()
        if not zone_data.polygon:
            log.warning("controller.tracking.no_arena_defined.using_default")
            zone_data.polygon = [
                [0, 0],
                [frame_width, 0],
                [frame_width, frame_height],
                [0, frame_height],
            ]

        arena_polygon = zone_data.polygon

        detector.set_zones(zone_data, frame_width, frame_height)

        if detector:
            has_aquarium = bool(zone_data and zone_data.polygon)
            detector.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.tracking.aquarium_status",
                defined=has_aquarium,
                plugin=detector.plugin.get_name(),
            )

        return zone_data, arena_polygon

    def _build_calibration_context(
        self,
        arena_polygon: list[list[int]] | list | None,
        calibration_data: dict | None,
    ) -> tuple[Calibration | None, tuple[float, float] | None]:
        """Calculate calibration and pixel/cm ratio for tracking outputs.

        Phase 3: Moved from MainViewModel._build_calibration_context
        """
        pixel_per_cm_ratio = None
        cal = None

        calibration_source = calibration_data or (
            self.project_manager.project_data.get("calibration")
            if self.project_manager and self.project_manager.project_data
            else None
        )

        if calibration_source:
            width_cm = calibration_source.get("aquarium_width_cm")
            height_cm = calibration_source.get("aquarium_height_cm")
            if width_cm and height_cm and arena_polygon:
                polygon_array = np.array(arena_polygon)
                cal = Calibration(polygon_array, width_cm, height_cm)
                pixel_per_cm_ratio = cal.pixel_per_cm_ratio

        return cal, pixel_per_cm_ratio

    def _tracking_cancelled(self, experiment_id: str, frame_num: int, log_key: str) -> bool:
        """Handle cancel-event checks during tracking loop.

        Phase 3: Moved from MainViewModel._tracking_cancelled
        """
        if not self.cancel_event.is_set():
            return False

        log.info(log_key, frame=frame_num, video=experiment_id)
        return True

    def _build_metadata_context(
        self,
        *,
        video_info: dict,
        single_video_config: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> dict | None:
        """Build metadata context for processing.

        Phase 3: Moved from MainViewModel._build_metadata_context
        """
        if single_video_config:
            return None

        metadata_context = dict(video_info.get("metadata") or {})
        try:
            derived_metadata = self.project_manager.derive_processing_metadata(
                experiment_id,
                video_path,
            )
            metadata_context.update(derived_metadata)
        except Exception:  # pragma: no cover - defensive fallback
            log.debug(
                "controller.processing.metadata_derive_failed",
                experiment=experiment_id,
                video_path=video_path,
            )

        return metadata_context

    def _schedule_analysis_metadata_update(self, metadata: dict) -> None:
        """Schedule analysis metadata update via event bus.

        Phase 3: Moved from MainViewModel._schedule_analysis_metadata_update
        """
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_METADATA, {"metadata": metadata}
            )

    def _notify_task_status_start(self, *, index: int, total: int, experiment_id: str) -> None:
        """Notify UI of task start via event bus.

        Phase 3: Moved from MainViewModel._notify_task_status_start
        """
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {"payload": {"index": index, "total": total, "experiment_id": experiment_id}},
            )

    def _snapshot_results_dir(self, results_path: Path) -> set[str]:
        """Capture the initial state of a results directory for later cleanup.

        Phase 3: Moved from MainViewModel._snapshot_results_dir
        """
        if not results_path.exists():
            return set()
        try:
            return {item.name for item in results_path.iterdir()}
        except Exception:  # pragma: no cover - best effort snapshot
            log.warning(
                "controller.results.snapshot_failed",
                results_dir=str(results_path),
                exc_info=True,
            )
            return set()

    def _cleanup_cancelled_results(self, results_dir: str, baseline_items: set[str]) -> None:
        """Remove artifacts created during a cancelled analysis run.

        Phase 3: Moved from MainViewModel._cleanup_cancelled_results
        """
        results_path = Path(results_dir)
        if not results_path.exists():
            return

        try:
            for item in list(results_path.iterdir()):
                if item.name in baseline_items:
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except FileNotFoundError:
                    continue
                except Exception:
                    log.warning(
                        "controller.results.cleanup_failed",
                        path=str(item),
                        exc_info=True,
                    )

            remaining = {child.name for child in results_path.iterdir()}
            if not baseline_items and not remaining:
                results_path.rmdir()
                log.info("controller.results.cleanup_removed_directory", path=str(results_path))
        except Exception:  # pragma: no cover - defensive cleanup
            log.warning(
                "controller.results.cleanup_unexpected_error",
                results_dir=str(results_dir),
                exc_info=True,
            )

    def _prepare_results_directory(self, results_dir: str) -> None:
        """Keep per-video results folders clean and archive older runs.

        Phase 3: Moved from MainViewModel._prepare_results_directory
        """
        path = Path(results_dir)
        path.mkdir(parents=True, exist_ok=True)

        existing_items = [item for item in path.iterdir() if item.name != "history"]
        if not existing_items:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        history_root = path / "history"
        archive_dir = history_root / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)

        for item in existing_items:
            target = archive_dir / item.name
            shutil.move(str(item), str(target))

        log.info(
            "controller.results.archive_previous_run",
            results_dir=str(path),
            archive_dir=str(archive_dir),
            item_count=len(existing_items),
        )

    def _compose_analysis_view_metadata(
        self,
        *,
        experiment_id: str,
        video_path: str,
        metadata_context: dict | None,
        single_video_config: dict | None,
        analysis_profile: dict | None,
    ) -> dict:
        """Compose metadata for analysis view display.

        Phase 3: Moved from MainViewModel._compose_analysis_view_metadata
        """
        combined: dict = {}

        entry = self.project_manager.find_video_entry(
            path=video_path,
            experiment_id=experiment_id,
        )
        if entry:
            combined.update(dict(entry.get("metadata") or {}))
            for key in ("group", "group_display_name", "day", "subject"):
                value = entry.get(key)
                if value not in (None, "") and key not in combined:
                    combined[key] = value

        if metadata_context:
            for key, value in metadata_context.items():
                if value in (None, ""):
                    continue
                combined[key] = value

        if single_video_config:
            mapping = {
                "group_display_name": "group_display_name",
                "group_label": "group_display_name",
                "group_name": "group_display_name",
                "group_id": "group",
                "group": "group",
                "day": "day",
                "day_id": "day",
                "subject": "subject",
                "subject_id": "subject",
                "animal": "subject",
                "cobaia": "subject",
            }
            for source_key, target_key in mapping.items():
                value = single_video_config.get(source_key)
                if value in (None, ""):
                    continue
                combined.setdefault(target_key, value)

        combined.setdefault("experiment_id", experiment_id)

        if analysis_profile and isinstance(analysis_profile, dict):
            profile_name = analysis_profile.get("name")
            if profile_name:
                combined["analysis_profile"] = profile_name
            track_ids = analysis_profile.get("track_ids")
            if track_ids:
                combined["analysis_profile_tracks"] = list(track_ids)

        return combined

    def _make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
    ):
        """Create progress callback for video processing.

        Phase 3: Moved from MainViewModel._make_progress_callback

        Note: This requires access to detector_service._publish_processing_mode
        which we don't have in the service. This will need special handling.
        """

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, progress_fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", progress_fraction, step_status
            )
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {
                    "payload": {
                        "index": index,
                        "total": total_videos,
                        "experiment_id": experiment_id,
                        "step": status_message,
                    }
                },
            )

            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats}
                    )

            # Note: processing_report requires detector_service which we don't have here
            # This will need to be handled by the caller
            processing_report = None  # TODO: Pass from caller if needed

            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_DETECTION_OVERLAY,
                        {"detections": detections, "report": processing_report},
                    )

            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_FRAME,
                        {"frame": frame},
                    )

        return progress_callback

    def _collect_params_from_single_video(self, config: dict, experiment_id: str):
        """Extract parameters from single video config.

        Phase 3: Moved from MainViewModel._collect_params_from_single_video
        """
        metadata = dict(config)
        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("video_name", experiment_id)
        if not metadata.get("group_id"):
            metadata["group_id"] = "single_video"

        return (
            metadata,
            config.get("aquarium_width_cm"),
            config.get("aquarium_height_cm"),
            config.get(
                "sharp_turn_threshold_deg_s",
                self.settings.video_processing.sharp_turn_threshold_deg_s,
            ),
            config.get(
                "freezing_velocity_threshold",
                self.settings.video_processing.freezing_velocity_threshold,
            ),
            config.get(
                "freezing_min_duration_s", self.settings.video_processing.freezing_min_duration_s
            ),
            config.get("smoothing_window_length", self.settings.trajectory_smoothing.window_length),
            config.get("smoothing_polyorder", self.settings.trajectory_smoothing.polyorder),
        )

    def _collect_params_from_project(
        self, metadata_context: dict | None, experiment_id: str, video_path: Path | str
    ):
        """Extract parameters from project data.

        Phase 3: Moved from MainViewModel._collect_params_from_project
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration", {})

        metadata = dict(metadata_context or {})
        csv_metadata = self.project_manager.get_metadata_for_experiment(experiment_id)
        if csv_metadata:
            metadata.update(csv_metadata)
        if not metadata:
            metadata = self.project_manager.derive_processing_metadata(experiment_id, video_path)
            log.info(
                "controller.processing.metadata_fallback",
                experiment_id=experiment_id,
                fields=list(metadata.keys()),
            )

        return (
            metadata,
            calibration.get("aquarium_width_cm"),
            calibration.get("aquarium_height_cm"),
            self.settings.video_processing.sharp_turn_threshold_deg_s,
            self.settings.video_processing.freezing_velocity_threshold,
            self.settings.video_processing.freezing_min_duration_s,
            self.settings.trajectory_smoothing.window_length,
            self.settings.trajectory_smoothing.polyorder,
        )

    def _collect_analysis_parameters(
        self,
        *,
        single_video_config: dict | None,
        metadata_context: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> tuple[dict, float | None, float | None, float, float, float, int, int]:
        """Collect analysis parameters from config or project.

        Phase 3: Moved from MainViewModel._collect_analysis_parameters
        """
        if single_video_config:
            return self._collect_params_from_single_video(single_video_config, experiment_id)
        else:
            return self._collect_params_from_project(metadata_context, experiment_id, video_path)

    def _prepare_analysis_calibration_context(
        self,
        *,
        arena_polygon_px: list,
        width_cm: float | None,
        height_cm: float | None,
        zone_data: ZoneData,
    ) -> tuple[
        Calibration | None,
        list[tuple[float, float]] | None,
        list[ROI],
        dict[str, tuple[int, int, int]],
        float | None,
        float | None,
    ]:
        """Prepare calibration context for analysis.

        Phase 3: Moved from MainViewModel._prepare_calibration_context
        (renamed to avoid conflict with tracking version)
        """
        if not all([width_cm, height_cm, arena_polygon_px]):
            return None, None, [], {}, None, None

        assert width_cm is not None
        assert height_cm is not None

        cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
        _video_width_px, _video_height_px = cal.target_dims_px
        pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio

        warped_points = cal.transform_points(arena_polygon_px)
        arena_polygon_warped = [(float(point[0]), float(point[1])) for point in warped_points]
        rois: list[ROI] = []
        for i, polygon in enumerate(zone_data.roi_polygons):
            warped_points = cal.transform_points(polygon)
            roi_points_px = [(float(x), float(y)) for x, y in warped_points]
            roi_name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"
            rois.append(
                ROI(
                    name=roi_name,
                    geometry=Polygon(roi_points_px),
                    coordinate_space="px",
                )
            )

        roi_colors = {
            (zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"): color
            for i, color in enumerate(zone_data.roi_colors)
        }

        return cal, arena_polygon_warped, rois, roi_colors, pixelcm_x, pixelcm_y

    def _generate_reports_for_video(
        self,
        *,
        reporter: Reporter,
        experiment_id: str,
        results_dir: str,
        progress_callback,
        cancel_event: threading.Event | None = None,
    ) -> tuple[str, str, str] | None:
        """Generate analysis reports for video.

        Phase 3: Moved from MainViewModel._generate_reports_for_video
        """
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.skipped",
                video=experiment_id,
                reason="cancelled",
            )
            return None

        summary_parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
        summary_excel_path = os.path.join(results_dir, f"{experiment_id}_summary.xlsx")
        report_docx_path = os.path.join(results_dir, f"{experiment_id}_report.docx")

        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.skipped",
                video=experiment_id,
                reason="cancelled_before_write",
            )
            return None

        reporter.export_summary_data(summary_parquet_path, format="parquet")
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.partial_skip",
                video=experiment_id,
                reason="cancelled_after_parquet",
            )
            return None
        reporter.export_summary_data(summary_excel_path, format="excel")
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.partial_skip",
                video=experiment_id,
                reason="cancelled_after_excel",
            )
            return None
        reporter.export_individual_report_step_by_step(report_docx_path, progress_callback)

        return summary_parquet_path, summary_excel_path, report_docx_path

    def _filter_trajectory_by_tracks(
        self,
        *,
        trajectory_df: pd.DataFrame,
        analysis_profile: dict | None,
        experiment_id: str,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Filter trajectory dataframe by requested track IDs from analysis profile.

        Args:
            trajectory_df: Full trajectory dataframe
            analysis_profile: Analysis profile configuration
            experiment_id: Experiment identifier (for logging)

        Returns:
            Tuple of (filtered_df, resolved_track_ids)
        """
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        requested_track_ids_raw = profile_dict.get("track_ids", [])

        if isinstance(requested_track_ids_raw, (list, tuple, set)):
            requested_track_ids = list(requested_track_ids_raw)
        elif requested_track_ids_raw in (None, ""):
            requested_track_ids = []
        else:
            requested_track_ids = [requested_track_ids_raw]

        filtered_df = trajectory_df
        resolved_track_ids: list[str] = []

        if "track_id" in trajectory_df.columns:
            resolved_track_ids = sorted(
                {str(track) for track in trajectory_df["track_id"].dropna().unique().tolist()}
            )

            if requested_track_ids:
                requested_str = {
                    str(track).strip() for track in requested_track_ids if track not in (None, "")
                }

                mask = trajectory_df["track_id"].astype(str).isin(requested_str)
                narrowed = trajectory_df[mask]
                if narrowed.empty:
                    log.warning(
                        "controller.analysis.profile_track_miss",
                        video=experiment_id,
                        requested=list(requested_str),
                    )
                else:
                    filtered_df = narrowed
                    resolved_track_ids = sorted(requested_str)
        elif requested_track_ids:
            log.warning(
                "controller.analysis.profile_track_column_missing",
                video=experiment_id,
            )

        return filtered_df, resolved_track_ids

    def _enrich_metadata_with_profile(
        self,
        *,
        metadata: dict,
        analysis_profile: dict | None,
    ) -> dict:
        """Enrich metadata with analysis profile information.

        Args:
            metadata: Base metadata dictionary
            analysis_profile: Analysis profile configuration

        Returns:
            Enriched metadata dictionary
        """
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}

        if isinstance(profile_dict, dict):
            profile_name = profile_dict.get("name")
            if profile_name and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile", profile_name)
            track_list = profile_dict.get("track_ids")
            if track_list and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile_tracks", list(track_list))

        return metadata

    def _create_reporter_instance(
        self,
        *,
        filtered_df: pd.DataFrame,
        metadata: dict,
        calibration: Calibration,
        arena_polygon_warped: list,
        rois: list,
        roi_colors: dict,
        video_path: str,
        pixelcm_x: float,
        pixelcm_y: float,
        sharp_turn_threshold: float,
        freezing_threshold: float,
        freezing_duration: float,
        smoothing_window: int,
        smoothing_polyorder: int,
    ) -> Reporter:
        """Create Reporter instance with all required parameters.

        Args:
            filtered_df: Filtered trajectory dataframe
            metadata: Enriched metadata
            calibration: Calibration instance
            arena_polygon_warped: Warped arena polygon coordinates
            rois: List of ROI objects
            roi_colors: ROI color mapping
            video_path: Path to video file
            pixelcm_x: Pixels per cm ratio (X axis)
            pixelcm_y: Pixels per cm ratio (Y axis)
            sharp_turn_threshold: Sharp turn detection threshold
            freezing_threshold: Freezing detection threshold
            freezing_duration: Minimum freezing duration
            smoothing_window: Trajectory smoothing window length
            smoothing_polyorder: Trajectory smoothing polynomial order

        Returns:
            Reporter instance
        """
        return Reporter(
            trajectory_df=filtered_df,
            metadata=metadata,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=calibration.target_dims_px[1],
            arena_polygon_px=arena_polygon_warped,
            rois=rois,
            fps=self.settings.video_processing.fps,
            roi_colors=roi_colors,
            video_path=video_path,
            calibration=calibration,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_threshold,
            freezing_duration=freezing_duration,
            smoothing_window_length=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )

    def _analyze_social_proximity(
        self,
        *,
        filtered_df: pd.DataFrame,
        analysis_profile: dict | None,
        pixelcm_x: float,
        pixelcm_y: float,
        experiment_id: str,
    ) -> dict | None:
        """Analyze social proximity if enabled in analysis profile.

        Args:
            filtered_df: Filtered trajectory dataframe
            analysis_profile: Analysis profile configuration
            pixelcm_x: Pixels per cm ratio (X axis)
            pixelcm_y: Pixels per cm ratio (Y axis)
            experiment_id: Experiment identifier (for logging)

        Returns:
            Social proximity summary dict or None if disabled/failed
        """
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        raw_social_config = profile_dict.get("social") if isinstance(profile_dict, dict) else {}
        social_config = raw_social_config if isinstance(raw_social_config, dict) else {}
        social_enabled = bool(social_config.get("enabled"))

        if not social_enabled:
            return None

        if pixelcm_x is None or pixelcm_y is None:
            return None

        if "track_id" not in filtered_df.columns:
            return None

        active_tracks = filtered_df["track_id"].dropna().unique().tolist()
        if len(active_tracks) <= 1:
            return None

        try:
            radius_cm = float(social_config.get("radius_cm", 5.0))
        except (TypeError, ValueError):
            radius_cm = 5.0

        try:
            return ROIAnalyzer.analyze_social_proximity(
                filtered_df,
                radius_cm,
                pixelcm_x,
                pixelcm_y,
            )
        except Exception:  # pragma: no cover - defensive
            log.warning(
                "controller.analysis.social_failed",
                video=experiment_id,
                exc_info=True,
            )
            return None

    def _register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
    ) -> None:
        """Register processing outputs with project manager.

        Phase 3: Moved from MainViewModel._register_project_outputs

        Note: This method calls self.refresh_project_views which is a MainViewModel method.
        This will need to be handled via callback or event.
        """
        self.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )
        # TODO: refresh_project_views needs to be called by MainViewModel
        # Could emit an event here instead

    def _run_analysis_pipeline(
        self,
        *,
        experiment_id: str,
        video_path: str,
        results_dir: str,
        arena_polygon_px: list | None,
        metadata_context: dict | None,
        single_video_config: dict | None,
        progress_callback,
        analysis_profile: dict | None,
        video_context: VideoContext | None = None,
    ) -> bool:
        """Run complete analysis pipeline for a tracked video.

        Phase 3: Moved from MainViewModel._run_analysis_pipeline
        Phase 4 Refactoring: Simplified by extracting helper methods

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to source video
            results_dir: Directory containing tracking outputs
            arena_polygon_px: Arena polygon in pixels (optional)
            metadata_context: Additional metadata for reports
            single_video_config: Overrides for single-video mode
            progress_callback: Progress reporting callable
            analysis_profile: Profile describing analysis parameters
            video_context: Optional cached capture metadata
        """
        # Load trajectory data
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_df = self.load_trajectory_dataframe(trajectory_path, experiment_id)
        if trajectory_df is None:
            return False

        if self.cancel_event.is_set():
            log.info("controller.analysis.cancelled_before_pipeline", video=experiment_id)
            return False

        # Filter trajectory by requested tracks
        filtered_df, resolved_track_ids = self._filter_trajectory_by_tracks(
            trajectory_df=trajectory_df,
            analysis_profile=analysis_profile,
            experiment_id=experiment_id,
        )

        # Collect analysis parameters
        (
            metadata,
            width_cm,
            height_cm,
            sharp_turn_threshold,
            freezing_threshold,
            freezing_duration,
            smoothing_window,
            smoothing_polyorder,
        ) = self._collect_analysis_parameters(
            single_video_config=single_video_config,
            metadata_context=metadata_context,
            experiment_id=experiment_id,
            video_path=video_path,
        )

        # Enrich metadata with profile information
        metadata = self._enrich_metadata_with_profile(
            metadata=metadata,
            analysis_profile=analysis_profile,
        )

        # Validate calibration data
        zone_data = self.project_manager.get_zone_data()
        arena_polygon_px = self.ensure_arena_polygon(
            arena_polygon_px,
            video_path,
            video_context=video_context,
        )
        if not all([width_cm, height_cm, arena_polygon_px]):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Processamento",
                    "message": "Dados de calibração incompletos.",
                },
            )
            return False

        assert arena_polygon_px is not None

        # Prepare calibration context
        (
            calibration,
            arena_polygon_warped,
            rois,
            roi_colors,
            pixelcm_x,
            pixelcm_y,
        ) = self._prepare_analysis_calibration_context(
            arena_polygon_px=arena_polygon_px,
            width_cm=width_cm,
            height_cm=height_cm,
            zone_data=zone_data,
        )

        if (
            not calibration
            or arena_polygon_warped is None
            or pixelcm_x is None
            or pixelcm_y is None
        ):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Processamento",
                    "message": "Falha ao preparar dados de calibração.",
                },
            )
            return False

        # Create Reporter instance
        reporter = self._create_reporter_instance(
            filtered_df=filtered_df,
            metadata=metadata,
            calibration=calibration,
            arena_polygon_warped=arena_polygon_warped,
            rois=rois,
            roi_colors=roi_colors,
            video_path=video_path,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_threshold,
            freezing_duration=freezing_duration,
            smoothing_window=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )

        if self.cancel_event.is_set():
            log.info("controller.analysis.cancelled_before_reports", video=experiment_id)
            return False

        # Generate reports
        generated_outputs = self._generate_reports_for_video(
            reporter=reporter,
            experiment_id=experiment_id,
            results_dir=results_dir,
            progress_callback=progress_callback,
            cancel_event=self.cancel_event,
        )

        if generated_outputs is None:
            return False

        summary_parquet_path, summary_excel_path, report_docx_path = generated_outputs

        # Analyze social proximity
        social_summary = self._analyze_social_proximity(
            filtered_df=filtered_df,
            analysis_profile=analysis_profile,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            experiment_id=experiment_id,
        )

        # Publish social summary
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        profile_name = profile_dict.get("name", "default")
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_SOCIAL_SUMMARY,
            {"profile": profile_name, "stats": social_summary, "tracks": resolved_track_ids},
        )

        # Register outputs
        self._register_project_outputs(
            video_path=video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet_path,
            summary_excel=summary_excel_path,
            report_path=report_docx_path,
        )

        return True

    def process_frame_source(
        self,
        *,
        frame_source,  # FrameSource type hint removed due to circular import
        output_dir: str,
        experiment_id: str,
        detector: Detector,
        recorder: Recorder,
        single_video_config: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
        record_video: bool = True,
    ) -> bool:
        """
        Process frames from a FrameSource (live camera or video file).

        This method provides a unified interface for processing both
        video files and live camera streams.

        Args:
            frame_source: FrameSource instance (VideoFileSource, LiveStreamSource, or Camera)
            output_dir: Output directory for results
            experiment_id: Unique experiment identifier
            detector: Detector instance
            recorder: Recorder instance
            single_video_config: Optional configuration dict for single video mode
            analysis_interval_frames: Frame interval for running detection/tracking
            display_interval_frames: Frame interval for updating UI
            record_video: Whether to save video with overlay

        Returns:
            True if processing succeeded, False otherwise
        """
        log.info(
            "video_processing_service.process_frame_source.start",
            experiment_id=experiment_id,
            output_dir=output_dir,
            is_live=frame_source.get_properties().get("is_live_stream", False),
        )

        # Use the existing run_tracking_if_needed which now should support FrameSource
        # We'll pass a pseudo video_path for compatibility
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Run tracking (will be adapted to use frame_source internally)
        success, arena_polygon = self.run_tracking_if_needed(
            video_path=frame_source,  # Pass frame_source directly
            results_dir=str(output_path),
            experiment_id=experiment_id,
            detector=detector,
            recorder=recorder,
            progress_callback=None,
            calibration_data=single_video_config,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
        )

        if not success:
            log.warning(
                "video_processing_service.process_frame_source.tracking_failed",
                experiment_id=experiment_id,
            )
            return False

        # Run analysis if tracking succeeded
        if single_video_config:
            analysis_success = self._run_analysis_pipeline(
                experiment_id=experiment_id,
                video_path="live_stream",  # Placeholder for live streams
                results_dir=str(output_path),
                arena_polygon_px=arena_polygon,
                metadata_context=single_video_config,
                single_video_config=single_video_config,
                progress_callback=None,
                analysis_profile=None,
            )

            return analysis_success

        return True

    def process_single_video(
        self,
        *,
        index: int,
        total_videos: int,
        video_info: dict,
        single_video_config: dict | None,
        analysis_interval_frames: int,
        display_interval_frames: int,
        output_base_dir: str,
        experiment_id: str,
        metadata_context: dict | None,
        analysis_profile: dict | None,
        detector: Detector,
        recorder: Recorder,
    ) -> tuple[bool, str | None]:
        """Process a single video: tracking + analysis.

        Phase 3: Moved from MainViewModel._process_single_video_impl

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            video_info: Video metadata dict
            single_video_config: Config for single video mode
            analysis_interval_frames: Frame interval for analysis
            display_interval_frames: Frame interval for display
            output_base_dir: Base output directory
            experiment_id: Unique experiment identifier
            metadata_context: Optional metadata dictionary
            analysis_profile: Optional analysis profile configuration
            detector: Detector instance
            recorder: Recorder instance

        Returns:
            Tuple of (success: bool, results_dir: str | None)
        """
        video_context: VideoContext | None = None
        try:
            video_path = video_info.get("path")
            if not video_path:
                return False, None

            video_context = self._create_video_context(video_path)
            if video_context is None:
                log.error(
                    "video_processing.context_init_failed",
                    video_path=video_path,
                )
                return False, None

            if metadata_context is None:
                metadata_context = self._build_metadata_context(
                    video_info=video_info,
                    single_video_config=single_video_config,
                    experiment_id=experiment_id,
                    video_path=video_path,
                )

            analysis_view_metadata = self._compose_analysis_view_metadata(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                analysis_profile=analysis_profile,
            )
            self._schedule_analysis_metadata_update(analysis_view_metadata)
            self._notify_task_status_start(
                index=index,
                total=total_videos,
                experiment_id=experiment_id,
            )

            self.project_manager.set_active_zone_video(video_path)
            progress_callback = self._make_progress_callback(
                index=index,
                total_videos=total_videos,
                experiment_id=experiment_id,
            )

            self.display_initial_frame(video_path, frame=video_context.first_frame)

            results_path, _ = self.resolve_results_path(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                output_base_dir=output_base_dir,
            )
            results_dir = str(results_path)

            # Prepare results directory (archive previous runs if needed)
            self._prepare_results_directory(results_dir)

            baseline_items = self._snapshot_results_dir(results_path)

            tracking_success, arena_polygon_px = self.run_tracking_if_needed(
                video_path,
                results_dir,
                experiment_id,
                detector,
                recorder,
                progress_callback,
                calibration_data=single_video_config,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                video_context=video_context,
            )

            if self.cancel_event.is_set():
                self._cleanup_cancelled_results(results_dir, baseline_items)
                return False, results_dir

            if not tracking_success:
                if self.cancel_event.is_set():
                    self._cleanup_cancelled_results(results_dir, baseline_items)
                return False, results_dir

            analysis_success = self._run_analysis_pipeline(
                experiment_id=experiment_id,
                video_path=video_path,
                results_dir=results_dir,
                arena_polygon_px=arena_polygon_px,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                progress_callback=progress_callback,
                analysis_profile=analysis_profile,
                video_context=video_context,
            )

            if self.cancel_event.is_set():
                self._cleanup_cancelled_results(results_dir, baseline_items)
                return False, results_dir

            return analysis_success, results_dir
        finally:
            # Release frame references
            if detector and hasattr(detector, "clear_cache"):
                detector.clear_cache()
            if video_context is not None:
                video_context.release()
