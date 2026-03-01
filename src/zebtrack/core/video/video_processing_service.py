"""Video Processing Service for ZebTrack-AI — Facade.

Phase 2.3 decomposition: Thin facade delegating to four extracted mixins:

- VideoContextFactoryMixin  — video I/O, results dirs, trajectory loading
- TrackingSessionRunnerMixin — tracking loop, zone prep, calibration
- ProgressNotifierMixin      — progress callbacks and UI notifications
- AnalysisPipelineRunnerMixin — report generation, social analysis

Public surface kept intact so callers do not need updating.

Dependencies (injected):
    See __init__ parameters below.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
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
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.core.video.analysis_pipeline_runner import AnalysisPipelineRunnerMixin
from zebtrack.core.video.progress_notifier import ProgressNotifierMixin
from zebtrack.core.video.tracking_session_runner import TrackingSessionRunnerMixin
from zebtrack.core.video.video_context_factory import VideoContextFactoryMixin

log = structlog.get_logger()


@dataclass
class VideoContext:
    """Shared video capture metadata to avoid redundant I/O.

    v2.2: Added skip_threshold for dynamic frame skip calibration.
    """

    path: str
    cap: cv2.VideoCapture | None
    width: int
    height: int
    fps: float
    first_frame: np.ndarray | None = None
    skip_threshold: int = 60

    def reset(self) -> None:
        """Seek capture back to the first frame if still open."""
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def release(self) -> None:
        """Release underlying capture safely."""
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        self.cap = None


class VideoProcessingService(
    VideoContextFactoryMixin,
    TrackingSessionRunnerMixin,
    ProgressNotifierMixin,
    AnalysisPipelineRunnerMixin,
):
    """Service for video processing orchestration.

    Phase 2.3: Thin facade — all business logic lives in the four mixins
    listed above.  Only ``__init__``, ``process_frame_source``, and
    ``process_single_video`` remain here.
    """

    def __init__(
        self,
        *,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_coordinator: UIScheduler,
        ui_event_bus: EventBusV2,
        cancel_event: threading.Event,
        settings_obj: Settings,
        detector: Detector | None = None,
        recorder: Recorder | None = None,
    ) -> None:
        """Initialize VideoProcessingService with injected dependencies."""
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.ui_event_bus = ui_event_bus
        self.cancel_event = cancel_event
        self.settings = settings_obj
        self.detector = detector
        self.recorder = recorder

        log.info("video_processing_service.init.complete")

    # ------------------------------------------------------------------
    # Entry-point: process a FrameSource (live camera or video file)
    # ------------------------------------------------------------------

    def process_frame_source(
        self,
        *,
        frame_source,
        output_dir: str,
        experiment_id: str,
        detector: Detector,
        recorder: Recorder,
        single_video_config: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
        record_video: bool = True,
    ) -> bool:
        """Process frames from a FrameSource (live camera or video file).

        Returns:
            True if processing succeeded, False otherwise
        """
        log.info(
            "video_processing_service.process_frame_source.start",
            experiment_id=experiment_id,
            output_dir=output_dir,
            is_live=frame_source.get_properties().get("is_live_stream", False),
        )

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        success, arena_polygon = self.run_tracking_if_needed(
            video_path=frame_source,
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

        if single_video_config:
            analysis_success = self._run_analysis_pipeline(
                experiment_id=experiment_id,
                video_path="live_stream",
                results_dir=str(output_path),
                arena_polygon_px=arena_polygon,
                metadata_context=single_video_config,
                single_video_config=single_video_config,
                progress_callback=None,
                analysis_profile=None,
            )
            return analysis_success

        return True

    # ------------------------------------------------------------------
    # Entry-point: process a single pre-recorded video
    # ------------------------------------------------------------------

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
        processing_report_callback: Callable[[], Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Process a single video: tracking + analysis.

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
                processing_report_callback=processing_report_callback,
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
            if detector and hasattr(detector, "clear_cache"):
                detector.clear_cache()
            if video_context is not None:
                video_context.release()
