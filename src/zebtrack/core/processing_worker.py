"""
ProcessingWorker: Dedicated multiprocessing worker for video processing.

This module implements the background processing logic for video analysis,
bypassing the GIL by using multiprocessing.Process.

Architecture:
    - ProcessingWorker: A wrapper class that manages the process and callbacks.
    - _WorkerProcess: The actual multiprocessing.Process subclass.
    - ProcessingContext: Configuration passed from Coordinator.
    - ProcessingCallbacks: Callbacks to update UI/State in main process.
"""

from __future__ import annotations

import multiprocessing
import os
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import cv2
import time
import structlog

from zebtrack.core.detector import Detector, ZoneData
from zebtrack.io.recorder import Recorder

# Settings is used at runtime in WorkerConfig
if TYPE_CHECKING:
    pass

log = structlog.get_logger()


@dataclass
class ProcessingContext:
    """Context for processing, passed from Coordinator."""

    videos_to_process: list[dict]
    output_base_dir: str
    cancel_event: threading.Event
    settings: Any  # Settings object
    single_video_config: dict | None = None
    zone_data: Any = None  # ZoneData object or dict
    analysis_interval_frames: int = 10
    display_interval_frames: int = 10
    process_single_video_func: Callable | None = None
    apply_project_settings_func: Callable | None = None
    determine_intervals_func: Callable | None = None
    retry_strategy: str = "stop"


@dataclass
class ProcessingCallbacks:
    """Callbacks for processing events."""

    on_started: Callable[[], None]
    on_progress: Callable[[int, int, str, float, str, dict | None], None]  # index, total, experiment_id, fraction, message, stats
    on_frame_processed: Callable[[Any, Any, Any], None]
    on_video_completed: Callable[[int, int, str, bool], None]
    on_error: Callable[[Exception, str], None]
    on_completed: Callable[[bool, str, dict | None], None]
    on_fatal_error: Callable[[Exception, str, dict], None]


@dataclass
class WorkerConfig:
    """Configuration passed to the worker process."""

    settings: Any
    output_base_dir: str
    tasks: list[dict]  # List of video info dicts
    single_video_mode: bool = False
    analysis_interval_frames: int = 10
    display_interval_frames: int = 10
    model_path: str = ""
    model_type: str = "yolo"  # 'yolo' or 'openvino'
    zone_data: dict | None = None  # serialized ZoneData


