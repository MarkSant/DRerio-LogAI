"""Tracking session runner mixin: hands a video's tracking to the processing worker.

Extracted from VideoProcessingService (Phase 2.3 decomposition).

``run_tracking_if_needed`` is the only entry point. The frame loop itself lives in
``core/video/processing_worker.py``: the in-process helpers this mixin used to carry
(session setup, per-frame processing, calibration, finalisation) had no callers once
tracking moved to the worker and were removed (#647). Notably, the removed setup path
passed ``calibration=`` to ``start_recording``, which would have warped the trajectory
out of raw pixels; the worker never does.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.detection import Detector
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.i18n import _
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()


class TrackingSessionRunnerMixin:
    """Mixin that runs a video's tracking through ``ProcessingWorker``."""

    # ── Attribute stubs (provided by the facade __init__) ──
    project_manager: ProjectManager
    ui_event_bus: EventBusV2
    cancel_event: threading.Event
    settings: Settings
    weight_manager: WeightManager | None

    def run_tracking_if_needed(
        self,
        video_path: Path | str,
        results_dir: Path | str,
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
        results_dir = Path(results_dir) if isinstance(results_dir, str) else results_dir
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
                data=payloads.StatusPayload(
                    message=_("Starting process for {name}...").format(name=experiment_id)
                ),
            )
        )

        from zebtrack.core.services.worker_model_resolution import resolve_worker_model
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

        project_data = getattr(self.project_manager, "project_data", None)
        context = ProcessingContext(
            videos_to_process=[task],
            output_base_dir=str(results_dir),
            cancel_event=self.cancel_event,
            settings=self.settings,
            single_video_config=None,
            zone_data=zone_data,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            model_spec=resolve_worker_model(
                getattr(self, "weight_manager", None),
                self.settings,
                project_data if isinstance(project_data, dict) else None,
            ),
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
                            data=payloads.FrameDisplayPayload(
                                frame=frame,
                                detections=detections or [],
                            ),
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
