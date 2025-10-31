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
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.core.detector import Detector
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_coordinator import UICoordinator
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import ZoneData
from zebtrack.ui.events import Events

log = structlog.get_logger()


class VideoProcessingService:
    """Service for video processing orchestration.

    Phase 7.2: Consolidates video processing logic previously scattered
    in MainViewModel into a cohesive service layer.
    """

    def __init__(
        self,
        *,
        detector: Detector | None,
        recorder: Recorder,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        ui_event_bus: EventBus,
        root,  # tkinter.Tk
        view,  # ApplicationGUI
        cancel_event,  # threading.Event
        settings_obj: Settings,
    ):
        """Initialize VideoProcessingService with injected dependencies.

        Args:
            detector: Detector instance (can be None if not initialized)
            recorder: Recorder instance for trajectory writing
            project_manager: ProjectManager for project state
            state_manager: StateManager for centralized state
            ui_coordinator: UICoordinator for UI updates
            ui_event_bus: Event bus for UI events
            root: Tkinter root for scheduling UI updates
            view: ApplicationGUI for direct UI access
            cancel_event: Threading event for cancellation signaling
            settings_obj: Settings instance for configuration access
        """
        self.detector = detector
        self.recorder = recorder
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.ui_event_bus = ui_event_bus
        self.root = root
        self.view = view
        self.cancel_event = cancel_event
        self.settings = settings_obj

        log.info("video_processing_service.init.complete")

    def display_initial_frame(self, video_path: Path | str) -> None:
        """Display first frame of video in UI.

        Args:
            video_path: Path to video file
        """
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
        self, arena_polygon_px: list | None, video_path: Path | str
    ) -> list | None:
        """Ensure arena polygon exists, using full frame as fallback.

        Args:
            arena_polygon_px: Existing polygon or None
            video_path: Path to video (for extracting dimensions)

        Returns:
            Arena polygon (existing or full-frame fallback)
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        if arena_polygon_px:
            return arena_polygon_px

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return [[0, 0], [width, 0], [width, height], [0, height]]

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
            self.root.after(
                0,
                lambda: self.view.show_error(
                    "Erro de Processamento",
                    f"Falha ao gerar arquivo de trajetória para {experiment_id}.",
                ),
            )
            return None

        try:
            return pd.read_parquet(trajectory_path)
        except Exception as exc:
            log.error(
                "video_processing.trajectory_read_failed",
                path=trajectory_path,
                error=str(exc),
            )
            self.root.after(
                0,
                lambda: self.view.show_error(
                    "Erro de Processamento",
                    f"Falha ao ler arquivo de trajetória para {experiment_id}.",
                ),
            )
            return None

    def create_progress_callback(
        self, *, index: int, total_videos: int, experiment_id: str
    ) -> Callable:
        """Create progress callback for video processing.

        Phase 7.2: Extracted from controller to centralize progress handling.

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            experiment_id: Experiment identifier

        Returns:
            Callable that accepts progress stats dict
        """
        # TODO: Implement in next sub-step (7.2c)
        raise NotImplementedError("Será implementado na sub-etapa 7.2c")

    def run_tracking_if_needed(
        self,
        video_path: Path | str,
        results_dir: str,
        experiment_id: str,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
    ) -> tuple[bool, list | None]:
        """Run tracking process if trajectory doesn't exist.

        Phase 3: Moved from MainViewModel._run_tracking_if_needed

        Args:
            video_path: Path to video file
            results_dir: Output directory for results
            experiment_id: Unique experiment identifier
            progress_callback: Optional progress update callback
            calibration_data: Optional calibration configuration
            analysis_interval_frames: Frame interval for analysis
            display_interval_frames: Frame interval for display

        Returns:
            Tuple of (success: bool, arena_polygon: list | None)
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        arena_polygon = self.project_manager.get_zone_data().polygon
        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            return True, arena_polygon

        if self.detector is None:
            log.error("controller.tracking.no_detector")
            return False, None

        log.info("controller.tracking.generating", video=experiment_id)
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Gerando trajetória para {experiment_id}..."},
        )

        recorder = self.recorder.__class__(settings_obj=self.settings)
        cap = cv2.VideoCapture(str(video_path))
        try:
            if not cap.isOpened():
                log.error("controller.tracking.video_open_failed", path=video_path)
                return False, None

            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            zone_data, arena_polygon = self._prepare_zone_data_for_tracking(
                frame_width, frame_height
            )

            cal, pixel_per_cm_ratio = self._build_calibration_context(
                arena_polygon, calibration_data
            )

            recorder.start_recording(
                output_folder=results_dir,
                frame_width=frame_width,
                frame_height=frame_height,
                zones=zone_data,
                is_video_file=True,
                base_name=experiment_id,
                pixel_per_cm_ratio=pixel_per_cm_ratio,
                calibration=cal,
            )

            if self.detector and hasattr(self.detector, "reset_tracking_state"):
                try:
                    self.detector.reset_tracking_state()
                except Exception:  # pragma: no cover - defensive
                    plugin_obj = getattr(self.detector, "plugin", None)
                    plugin_class = getattr(plugin_obj, "__class__", type(self.detector))
                    log.warning(
                        "controller.tracking.reset_tracker_failed",
                        plugin=plugin_class,
                        exc_info=True,
                    )

            frame_num = 0
            processed_frames_count = 0
            detected_frames_count = 0  # Frames that actually have detections
            start_time = time.time()  # Track processing start time
            cancel_requested = False
            log.info("controller.tracking.loop.start", video=experiment_id)
            while True:
                if self._tracking_cancelled(
                    experiment_id,
                    frame_num,
                    "controller.tracking.cancelled.event_detected",
                ):
                    cancel_requested = True
                    break

                ret, frame = cap.read()
                if not ret:
                    log.info("controller.tracking.loop.end_of_video", frame=frame_num)
                    break

                if self._tracking_cancelled(
                    experiment_id,
                    frame_num,
                    "controller.tracking.cancelled.after_read",
                ):
                    cancel_requested = True
                    break

                # Check if we should process this frame (analysis interval)
                should_process = frame_num % analysis_interval_frames == 0
                detections = []

                if should_process:
                    detections, _ = self.detector.detect(frame, project_type="pre-recorded")

                    timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    recorder.write_detection_data(timestamp, frame_num, detections)

                    processed_frames_count += 1

                    # Count frames that actually have detections
                    if detections:
                        detected_frames_count += 1

                if self._tracking_cancelled(
                    experiment_id,
                    frame_num,
                    "controller.tracking.cancelled.before_progress",
                ):
                    cancel_requested = True
                    break

                # Update GUI display every processed frame for smoother visualization
                if progress_callback and should_process:
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    progress_fraction = (frame_num + 1) / total_frames if total_frames > 0 else 0

                    # Calculate elapsed time and ETA
                    elapsed_time = time.time() - start_time
                    if frame_num > 0 and progress_fraction > 0:
                        estimated_total_time = elapsed_time / progress_fraction
                        eta_time = estimated_total_time - elapsed_time
                    else:
                        eta_time = -1  # Unknown

                    # Prepare statistics for GUI update
                    stats = {
                        "total_frames": total_frames,
                        "current_frame": frame_num + 1,  # For accurate ETA calculation
                        "processed_frames": processed_frames_count,
                        "detected_frames": detected_frames_count,
                        "start_time": start_time,
                        "elapsed": elapsed_time,
                        "eta": eta_time,
                        "percent": progress_fraction * 100,
                    }

                    # Always draw overlay on processed frames
                    self.detector.draw_overlay(frame, detections)
                    progress_callback(
                        progress_fraction,
                        "Gerando trajetória...",
                        frame,
                        stats,
                        detections=detections,
                    )

                frame_num += 1

            stop_reason = "Cancelled by user" if cancel_requested else None
            recorder.stop_recording(
                force_stop=cancel_requested, reason=stop_reason
            )  # Skip save on cancel

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

        except Exception as e:
            log.error(
                "controller.tracking.error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Rastreamento",
                    "message": f"Ocorreu um erro inesperado ao gerar a trajetória para {experiment_id}:\n{e}",  # noqa: E501
                },
            )
            return False, None
        finally:
            if cap.isOpened():
                cap.release()

    def _prepare_zone_data_for_tracking(
        self, frame_width: int, frame_height: int
    ) -> tuple[ZoneData, list[list[int]]]:
        """Ensure zone data is ready for tracking and inform plugins.

        Phase 3: Moved from MainViewModel._prepare_zone_data_for_tracking
        """
        assert self.detector is not None

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

        self.detector.set_zones(zone_data, frame_width, frame_height)

        if self.detector and hasattr(self.detector.plugin, "set_aquarium_region_defined"):
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.plugin.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.tracking.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
                context=getattr(self.detector.plugin, "_context", "unknown"),
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
    ) -> tuple[bool, str | None]:
        """Process a single video: tracking + analysis.

        Phase 7.2: Complete single-video workflow (~86 lines).

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

        Returns:
            Tuple of (success: bool, results_dir: str | None)
        """
        # TODO: Implement in sub-step 7.2d
        raise NotImplementedError("Será implementado na sub-etapa 7.2d")