class ProcessingWorker:
    """
    Wrapper class that manages the worker process and bridges
    multiprocessing queues to thread-safe callbacks.
    """

    def __init__(self, context: ProcessingContext, callbacks: ProcessingCallbacks):
        self.context = context
        self.callbacks = callbacks
        self.result_queue = multiprocessing.Queue()
        self.command_queue = multiprocessing.Queue()
        self.process = None
        self._monitor_thread = None

    @property
    def is_running(self) -> bool:
        """Check if the worker is currently running."""
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    def start_in_thread(self) -> threading.Thread:
        """Start the worker process and the monitoring thread."""
        if self.is_running:
            return self._monitor_thread

        # Prepare zone data dictionary
        z_data = self.context.zone_data
        z_dict = None
        if z_data:
            if isinstance(z_data, dict):
                z_dict = z_data
            else:
                # Serialize ZoneData object
                z_dict = {
                    "polygon": getattr(z_data, "polygon", []),
                    "roi_polygons": getattr(z_data, "roi_polygons", []),
                    "roi_names": getattr(z_data, "roi_names", []),
                    "roi_colors": getattr(z_data, "roi_colors", []),
                }
            # DEBUG: Log serialized zone data
            log.info(
                "worker.zone_data_serialized",
                polygon_points=len(z_dict.get("polygon", [])) if z_dict else 0,
                has_polygon=bool(z_dict and z_dict.get("polygon")),
                polygon_sample=z_dict.get("polygon", [])[:3] if z_dict and z_dict.get("polygon") else "empty",
            )

        # Create WorkerConfig
        config = WorkerConfig(
            settings=self.context.settings,
            output_base_dir=self.context.output_base_dir,
            tasks=self.context.videos_to_process,
            single_video_mode=bool(self.context.single_video_config),
            analysis_interval_frames=self.context.analysis_interval_frames,
            display_interval_frames=self.context.display_interval_frames,
            zone_data=z_dict,
            # Model path logic inside _WorkerProcess will handle defaults
        )

        self.process = _WorkerProcess(config, self.result_queue, self.command_queue)
        self.process.start()

        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="ProcessingMonitor")
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        return self._monitor_thread

    def cancel(self, timeout: float | None = None) -> bool:
        """Cancel processing."""
        self.context.cancel_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=timeout)
            return not self._monitor_thread.is_alive()
        return True

    def _monitor_loop(self):  # noqa: C901
        """Monitor results from the worker process."""
        self.callbacks.on_started()

        cancel_sent = False  # Track if we've sent cancel command

        # Log cancel_event details for debugging
        log.info(
            "monitor_loop.started",
            cancel_event_id=id(self.context.cancel_event),
            is_set=self.context.cancel_event.is_set(),
        )

        while True:
            # Forward cancellation (send only once to avoid flooding queue)
            if self.context.cancel_event.is_set() and not cancel_sent:
                log.info(
                    "monitor_loop.cancel_detected",
                    cancel_event_id=id(self.context.cancel_event),
                )
                self.command_queue.put("cancel")
                cancel_sent = True
                log.info("monitor_loop.cancel_command_sent")

            try:
                # Poll queue
                try:
                    msg = self.result_queue.get(timeout=0.1)
                except queue.Empty:
                    if self.process and not self.process.is_alive():
                        break
                    continue

                msg_type = msg.get("type")

                if msg_type == "progress":
                    if self.callbacks.on_progress:
                        self.callbacks.on_progress(
                            msg.get("index", 0),
                            msg.get("total", 1),
                            msg.get("experiment_id", ""),
                            msg["fraction"],
                            msg["message"],
                            msg.get("stats")
                        )

                elif msg_type == "frame":
                    # Pass frame to callback
                    if self.callbacks.on_frame_processed:
                        self.callbacks.on_frame_processed(
                            msg["frame"],
                            msg.get("detections"),
                            msg.get("info"),
                        )

                elif msg_type == "video_completed":
                    if self.callbacks.on_video_completed:
                        self.callbacks.on_video_completed(
                            msg["index"],
                            0,  # Total not always passed back in this msg
                            msg["experiment_id"],
                            msg["success"],
                        )

                elif msg_type == "completed":
                    if self.callbacks.on_completed:
                        self.callbacks.on_completed(
                            msg.get("cancelled", False),
                            self.context.output_base_dir,
                            msg.get("summary"),
                        )
                    break

                elif msg_type == "error":
                    if self.callbacks.on_error:
                        self.callbacks.on_error(
                            Exception(msg["error"]), msg.get("experiment_id", "unknown")
                        )

                elif msg_type == "fatal_error":
                    error = Exception(msg["error"])
                    context_str = "Fatal Worker Error"
                    info = {"affected_videos": []}

                    if self.callbacks.on_fatal_error:
                        self.callbacks.on_fatal_error(error, context_str, info)
                    elif self.callbacks.on_error:
                        # Fallback to normal error callback
                        self.callbacks.on_error(error, context_str)
                    break

            except Exception as e:
                log.error("worker.monitor_loop_error", error=str(e))
                break

        if self.process:
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                log.warning("worker.process.force_terminate")
                self.process.terminate()


