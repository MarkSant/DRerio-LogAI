"""Multi-aquarium coordinator for zone, arena, and detection management.

Phase 4: Extracted from ProcessingCoordinator.
Handles aquarium detection, zone/arena polygon management, processing mode
configuration, and multi-aquarium assignment workflows.

Estimated size: ~750 lines (target <800).
"""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.coordinators.ui_state_coordinator import UIStateController
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.core.video.video_classification_service import VideoClassificationService
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class MultiAquariumCoordinator(BaseCoordinator):
    """Coordinator for multi-aquarium detection, zones, and processing modes.

    Responsibilities:
        - Multi-aquarium state reset
        - Processing mode management (single/multi-track toggling)
        - Aquarium detection (single and multi)
        - Aquarium assignment completion workflow
        - Folder relocation for named aquariums
        - Arena polygon management (set, save, add ROI)
        - Processing intervals and single-animal mode configuration

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        settings_obj: Settings,
        ui_coordinator: UIScheduler,
        ui_state_controller: UIStateController,
        cancel_event: Event,
        video_classification_service: VideoClassificationService,
        weight_manager: WeightManager | None = None,
        event_bus: EventBusV2 | None = None,
        view: Any = None,
        root: Any = None,
        detector: Any = None,
    ) -> None:
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.settings = settings_obj
        self.ui_coordinator = ui_coordinator
        self.ui_state_controller = ui_state_controller
        self.cancel_event = cancel_event
        self.video_classification_service = video_classification_service
        self.weight_manager = weight_manager
        self.view = view
        self.root = root
        self.detector = detector

        # Internal state
        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self._is_detecting_aquarium: bool = False
        self._auto_assign_aquariums: bool = False
        self._last_assignment_configs: list[dict] | None = None
        self._assigned_videos: set[str] = set()

        log.info("multi_aquarium_coordinator.initialized")

    # ========================================================================
    # Multi-Aquarium State
    # ========================================================================

    def reset_multi_aquarium_state(self) -> None:
        """Reset batch assignment state when project changes."""
        self._auto_assign_aquariums = False
        self._last_assignment_configs = None
        self._assigned_videos.clear()
        log.info("processing_coordinator.multi_aquarium_state.reset")

    # ========================================================================
    # Processing Mode Management
    # ========================================================================

    def _on_processing_mode_changed(self, payload: payloads.EventPayload) -> None:
        """Handle ZONE_PROCESSING_MODE_CHANGED event."""
        sequential = bool(_payload_get(payload, "sequential", False))
        video_path = _payload_get(payload, "video_path")
        if video_path:
            self._apply_processing_mode_to_video(video_path, sequential=sequential)
        else:
            self._apply_processing_mode_to_all_videos(sequential=sequential)

    def _apply_processing_mode_to_video(self, video_path: Path | str, *, sequential: bool) -> None:
        """Apply sequential/parallel mode to a specific video's multi-aquarium data."""
        from zebtrack.core.project.zone_manager import ZoneManager

        multi_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
        if multi_data:
            multi_data.sequential_processing = sequential
            serialized = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)
            entry = self.project_manager.find_video_entry(path=video_path)
            if entry:
                entry["multi_aquarium_zone_data"] = serialized
                self.project_manager.save_project()
            log.info(
                "processing_coordinator.mode_applied",
                video=os.path.basename(video_path),
                sequential=sequential,
            )

    def _apply_processing_mode_to_all_videos(self, *, sequential: bool) -> None:
        """Apply sequential/parallel mode to all videos in the project."""
        all_videos = self.project_manager.get_all_videos() or []
        for video_info in all_videos:
            path = video_info.get("path", "")
            if path:
                self._apply_processing_mode_to_video(path, sequential=sequential)

    # ========================================================================
    # Aquarium Detection
    # ========================================================================

    def run_aquarium_detection(
        self,
        video_path: Path | str,
        *,
        count: int | None = None,
        method: str = "auto",
        multi_aquarium: bool = False,
        stabilization_frames: int = 10,
    ) -> dict | None:
        """Run aquarium detection on a video.

        Args:
            video_path: Path to the video file.
            count: Expected number of aquariums (None for single).
            method: Detection method ('auto', 'contour', 'corners', 'model').
            multi_aquarium: Whether to detect multiple aquariums.
            stabilization_frames: Number of initial frames to analyze for stability.

        Returns:
            Detection results dict, or None on failure.
        """
        if self._is_detecting_aquarium:
            log.warning("processing_coordinator.aquarium_detection.already_active")
            return None

        self._is_detecting_aquarium = True
        log.info(
            "processing_coordinator.aquarium_detection.start",
            video=os.path.basename(video_path),
            multi=multi_aquarium,
            count=count,
        )

        try:
            from zebtrack.core.detection.aquarium_detector import AquariumDetector

            # Resolve model path via weight_manager (same pattern as LiveCalibrationCoordinator)
            detection_method = method if method != "auto" else "det"
            model_path = None
            if self.weight_manager:
                model_path = self.weight_manager.get_weight_path_by_method(
                    method=detection_method, task="aquarium"
                )
            if not model_path:
                log.error(
                    "processing_coordinator.aquarium_detection.no_model",
                    method=detection_method,
                )
                return None

            detector = AquariumDetector(model_path=model_path, mode=detection_method)

            if multi_aquarium:
                polygons = detector.detect_multiple_aquariums(
                    video_path=video_path,
                    expected_count=count or 2,
                    stabilization_frames=stabilization_frames,
                )
                if polygons:
                    log.info(
                        "processing_coordinator.aquarium_detection.multi_success",
                        count=len(polygons),
                    )

                    # Convert numpy arrays to lists for serialization
                    polygon_lists = [p.tolist() if hasattr(p, "tolist") else p for p in polygons]

                    self._publish_event(
                        UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS,
                        {
                            "video_path": video_path,
                            "polygons": polygon_lists,
                            "count": len(polygon_lists),
                            "method": method,
                        },
                    )

                    # Trigger assignment dialog
                    self._publish_event(
                        UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
                        {
                            "video_path": video_path,
                            "polygons": polygon_lists,
                            "count": len(polygon_lists),
                        },
                    )
                    return {"polygons": polygon_lists, "count": len(polygon_lists)}
                else:
                    log.warning("processing_coordinator.aquarium_detection.multi_failed")
                    self._publish_event(
                        UIEvents.ZONE_MULTI_AUTO_DETECT_FAILED,
                        {"video_path": video_path, "reason": "Detecção falhou"},
                    )
                return None
            else:
                # Single aquarium detection
                results = detector.detect_aquariums(
                    video_path=video_path,
                    stabilization_frames=stabilization_frames,
                )
                if results:
                    polygon = results[0]
                    polygon_list: list[tuple[float, float]] = (
                        polygon.tolist() if hasattr(polygon, "tolist") else list(polygon)
                    )
                    log.info(
                        "processing_coordinator.aquarium_detection.single_success",
                        points=len(polygon_list),
                    )
                    # Set arena polygon directly (no SUCCESS event exists for single detect)
                    self.set_main_arena_polygon(polygon_list)
                    return {"polygon": polygon_list}
                else:
                    log.warning("processing_coordinator.aquarium_detection.single_failed")
                return None

        except Exception as exc:  # except Exception justified: YOLO + cv2 + geometry pipeline
            log.error(
                "processing_coordinator.aquarium_detection.error",
                error=str(exc),
                exc_info=True,
            )
            if multi_aquarium:
                self._publish_event(
                    UIEvents.ZONE_MULTI_AUTO_DETECT_FAILED,
                    {"video_path": video_path, "reason": str(exc)},
                )
            return None
        finally:
            self._is_detecting_aquarium = False

    def _handle_multi_auto_detect(self, payload: payloads.EventPayload) -> None:
        """Handle ZONE_MULTI_AUTO_DETECT event.

        Extracts video_path and expected_count from event payload
        and delegates to run_aquarium_detection.
        """
        video_path = _payload_get(payload, "video_path", "")
        expected_count = _payload_get(payload, "expected_count", 2)
        method = _payload_get(payload, "method", "auto")

        if not video_path:
            log.warning("processing_coordinator.multi_auto_detect.no_video_path")
            return

        log.info(
            "processing_coordinator.multi_auto_detect.event_received",
            video=os.path.basename(video_path),
            expected_count=expected_count,
        )

        self.run_aquarium_detection(
            video_path,
            count=expected_count,
            method=method,
            multi_aquarium=True,
        )

    # ========================================================================
    # Aquarium Assignment
    # ========================================================================

    def _on_aquarium_assignment_completed(self, payload: payloads.EventPayload) -> None:
        """Handle ZONE_AQUARIUM_ASSIGNMENT_COMPLETED event.

        Processes aquarium group/subject/day assignments and updates project metadata.
        """
        configs = _payload_get(payload, "configs", [])
        video_path = _payload_get(payload, "video_path", "")
        apply_to_all = bool(_payload_get(payload, "apply_to_all", False))

        if not configs:
            log.warning("processing_coordinator.assignment.no_configs")
            return

        log.info(
            "processing_coordinator.assignment.received",
            video=os.path.basename(video_path) if video_path else "all",
            config_count=len(configs),
            apply_to_all=apply_to_all,
        )

        if apply_to_all:
            self._auto_assign_aquariums = True
            self._last_assignment_configs = configs

        # Update project metadata for the target video(s)
        target_videos = []
        if video_path:
            target_videos = [video_path]
        elif apply_to_all:
            all_vids = self.project_manager.get_all_videos() or []
            target_videos = [v.get("path", "") for v in all_vids if v.get("path")]

        for vpath in target_videos:
            if not vpath or vpath in self._assigned_videos:
                continue

            entry = self.project_manager.find_video_entry(path=vpath)
            if not entry:
                continue

            multi_data = self.project_manager.get_multi_aquarium_zone_data(vpath)
            if not multi_data:
                continue

            # Apply assignment configs to aquariums
            for config in configs:
                aq_id = config.get("aquarium_id", 0)
                for aq in multi_data.aquariums:
                    if aq.id == aq_id:
                        aq.group = config.get("group_name", "")
                        aq.subject_id = config.get("subject_name", "")
                        aq.day = config.get("day", "1")
                        break

            # Save updated multi-aquarium data
            from zebtrack.core.project.zone_manager import ZoneManager

            serialized = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)
            entry["multi_aquarium_zone_data"] = serialized

            # Update metadata in multi_aquarium_outputs if they exist
            multi_outputs = entry.get("multi_aquarium_outputs")
            if multi_outputs:
                for config in configs:
                    aq_id_str = str(config.get("aquarium_id", 0))
                    if aq_id_str in multi_outputs:
                        multi_outputs[aq_id_str]["group"] = config.get("group_name", "")
                        multi_outputs[aq_id_str]["subject_id"] = config.get("subject_name", "")
                        multi_outputs[aq_id_str]["day"] = config.get("day", "1")

            # Relocate folders if needed
            self._relocate_multi_aquarium_folders(vpath, entry, configs)

            self._assigned_videos.add(vpath)

        self.project_manager.save_project()

        self._publish_event(
            UIEvents.UI_REFRESH_PROJECT_VIEWS, payloads.ProjectViewsRefreshRequestedPayload()
        )
        log.info("processing_coordinator.assignment.completed", videos=len(target_videos))

    def _relocate_multi_aquarium_folders(
        self, video_path: Path | str, entry: dict, configs: list[dict]
    ) -> None:
        """Relocate multi-aquarium output folders from generic to named paths.

        Moves files from 'Sujeito_Indefinido' folders to properly named
        subject/group folders based on assignment configs.
        """
        multi_outputs = entry.get("multi_aquarium_outputs")
        if not multi_outputs:
            return

        experiment_id = os.path.splitext(os.path.basename(video_path))[0]
        project_path = self.project_manager.project_path
        if not project_path:
            return

        for config in configs:
            aq_id = config.get("aquarium_id", 0)
            aq_id_str = str(aq_id)
            group = config.get("group_name", "")
            subject = config.get("subject_name", "")
            day = config.get("day", "1")

            if aq_id_str not in multi_outputs:
                continue

            output_info = multi_outputs[aq_id_str]
            old_results_dir = output_info.get("results_dir", "")
            if not old_results_dir or not os.path.exists(old_results_dir):
                continue

            # Build new path based on assignment
            metadata = {
                "group": group,
                "group_display_name": group,
                "subject": subject,
                "day": day,
            }
            new_results_dir = str(
                self.project_manager.resolve_results_directory(
                    experiment_id=f"{experiment_id}_aq{aq_id}",
                    video_path=str(video_path),
                    metadata=metadata,
                )
            )

            if old_results_dir == new_results_dir:
                continue

            # Move files
            try:
                os.makedirs(new_results_dir, exist_ok=True)
                for item in os.listdir(old_results_dir):
                    src = os.path.join(old_results_dir, item)
                    dst = os.path.join(new_results_dir, item)
                    if os.path.isfile(src):
                        shutil.move(src, dst)

                # Update output info paths
                output_info["results_dir"] = new_results_dir
                pf = output_info.get("parquet_files", {})
                for key in list(pf.keys()):
                    old_pf_path = pf[key]
                    if old_pf_path and os.path.basename(old_pf_path):
                        new_pf_path = os.path.join(new_results_dir, os.path.basename(old_pf_path))
                        if os.path.exists(new_pf_path):
                            pf[key] = new_pf_path

                # Clean up old directory if empty
                try:
                    if os.path.exists(old_results_dir) and not os.listdir(old_results_dir):
                        os.rmdir(old_results_dir)
                        parent = os.path.dirname(old_results_dir)
                        if os.path.exists(parent) and not os.listdir(parent):
                            os.rmdir(parent)
                except OSError:
                    log.debug(
                        "coordinator.empty_dir_cleanup.skipped",
                        path=str(old_results_dir),
                        exc_info=True,
                    )

                log.info(
                    "processing_coordinator.folder_relocated",
                    aq_id=aq_id,
                    old=old_results_dir,
                    new=new_results_dir,
                )
            except OSError as e:
                log.warning(
                    "processing_coordinator.folder_relocation_failed",
                    aq_id=aq_id,
                    error=str(e),
                )

    # ========================================================================
    # Arena & ROI Polygon Management
    # ========================================================================

    def set_main_arena_polygon(self, points: list[tuple[float, float]]) -> bool:
        """Set the main arena polygon for the current video.

        Args:
            points: List of (x, y) tuples defining the arena polygon.

        Returns:
            True if the polygon was set successfully, False otherwise.
        """
        if not points or len(points) < 3:
            log.warning("processing_coordinator.set_arena.invalid_points", count=len(points))
            return False

        zone_data = self.project_manager.get_zone_data()
        if zone_data is None:
            from zebtrack.core.detection import ZoneData

            zone_data = ZoneData(polygon=[(int(x), int(y)) for x, y in points])
        else:
            zone_data.polygon = [(int(x), int(y)) for x, y in points]

        self.project_manager.save_zone_data(zone_data)
        self._publish_processing_mode(source="set_main_arena_polygon")
        log.info("processing_coordinator.set_arena.success", points=len(points))
        return True

    def save_manual_arena(self, polygon_list: list) -> bool:
        """Save a manually drawn arena polygon.

        Args:
            polygon_list: List of coordinate points from the UI canvas.

        Returns:
            True if saved successfully.
        """
        if not polygon_list:
            return False

        zone_data = self.project_manager.get_zone_data()
        if zone_data is None:
            from zebtrack.core.detection import ZoneData

            zone_data = ZoneData(polygon=polygon_list)
        else:
            zone_data.polygon = polygon_list

        self.project_manager.save_zone_data(zone_data)
        self._publish_processing_mode(source="save_manual_arena")
        log.info("processing_coordinator.save_arena.success", points=len(polygon_list))
        return True

    def add_roi_polygon(
        self,
        points_list: list[tuple[float, float]],
        name: str,
        color: tuple | None = None,
    ) -> bool:
        """Add an ROI polygon to the current zone data.

        Args:
            points_list: List of (x, y) tuples defining the ROI polygon.
            name: Name for the ROI region.
            color: Optional RGB color tuple for the ROI.

        Returns:
            True if the ROI was added successfully, False otherwise.
        """
        if not points_list or len(points_list) < 3:
            log.warning("processing_coordinator.add_roi.invalid_points", count=len(points_list))
            return False

        zone_data = self.project_manager.get_zone_data()
        if zone_data is None:
            log.warning("processing_coordinator.add_roi.no_zone_data")
            return False

        # Check for overlap with existing ROIs
        try:
            from shapely.geometry import Polygon as ShapelyPolygon

            new_poly = ShapelyPolygon(points_list)
            for i, existing_poly in enumerate(zone_data.roi_polygons):
                existing = ShapelyPolygon(existing_poly)
                if new_poly.intersects(existing):
                    overlap = new_poly.intersection(existing).area
                    overlap_pct = overlap / min(new_poly.area, existing.area) * 100
                    if overlap_pct > 50:
                        existing_name = (
                            zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                        )
                        log.warning(
                            "processing_coordinator.add_roi.high_overlap",
                            new_roi=name,
                            existing_roi=existing_name,
                            overlap_pct=f"{overlap_pct:.1f}%",
                        )
        except Exception:  # except Exception justified: non-critical polygon overlap geometry
            log.debug("processing_coordinator.add_roi.overlap_check.suppressed", exc_info=True)

        # Add the ROI (cast to list since ZoneData fields are typed as Sequence
        # but default_factory=list ensures they're mutable lists at runtime)
        roi_polys = cast(list, zone_data.roi_polygons)
        roi_polys.append(list(points_list))
        roi_nms = cast(list, zone_data.roi_names)
        roi_nms.append(name)
        if color:
            roi_cols = cast(list, zone_data.roi_colors)
            roi_cols.append(color)

        self.project_manager.save_zone_data(zone_data)
        log.info(
            "processing_coordinator.add_roi.success",
            name=name,
            points=len(points_list),
            total_rois=len(zone_data.roi_polygons),
        )
        return True

    # ========================================================================
    # Processing Mode Configuration
    # ========================================================================

    def _determine_processing_mode(self, single_video_config: dict | None = None) -> ProcessingMode:
        """Determine the processing mode based on settings and config."""
        resolved = self._resolve_single_animal_mode(single_video_config)

        if resolved is True:
            self._active_processing_mode = ProcessingMode.SINGLE_SUBJECT
        else:
            self._active_processing_mode = ProcessingMode.MULTI_TRACK

        log.info(
            "processing_coordinator.mode_determined",
            mode=self._active_processing_mode.name,
        )
        return self._active_processing_mode

    def _publish_processing_mode(
        self,
        source: str = "unknown",
        *,
        force: bool = False,
    ) -> None:
        """Publish the current processing mode to the event bus.

        Guards against race conditions by avoiding redundant publishes.
        """
        mode = self._active_processing_mode

        # Check if mode already published to avoid redundant events
        current_state = self.state_manager.get_processing_state()
        state_mode = getattr(current_state, "processing_mode", None)
        if state_mode == mode and not force:
            return

        self.state_manager.update_processing_state(
            source=f"processing_coordinator._publish_processing_mode.{source}",
            processing_mode=mode,
        )

        self._publish_event(
            UIEvents.UI_UPDATE_PROCESSING_MODE,
            payloads.UpdateProcessingModePayload(report=ProcessingReport(mode=mode, source=source)),
        )

        log.debug(
            "processing_coordinator.mode_published",
            mode=mode.name,
            source=source,
        )

    def _resolve_single_animal_mode(self, config: dict | None = None) -> bool | None:
        """Resolve single animal mode from config or project settings.

        Args:
            config: Optional single-video config dict.

        Returns:
            True for single animal, False for multi, None if unresolvable.
        """

        def _from_animals_count(value: object) -> bool | None:
            if value in (None, ""):
                return None
            try:
                return int(value) <= 1
            except (TypeError, ValueError):
                return None

        if config:
            val = config.get("single_animal_per_aquarium")
            if val is not None:
                return bool(val)

            count_based = _from_animals_count(config.get("animals_per_aquarium"))
            if count_based is not None:
                return count_based

        # Check project data
        project_data = getattr(self.project_manager, "project_data", {}) or {}

        # 1. Explicit flag at top level (legacy)
        val = project_data.get("single_animal_per_aquarium")
        if val is not None:
            return bool(val)

        # 2. Top-level animals_per_aquarium (legacy)
        count_based = _from_animals_count(project_data.get("animals_per_aquarium"))
        if count_based is not None:
            return count_based

        # 3. tracking.use_single_subject_tracker (set by wizard at project creation)
        tracking = project_data.get("tracking")
        if isinstance(tracking, dict):
            tracker_pref = tracking.get("use_single_subject_tracker")
            if tracker_pref is not None:
                return bool(tracker_pref)

        # 4. calibration.animals_per_aquarium (set by wizard at project creation)
        calibration = project_data.get("calibration")
        if isinstance(calibration, dict):
            count_based = _from_animals_count(calibration.get("animals_per_aquarium"))
            if count_based is not None:
                return count_based

        return None

    def _resolve_single_subject_tracker_preference(self, config: dict | None = None) -> bool | None:
        """Resolve single subject tracker preference."""
        if config:
            val = config.get("use_single_subject_tracker")
            if val is not None:
                return bool(val)

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        val = project_data.get("use_single_subject_tracker")
        if val is not None:
            return bool(val)

        return None

    def _configure_single_subject_tracker(self, enabled: bool) -> None:
        """Configure the detector for single-subject tracking mode."""
        if self.detector_service:
            try:
                self.detector_service.set_single_subject_mode(enabled)
            except Exception:  # except Exception justified: detector may not support mode
                log.debug(
                    "processing_coordinator.configure_tracker.suppressed",
                    exc_info=True,
                )

    def _determine_processing_intervals(self, config: dict | None = None) -> tuple[int, int]:
        """Determine analysis and display intervals.

        Args:
            config: Optional single-video config dict.

        Returns:
            Tuple of (analysis_interval_frames, display_interval_frames).
        """
        analysis = self.settings.video_processing.processing_interval
        display = self.settings.video_processing.display_interval

        if config:
            if "analysis_interval_frames" in config:
                analysis = int(config["analysis_interval_frames"])
            if "display_interval_frames" in config:
                display = int(config["display_interval_frames"])

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        if "analysis_interval_frames" in project_data:
            analysis = int(project_data["analysis_interval_frames"])
        if "display_interval_frames" in project_data:
            display = int(project_data["display_interval_frames"])

        return analysis, display

    @contextlib.contextmanager
    def _temporary_single_animal_mode(
        self, single_video_config: dict | None = None
    ) -> Generator[bool, None, None]:
        """Context manager to temporarily set single-animal mode during processing.

        Restores original settings on exit.
        """
        log.info(
            "controller.temporary_mode.entry",
            has_config=single_video_config is not None,
            config_keys=list(single_video_config.keys()) if single_video_config else [],
        )

        previous_mode = self.settings.video_processing.single_animal_per_aquarium
        resolved_mode = self._resolve_single_animal_mode(single_video_config)

        previous_tracker_pref = self.settings.tracking.use_single_subject_tracker
        resolved_tracker_pref = self._resolve_single_subject_tracker_preference(single_video_config)
        if resolved_tracker_pref is None and resolved_mode is not None:
            resolved_tracker_pref = bool(resolved_mode)
            log.info(
                "controller.processing.single_subject_tracker.inferred_from_single_animal",
                enabled=resolved_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

        if resolved_tracker_pref is None:
            resolved_tracker_pref = previous_tracker_pref

        if resolved_mode is not None and resolved_mode != previous_mode:
            self.settings.video_processing.single_animal_per_aquarium = resolved_mode
            log.info(
                "controller.processing.single_animal_mode",
                enabled=resolved_mode,
                previous=previous_mode,
                scope="single_video" if single_video_config else "project",
            )

        tracker_changed = resolved_tracker_pref != previous_tracker_pref
        if tracker_changed:
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            log.info(
                "controller.processing.single_subject_tracker",
                enabled=resolved_tracker_pref,
                previous=previous_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

        self._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
        self._publish_processing_mode(
            source="processing.temporary_mode.enter",
            force=True,
        )

        try:
            yield self.settings.video_processing.single_animal_per_aquarium
        finally:
            if self.settings.video_processing.single_animal_per_aquarium != previous_mode:
                self.settings.video_processing.single_animal_per_aquarium = previous_mode
                log.info(
                    "controller.processing.single_animal_mode_restored",
                    restored=previous_mode,
                )

            if tracker_changed:
                self.settings.tracking.use_single_subject_tracker = previous_tracker_pref
                log.info(
                    "controller.processing.single_subject_tracker_restored",
                    restored=previous_tracker_pref,
                )

            self._configure_single_subject_tracker(
                self.settings.tracking.use_single_subject_tracker
            )
            self._publish_processing_mode(
                source="processing.temporary_mode.exit",
                force=True,
            )
