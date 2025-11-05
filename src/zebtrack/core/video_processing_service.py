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
        cap = None  # Initialize to avoid UnboundLocalError in finally block
        try:
            cap = cv2.VideoCapture(str(video_path))
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
            if cap is not None and cap.isOpened():
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

        if self.detector:
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.tracking.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
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
        video_width_px, video_height_px = cal.target_dims_px
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
    ) -> bool:
        """Run complete analysis pipeline for a video.

        Phase 3: Moved from MainViewModel._run_analysis_pipeline
        """
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_df = self.load_trajectory_dataframe(trajectory_path, experiment_id)
        if trajectory_df is None:
            return False

        if self.cancel_event.is_set():
            log.info(
                "controller.analysis.cancelled_before_pipeline",
                video=experiment_id,
            )
            return False

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

        if isinstance(profile_dict, dict):
            profile_name = profile_dict.get("name")
            if profile_name and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile", profile_name)
            track_list = profile_dict.get("track_ids")
            if track_list and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile_tracks", list(track_list))

        zone_data = self.project_manager.get_zone_data()
        arena_polygon_px = self.ensure_arena_polygon(arena_polygon_px, video_path)
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

        reporter = Reporter(
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

        if self.cancel_event.is_set():
            log.info(
                "controller.analysis.cancelled_before_reports",
                video=experiment_id,
            )
            return False

        generated_outputs = self._generate_reports_for_video(
            reporter=reporter,
            experiment_id=experiment_id,
            results_dir=results_dir,
            progress_callback=progress_callback,
            cancel_event=self.cancel_event,
        )

        if generated_outputs is None:
            return False

        (
            summary_parquet_path,
            summary_excel_path,
            report_docx_path,
        ) = generated_outputs

        social_summary: dict | None = None
        raw_social_config = profile_dict.get("social") if isinstance(profile_dict, dict) else {}
        social_config = raw_social_config if isinstance(raw_social_config, dict) else {}
        social_enabled = bool(social_config.get("enabled"))
        if (
            social_enabled
            and pixelcm_x is not None
            and pixelcm_y is not None
            and "track_id" in filtered_df.columns
        ):
            active_tracks = filtered_df["track_id"].dropna().unique().tolist()
            if len(active_tracks) > 1:
                try:
                    radius_cm = float(social_config.get("radius_cm", 5.0))
                except (TypeError, ValueError):
                    radius_cm = 5.0

                try:
                    social_summary = ROIAnalyzer.analyze_social_proximity(
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

        profile_name = profile_dict.get("name", "default")
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_SOCIAL_SUMMARY,
            {"profile": profile_name, "stats": social_summary, "tracks": resolved_track_ids},
        )

        # Register outputs for both project and single video workflows
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
        frame_source: "FrameSource",
        output_dir: str,
        experiment_id: str,
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
            single_video_config: Optional configuration dict for single video mode
            analysis_interval_frames: Frame interval for running detection/tracking
            display_interval_frames: Frame interval for updating UI
            record_video: Whether to save video with overlay

        Returns:
            True if processing succeeded, False otherwise
        """
        from zebtrack.io.frame_source import FrameSource

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

        Returns:
            Tuple of (success: bool, results_dir: str | None)
        """
        try:
            video_path = video_info.get("path")
            if not video_path:
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

            self.display_initial_frame(video_path)

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
                progress_callback,
                calibration_data=single_video_config,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
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
            )

            if self.cancel_event.is_set():
                self._cleanup_cancelled_results(results_dir, baseline_items)
                return False, results_dir

            return analysis_success, results_dir
        finally:
            # Release frame references
            if self.detector and hasattr(self.detector, "clear_cache"):
                self.detector.clear_cache()
