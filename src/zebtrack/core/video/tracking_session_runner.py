"""Tracking session runner mixin — tracking loop, zone prep, and calibration.

Extracted from VideoProcessingService (Phase 2.3 decomposition).
Methods:
    _setup_tracking_session, _reset_detector_tracking_state, _process_tracking_frame,
    _calculate_tracking_progress_stats, _finalize_tracking_session,
    run_tracking_if_needed, _prepare_zone_data_for_tracking,
    _build_calibration_context, _tracking_cancelled
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog

if TYPE_CHECKING:
    from zebtrack.core.detection import Detector
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.core.video.video_processing_service import VideoContext
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.core.detection import ZoneData
from zebtrack.core.detection.calibration import Calibration
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()


class TrackingSessionRunnerMixin:
    """Mixin providing tracking session setup, execution loop, and finalisation."""

    # ── Attribute stubs (provided by the facade __init__) ──
    project_manager: ProjectManager
    state_manager: StateManager
    ui_coordinator: UIScheduler
    ui_event_bus: EventBusV2
    cancel_event: threading.Event
    settings: Settings
    detector: Detector | None
    recorder: Recorder | None

    # ── Cross-mixin method stubs (implemented by other mixins) ──
    def ensure_arena_polygon(
        self,
        arena_polygon_px: list | None,
        video_path: Path | str | None = None,
        video_context: Any | None = None,
    ) -> list[list[int]] | list | None: ...

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
        Recorder | None,
        ZoneData | None,
        list | None,
        Calibration | None,
        tuple | None,
    ]:
        """Set up tracking session: open video, prepare recorder, zones, and calibration."""
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

        Returns:
            Tuple of (detections, detected_count_increment, should_process)
        """
        should_process = frame_num % analysis_interval_frames == 0
        detections: list[tuple[Any, ...]] = []
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
        recorder: Recorder,
        cancel_requested: bool,
        experiment_id: str,
        trajectory_path: str,
        arena_polygon: list,
    ) -> tuple[bool, list]:
        """Finalize tracking session: stop recording, log results, publish events.

        Returns:
            Tuple of (success, arena_polygon)
        """
        stop_reason = "Cancelled by user" if cancel_requested else None
        recorder.stop_recording(force_stop=cancel_requested, reason=stop_reason)

        if cancel_requested:
            log.info("controller.tracking.cancelled", video=experiment_id)
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.SET_STATUS,
                    data={"message": f"Cancelamento solicitado para {experiment_id}."},
                )
            )
            return False, arena_polygon

        log.info("controller.tracking.success", path=trajectory_path)
        self.ui_event_bus.publish(
            Event(
                type=UIEvents.SET_STATUS,
                data={"message": f"Trajetória para {experiment_id} gerada."},
            )
        )
        return True, arena_polygon

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
        video_context: Any | None = None,
    ) -> tuple[bool, list[list[int]] | list | None]:
        """Run tracking process using multiprocessing worker to bypass GIL.

        Returns:
            Tuple of (success: bool, arena_polygon: list | None)
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")

        zone_data = self.project_manager.get_zone_data()
        arena_polygon = [list(point) for point in zone_data.polygon]

        # Early return if trajectory already exists
        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            return True, arena_polygon

        log.info("controller.tracking.starting_process", video=experiment_id)
        self.ui_event_bus.publish(
            Event(
                type=UIEvents.SET_STATUS,
                data={"message": f"Iniciando processo para {experiment_id}..."},
            )
        )

        from zebtrack.core.video.processing_worker import (
            ProcessingCallbacks,
            ProcessingContext,
            ProcessingWorker,
        )

        # Resolve actual path from video_path object if it's a FrameSource
        actual_path = str(video_path)
        if hasattr(video_path, "video_path"):
            actual_path = str(video_path.video_path)
        elif hasattr(video_path, "camera_index"):
            actual_path = str(video_path.camera_index)
        elif hasattr(video_path, "get_properties"):
            try:
                props = video_path.get_properties()
                if props.get("is_live_stream"):
                    actual_path = str(props.get("camera_index", 0))
                elif "path" in props:
                    actual_path = str(props["path"])
            except AttributeError:
                log.debug("video_processing.resolve_path.get_properties_error", exc_info=True)

        task = {
            "path": actual_path,
            "experiment_id": experiment_id,
        }

        context = ProcessingContext(
            videos_to_process=[task],
            output_base_dir=str(results_dir),
            cancel_event=self.cancel_event,
            settings=self.settings,
            single_video_config=None,
            zone_data=zone_data,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
        )

        result_status = {"success": False}

        def on_progress(*args) -> None:
            if not progress_callback:
                return
            if len(args) == 3:
                fraction, message, stats = args
            elif len(args) == 6:
                _idx, _total, _exp_id, fraction, message, stats = args
            else:
                log.warning("video_processing.on_progress.invalid_args", args_len=len(args))
                return
            progress_callback(fraction, message, stats=stats)

        def on_frame_processed(frame, detections, info):
            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_DISPLAY_FRAME,
                            data={
                                "frame": frame,
                                "detections": detections or [],
                            },
                        )
                    )

        def on_video_completed(idx, total, exp_id, success):
            log.info("tracking.video_completed", video=exp_id, success=success)
            result_status["success"] = success

        callbacks = ProcessingCallbacks(
            on_started=lambda: log.info("tracking.started", video=experiment_id),
            on_progress=on_progress,
            on_frame_processed=on_frame_processed,
            on_video_completed=on_video_completed,
            on_error=lambda e, exp_id: log.error("tracking.error", video=exp_id, error=str(e)),
            on_completed=lambda cancelled, out_dir, data: log.info(
                "tracking.session_completed", cancelled=cancelled
            ),
            on_fatal_error=lambda e, msg, data: log.error("tracking.fatal_error", error=str(e)),
        )

        worker = ProcessingWorker(context, callbacks)
        monitor_thread = worker.start_in_thread()

        monitor_thread.join()

        return result_status["success"], arena_polygon

    def _prepare_zone_data_for_tracking(
        self, frame_width: int, frame_height: int, detector: Any | None = None
    ) -> tuple[ZoneData, list[list[int]]]:
        """Ensure zone data is ready for tracking and inform plugins."""
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

        arena_polygon = [list(point) for point in zone_data.polygon]

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
        """Calculate calibration and pixel/cm ratio for tracking outputs."""
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
        """Handle cancel-event checks during tracking loop."""
        if not self.cancel_event.is_set():
            return False

        log.info(log_key, frame=frame_num, video=experiment_id)
        return True