class _WorkerProcess(multiprocessing.Process):
    """
    Worker process that runs video processing in a separate memory space.
    """

    def __init__(
        self,
        config: WorkerConfig,
        result_queue: multiprocessing.Queue,
        command_queue: multiprocessing.Queue,
    ):
        super().__init__(name="ZebTrack-ProcessingWorker")
        self.config = config
        self.result_queue = result_queue
        self.command_queue = command_queue
        self._cancel_requested = False

    def run(self):
        """Main entry point for the worker process."""
        # Configure logging for worker process (multiprocessing doesn't inherit parent config)
        # Use a separate log file for the worker to avoid file lock issues on Windows
        from zebtrack.logging_config import configure_logging
        configure_logging(log_file="analysis_worker.log")

        import os
        import traceback

        log.info("worker.process.started", pid=os.getpid())

        try:
            # 1. Initialize dependencies
            detector = self._initialize_detector()

            # 2. Process tasks
            total_videos = len(self.config.tasks)

            for index, video_info in enumerate(self.config.tasks):
                if self._check_cancellation():
                    break

                video_path = video_info.get("path")
                experiment_id = (
                    os.path.splitext(os.path.basename(video_path))[0]
                    if isinstance(video_path, str) and video_path
                    else f"video_{index + 1}"
                )

                log.info(
                    "worker.process.video_start",
                    index=index,
                    experiment_id=experiment_id,
                )

                self._send_progress(
                    index, total_videos, 0.0, f"Iniciando: {experiment_id}", experiment_id
                )

                try:
                    success = self._process_single_video(
                        index=index,
                        total_videos=total_videos,
                        video_path=video_path,
                        experiment_id=experiment_id,
                        detector=detector,
                        video_metadata=video_info,
                    )

                    self.result_queue.put(
                        {
                            "type": "video_completed",
                            "index": index,
                            "experiment_id": experiment_id,
                            "success": success,
                        }
                    )

                except Exception as e:
                    log.error(
                        "worker.process.video_error",
                        experiment_id=experiment_id,
                        error=str(e),
                        exc_info=True,
                    )
                    self.result_queue.put(
                        {
                            "type": "error",
                            "experiment_id": experiment_id,
                            "error": str(e),
                            "traceback": traceback.format_exc(),
                        }
                    )

                # Clean up after video
                import gc

                gc.collect()

        except Exception as e:
            log.critical("worker.process.fatal_error", error=str(e), exc_info=True)
            self.result_queue.put(
                {"type": "fatal_error", "error": str(e), "traceback": traceback.format_exc()}
            )
        finally:
            self.result_queue.put({"type": "completed", "cancelled": self._cancel_requested})
            log.info("worker.process.finished", pid=os.getpid())

    def _initialize_detector(self) -> Detector:
        """Initialize the detector with the appropriate plugin."""
        log.info("worker.detector.initializing", type=self.config.model_type)

        settings = self.config.settings

        # CRITICAL: Sync processing_interval from analysis_interval_frames
        # This ensures the Kalman filter dt is correctly set for sparse frame processing
        if hasattr(settings, "video_processing"):
            runtime_interval = self.config.analysis_interval_frames
            config_interval = getattr(settings.video_processing, "processing_interval", 1)
            if runtime_interval != config_interval:
                log.info(
                    "worker.detector.sync_processing_interval",
                    config_interval=config_interval,
                    runtime_interval=runtime_interval,
                    message="Updating settings.video_processing.processing_interval from UI value",
                )
                # Update the settings to match the runtime value
                # This affects Kalman filter dt in ByteTracker
                settings.video_processing.processing_interval = runtime_interval

        # Resolve model path (use settings if not provided in config)
        model_path = self.config.model_path
        if not model_path:
            # Fallback to settings
            model_path = settings.yolo_model.path

        if self.config.model_type == "openvino":
            from zebtrack.plugins.openvino_detector import OpenVINOPlugin

            plugin = OpenVINOPlugin(model_path=model_path, settings_obj=settings)
        else:
            from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin

            plugin = UltralyticsDetectorPlugin(model_path=model_path, settings_obj=settings)

        # Initialize Detector
        width = settings.camera.desired_width
        height = settings.camera.desired_height
        detector = Detector(
            plugin=plugin, base_width=width, base_height=height, settings_obj=settings
        )

        # CRITICAL: Propagate single_subject_mode from settings
        # This ensures SingleSubjectTracker is used when configured, preventing ID switches
        single_mode = False

        # Check animals_per_aquarium first
        if hasattr(settings, "video_processing") and hasattr(settings.video_processing, "animals_per_aquarium"):
             if settings.video_processing.animals_per_aquarium == 1:
                 single_mode = True

        # Check legacy/explicit override
        if hasattr(settings, "tracking") and hasattr(settings.tracking, "use_single_subject_tracker"):
             if settings.tracking.use_single_subject_tracker:
                 single_mode = True

        detector.set_single_subject_mode(single_mode)
        log.info("worker.detector.single_subject_mode_set", enabled=single_mode)

        # Restore ZoneData
        if self.config.zone_data:
            zd = ZoneData()
            zd.polygon = self.config.zone_data.get("polygon", [])
            zd.roi_polygons = self.config.zone_data.get("roi_polygons", [])
            zd.roi_names = self.config.zone_data.get("roi_names", [])
            zd.roi_colors = self.config.zone_data.get("roi_colors", [])

            # DEBUG: Log deserialized zone data
            log.info(
                "worker.zone_data_deserialized",
                polygon_points=len(zd.polygon),
                has_polygon=bool(zd.polygon),
                polygon_sample=zd.polygon[:3] if zd.polygon else "empty",
            )

            # Store as 'default' zones for the detector
            self._default_zone_data = zd
        else:
            log.warning("worker.zone_data_missing", reason="config.zone_data is None")
            self._default_zone_data = ZoneData()

        return detector

    def _get_zone_data_for_video(self, video_metadata: dict) -> ZoneData:
        """Get zone data for a specific video.

        Uses per-video zone_data from video_metadata if available (batch processing),
        otherwise falls back to the default zone data (single video processing).

        Args:
            video_metadata: Dict containing video info, may include 'zone_data' key

        Returns:
            ZoneData object for the video
        """
        video_zone_dict = video_metadata.get("zone_data")

        if video_zone_dict and isinstance(video_zone_dict, dict):
            # Use per-video zone data (batch processing)
            zd = ZoneData()
            zd.polygon = video_zone_dict.get("polygon", [])
            zd.roi_polygons = video_zone_dict.get("roi_polygons", [])
            zd.roi_names = video_zone_dict.get("roi_names", [])
            zd.roi_colors = video_zone_dict.get("roi_colors", [])

            log.info(
                "worker.using_per_video_zone_data",
                video=os.path.basename(video_metadata.get("path", "")),
                polygon_points=len(zd.polygon),
                roi_count=len(zd.roi_polygons),
            )
            return zd
        else:
            # Fall back to default zone data (single video mode)
            log.info(
                "worker.using_default_zone_data",
                video=os.path.basename(video_metadata.get("path", "")),
                polygon_points=len(self._default_zone_data.polygon),
            )
            return self._default_zone_data

    def _process_single_video(
        self,
        index: int,
        total_videos: int,
        video_path: str,
        experiment_id: str,
        detector: Detector,
        video_metadata: dict,
    ) -> bool:
        """Process a single video file."""

        # 1. Open Video
        # 1. Open Video
        if isinstance(video_path, str) and video_path.isdigit():
            cap = cv2.VideoCapture(int(video_path))
        else:
            cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video: {video_path}")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # 2. Setup Zones & Calibration
        # Use per-video zone data if available (batch processing), otherwise use default
        video_zone_data = self._get_zone_data_for_video(video_metadata)

        # Force base dimensions to match video to prevent double-scaling if zones are already in native coords
        detector.base_width = width
        detector.base_height = height
        detector.set_zones(video_zone_data, width, height)

        # Fix: Ensure detector knows aquarium is defined if we have a polygon
        has_aquarium = bool(video_zone_data.polygon and len(video_zone_data.polygon) >= 3)
        detector.set_aquarium_region_defined(has_aquarium)

        # DEBUG: Log zone setup results
        log.info(
            "worker.zones_configured_for_video",
            video=experiment_id,
            video_dimensions=(width, height),
            polygon_points=len(video_zone_data.polygon),
            has_aquarium=has_aquarium,
            scaled_polygon_size=detector.scaled_polygon.size if hasattr(detector, 'scaled_polygon') else 'N/A',
            aquarium_region_defined=detector._aquarium_region_defined,
        )

        # 3. Setup Recorder
        # For single video mode, use the provided output directory
        # For batch processing, use the pre-calculated results_dir from video_metadata
        # or create a per-video results directory next to the video file
        if self.config.single_video_mode:
            results_dir = self.config.output_base_dir
        else:
            # Use pre-calculated results_dir if provided (batch processing with project metadata)
            results_dir = video_metadata.get("results_dir")
            if not results_dir:
                # Fallback: Create results directory next to the video file
                video_dir = os.path.dirname(video_path)
                results_dir = os.path.join(video_dir, f"{experiment_id}_results")
            os.makedirs(results_dir, exist_ok=True)
            log.info(
                "worker.results_dir_configured",
                video=experiment_id,
                results_dir=results_dir,
            )

        recorder = Recorder(settings_obj=self.config.settings)

        pixel_ratio = None

        recorder.start_recording(
            output_folder=results_dir,
            frame_width=width,
            frame_height=height,
            zones=video_zone_data,
            is_video_file=True,
            base_name=experiment_id,
            pixel_per_cm_ratio=pixel_ratio,
        )

        detector.reset_tracking_state()

        # 4. Processing Loop
        frame_num = 0
        processed_frames = 0  # Count frames actually processed by detector
        detected_frames = 0  # Count frames with at least one detection
        start_time = time.time()

        try:
            while True:
                if self._check_cancellation():
                    return False

                should_process = frame_num % self.config.analysis_interval_frames == 0
                detections = []

                if should_process:
                    # OPTIMIZATION: Only decode frames that will be processed
                    # cap.read() is expensive for high-res videos; only call when needed
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # Detect
                    detections, _ = detector.detect(frame, project_type="pre-recorded")
                    processed_frames += 1  # Count actually processed frames

                    # Count frames with detections
                    if detections:
                        detected_frames += 1

                    # Check cancellation after detection (slowest part)
                    if self._check_cancellation():
                        return False

                    # Record
                    timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    recorder.write_detection_data(timestamp, frame_num, detections)

                    # Display Update?
                    if frame_num % self.config.display_interval_frames == 0:
                        # Draw overlay (arena, ROIs, bboxes) on frame for display
                        detector.draw_overlay(frame, detections)

                        # Resize for preview if needed
                        # OPTIMIZATION: Use INTER_NEAREST for faster resizing
                        preview_frame = frame
                        if width > 1280:
                            scale = 1280 / width
                            preview_frame = cv2.resize(
                                preview_frame, (0, 0), fx=scale, fy=scale,
                                interpolation=cv2.INTER_NEAREST
                            )

                        # Calculate stats
                        elapsed = time.time() - start_time
                        fps = processed_frames / elapsed if elapsed > 0 else 0
                        stats = {
                            "fps": fps,  # Actual detection FPS
                            "frame": frame_num,  # Current position in video
                            "total_frames": total_frames,
                            "current_frame": frame_num,
                            "processed_frames": processed_frames,  # Frames run through detector
                            "detected_frames": detected_frames,  # Frames with detections
                        }

                        self.result_queue.put(
                            {
                                "type": "frame",
                                "frame": preview_frame,
                                "detections": detections,
                                "info": stats,
                                "experiment_id": experiment_id,
                            }
                        )

                        self._send_progress(
                            index,
                            total_videos,
                            frame_num / total_frames if total_frames > 0 else 0,
                            "Processando...",
                            experiment_id,
                            stats=stats,
                        )
                else:
                    # OPTIMIZATION: Fast seek without decoding for skipped frames
                    # cap.grab() is 10-20x faster than cap.read() for high-res videos
                    ret = cap.grab()
                    if not ret:
                        break

                frame_num += 1

        finally:
            cap.release()
            recorder.stop_recording()

        return True

    def _check_cancellation(self) -> bool:
        """Check for cancellation messages."""
        try:
            msg = self.command_queue.get_nowait()
            if msg == "cancel":
                self._cancel_requested = True
                log.info("worker.process.cancelled_by_command")
        except queue.Empty:
            pass
        return self._cancel_requested

    def _send_progress(self, index, total, fraction, message, experiment_id, stats=None):
        self.result_queue.put(
            {
                "type": "progress",
                "index": index,
                "total": total,
                "fraction": fraction,
                "message": message,
                "experiment_id": experiment_id,
                "stats": stats,
            }
        )
