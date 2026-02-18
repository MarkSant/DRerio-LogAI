"""Single-aquarium detection and tracking for zebrafish.

Manages the detection process for single-aquarium mode by delegating to a
detector plugin and handling stateful logic for zone tracking, ByteTrack/simple
tracking, ROI filtering, and overlay rendering.
"""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog

from zebtrack.core.detection_post_processor import DetectionPostProcessor
from zebtrack.core.detection_types import MultiAquariumZoneData, ZoneData
from zebtrack.core.single_subject_tracker import SingleSubjectTracker
from zebtrack.core.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.tracker.byte_tracker import BYTETracker

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()

__all__ = ["SingleDetector"]


class SingleDetector:
    """Manages the detection process for single-aquarium mode.

    Delegates to a plugin for raw inference and handles stateful logic for
    zone tracking, ROI filtering, and overlay rendering.

    Nota de Otimização:
    O rastreamento de objetos é baseado nos bounding boxes. Se o modelo de IA
    carregado for um modelo de segmentação (*_seg.pt), ele realizará a
    tarefa computacionalmente mais custosa de encontrar máscaras de pixel,
    mesmo que apenas os bounding boxes sejam usados. Para um desempenho
    ótimo no rastreamento, um modelo treinado apenas para DETECÇÃO (que
    gera somente bounding boxes) deve ser usado em futuras versões.

    Args:
        plugin: An instantiated detector plugin.
        zone_scaler: ZoneScaler instance for coordinate scaling.
        post_processor: DetectionPostProcessor for utilities.
        base_width: The reference width the zones were defined on.
        base_height: The reference height the zones were defined on.
        settings_obj: Settings instance (injected, optional for backward compat).
    """

    def __init__(
        self,
        plugin: DetectorPlugin,
        zone_scaler: ZoneScaler | None = None,
        post_processor: DetectionPostProcessor | None = None,
        base_width: int = 1280,
        base_height: int = 720,
        settings_obj: "Settings | None" = None,
    ) -> None:
        self.plugin = plugin
        if not self.plugin:
            log.error("single_detector.init.no_plugin")
            raise ValueError("SingleDetector must be initialized with a valid plugin.")

        self.settings = settings_obj
        self.zone_scaler = zone_scaler or ZoneScaler(base_width, base_height)
        self.post_processor = post_processor or DetectionPostProcessor()
        self.base_width = base_width
        self.base_height = base_height
        log.info("single_detector.init.success", plugin=self.plugin.get_name())

        # Zone configuration
        self.zones: ZoneData = ZoneData()
        self._zones_configured = False
        self._last_width: int | None = None
        self._last_height: int | None = None
        self._context: str = "tracking"
        self._aquarium_region_defined: bool = False

        # Tracking state
        self._single_subject_mode = False
        self._single_subject_tracker = SingleSubjectTracker()
        self._byte_tracker: BYTETracker | None = None
        self._byte_tracker_params: tuple[float, float, int, float, float, bool, bool] | None = None

        # Dynamic class ID resolution
        self.aquarium_class_id, self.animal_class_id = DetectionPostProcessor.resolve_class_ids(
            plugin
        )

    # =========================================================================
    # Properties — backward compatibility
    # =========================================================================

    @property
    def polygon(self) -> list[list[int]]:
        """Delegate to zones.polygon for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return [list(point) for point in self.zones.polygon]
        return []

    @property
    def roi_polygons(self) -> list[list[list[int]]]:
        """Delegate to zones.roi_polygons for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return [[list(point) for point in polygon] for polygon in self.zones.roi_polygons]
        return []

    @property
    def roi_names(self) -> list[str]:
        """Delegate to zones.roi_names for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return list(self.zones.roi_names)
        return []

    @property
    def roi_colors(self) -> list[tuple[int, int, int]]:
        """Delegate to zones.roi_colors for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return list(self.zones.roi_colors)
        return []

    @property
    def single_mode(self) -> bool:
        """Backward-compatible alias for single-subject mode flag."""
        return self._single_subject_mode

    @property
    def scaled_polygon(self) -> np.ndarray:
        """Delegate to zone_scaler.scaled_polygon."""
        return self.zone_scaler.scaled_polygon

    @scaled_polygon.setter
    def scaled_polygon(self, value: np.ndarray) -> None:
        """Allow direct assignment for backward compat (ProcessingWorker debug logging)."""
        self.zone_scaler.scaled_polygon = value

    @property
    def scaled_roi_polygons(self) -> list[np.ndarray]:
        """Delegate to zone_scaler.scaled_roi_polygons."""
        return self.zone_scaler.scaled_roi_polygons

    # =========================================================================
    # Zone configuration
    # =========================================================================

    def set_zones(
        self,
        zones: ZoneData | MultiAquariumZoneData,
        actual_width: int,
        actual_height: int,
    ) -> None:
        """Set the detection zones and scale them to current video resolution.

        Args:
            zones: The zone configuration object.
            actual_width: The width of the video/camera frame to scale to.
            actual_height: The height of the video/camera frame to scale to.

        Raises:
            ValueError: If dimensions are non-positive.
        """
        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(
                "Actual dimensions must be positive. "
                f"set_zones(zones, actual_width={actual_width}, "
                f"actual_height={actual_height})"
            )

        self.zones = zones  # type: ignore[assignment]
        # Clear cache if zones are redefined
        self.zone_scaler.clear_cache()

        self.zone_scaler.update_scaling(zones, actual_width, actual_height)

        # Collect stats for logging
        has_polygon = False
        polygon_points = 0
        roi_count = 0
        polygon_sample: Any = "empty"
        is_multi = isinstance(zones, MultiAquariumZoneData) or hasattr(zones, "aquariums")

        if is_multi and isinstance(zones, MultiAquariumZoneData):
            multi_zones = zones
            polygon_points = sum(len(aq.polygon) for aq in multi_zones.aquariums)
            roi_count = sum(len(aq.roi_polygons) for aq in multi_zones.aquariums)
            has_polygon = bool(multi_zones.aquariums)
            if has_polygon:
                polygon_sample = str(multi_zones.aquariums[0].polygon[:3])
        elif isinstance(zones, ZoneData):
            single_zone = zones
            has_polygon = bool(single_zone.polygon)
            polygon_points = len(single_zone.polygon) if single_zone.polygon else 0
            roi_count = len(single_zone.roi_polygons) if single_zone.roi_polygons else 0
            if has_polygon:
                poly_np = np.array(single_zone.polygon)
                polygon_sample = poly_np[:3].tolist() if poly_np.size > 0 else "empty"
        else:
            log.warning("single_detector.zones.unknown_type", type=type(zones))

        log.info(
            "single_detector.zones.set",
            roi_count=roi_count,
            polygon_points=polygon_points,
            has_polygon=has_polygon,
            scaled_polygon_sample=polygon_sample,
            actual_dimensions=(actual_width, actual_height),
            base_dimensions=(self.base_width, self.base_height),
            is_multi_aquarium=is_multi,
        )

        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height
        self._single_subject_tracker.reset()

    def set_context(self, context: str) -> None:
        """Set the detection context.

        Args:
            context: 'tracking' or 'diagnostic'.
        """
        if context in ("tracking", "diagnostic"):
            self._context = context
            log.info("single_detector.context.set", context=context)

    def set_aquarium_region_defined(self, defined: bool = True) -> None:
        """Set whether aquarium region has been defined.

        Args:
            defined: True if aquarium region is defined.
        """
        self._aquarium_region_defined = bool(defined)
        log.info("single_detector.aquarium_region_defined.set", defined=defined)

    # =========================================================================
    # Detection
    # =========================================================================

    def detect(
        self,
        frame: np.ndarray,
        project_type: str,
        conf_threshold: float | None = None,
    ) -> tuple[list[tuple], str | None]:
        """Process a single frame for object detection and state tracking.

        Args:
            frame: Input BGR frame.
            project_type: Project type string.
            conf_threshold: Optional confidence threshold override.

        Returns:
            Tuple of (list of detection tuples, error message or None).

        Raises:
            RuntimeError: If set_zones() was not called.
            ValueError: If frame is invalid.
        """
        DetectionPostProcessor.validate_frame(frame)

        if not self._zones_configured:
            raise RuntimeError(
                "Must call set_zones() before detect(). "
                "Zones need video dimensions for proper scaling."
            )

        if self._last_width and self._last_height:
            expected = (self._last_width, self._last_height)
            actual = (frame.shape[1], frame.shape[0])
            if expected != actual:
                log.warning(
                    "single_detector.dimension_mismatch",
                    expected=expected,
                    actual=actual,
                    message=(
                        "Frame dimensions differ from dimensions used to "
                        "set zones. This may cause inaccurate detection "
                        "scaling."
                    ),
                )

        if self.zone_scaler.scaled_polygon.size == 0:
            return [], None

        crop_info = self.zone_scaler.get_crop_info(frame, self.zone_scaler.scaled_polygon)
        if crop_info is None:
            return [], None

        cropped_frame, crop_x1, crop_y1 = crop_info
        raw_detections = self.plugin.detect(cropped_frame, conf_threshold=conf_threshold)

        predictions = DetectionPostProcessor.offset_detections(raw_detections, crop_x1, crop_y1)

        if self.zone_scaler.scaled_polygon.size > 0:
            filtered = []
            for det in predictions:
                x1, y1, x2, y2 = det[0], det[1], det[2], det[3]
                if self.zone_scaler.is_inside_polygon(
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    self.zone_scaler.scaled_polygon,
                ):
                    filtered.append(det)
            predictions = filtered

        predictions = DetectionPostProcessor.apply_class_mismatch_fallback(
            predictions,
            self.zone_scaler.scaled_polygon,
            self.aquarium_class_id,
            self.animal_class_id,
        )
        if self.animal_class_id is not None:
            predictions = [det for det in predictions if det[6] == self.animal_class_id]

        if self.settings is None and not self._single_subject_mode and len(predictions) > 1:
            from zebtrack.tracker.basetrack import BaseTrack

            tracked = [
                (
                    int(det[0]),
                    int(det[1]),
                    int(det[2]),
                    int(det[3]),
                    float(det[4]),
                    BaseTrack.next_id(),
                    int(det[6]),
                )
                for det in predictions
            ]
            return tracked, None

        return self.track(predictions, project_type)

    def track(self, predictions: list[tuple], project_type: str) -> tuple[list[tuple], str | None]:
        """Track objects across frames using configured tracker.

        Args:
            predictions: List of detection tuples.
            project_type: Project type (e.g. 'pre-recorded').

        Returns:
            Tuple of (tracked_predictions, error_message).
        """
        if self._context != "tracking":
            return predictions, None

        height = self._last_height or self.base_height
        width = self._last_width or self.base_width
        frame_shape = (height, width, 3)

        if DetectionPostProcessor.should_use_bytetrack(self.settings):
            tracks = self._apply_byte_tracking(predictions, frame_shape)
        else:
            tracks = self._apply_simple_tracking(predictions)

        return tracks, None

    # =========================================================================
    # Tracking
    # =========================================================================

    def set_single_subject_mode(self, enabled: bool) -> None:
        """Toggle Single Animal Mode.

        When enabled, configures the ByteTracker to use robust 'Single Animal'
        logic (ID Resurrection + Immediate Activation).

        Args:
            enabled: True to enable single subject mode.
        """
        enabled = bool(enabled)
        if self._single_subject_mode == enabled:
            return

        self._single_subject_mode = enabled
        # Force re-init of ByteTracker to pick up the new mode
        self._byte_tracker = None
        self._byte_tracker_params = None

        log.info(
            "single_detector.single_subject_mode.changed",
            enabled=enabled,
            strategy="robust_bytetrack_single_animal",
        )

        if hasattr(self.plugin, "set_use_single_subject_mode"):
            try:
                self.plugin.set_use_single_subject_mode(enabled)
            except Exception:  # pragma: no cover - defensive
                log.warning("single_detector.plugin_update_failed", exc_info=True)

    def is_single_subject_mode(self) -> bool:
        """Expose the current single-subject tracking flag."""
        return self._single_subject_mode

    def reset_tracking_state(self) -> None:
        """Reset tracker state between videos.

        Resets plugin tracking, single subject tracker, ByteTracker,
        and global track ID counter.
        """
        if hasattr(self.plugin, "reset_tracking_state"):
            try:
                self.plugin.reset_tracking_state()
            except Exception:  # pragma: no cover - defensive
                log.warning(
                    "single_detector.reset_tracking_state.plugin_failed",
                    exc_info=True,
                )
        self._single_subject_tracker.reset()
        self._byte_tracker = None
        self._byte_tracker_params = None

        # Reset global track ID counter so new videos start with ID=1
        from zebtrack.tracker.basetrack import BaseTrack

        BaseTrack.reset_id_counter()
        log.debug("single_detector.reset_tracking_state.id_counter_reset")

    def clear_cache(self) -> None:
        """Clear the internal scaling cache to free memory."""
        self.zone_scaler.clear_cache()

    def _is_inside_polygon(self, x1: int, y1: int, x2: int, y2: int, polygon: np.ndarray) -> bool:
        """Backward-compat delegation to ``zone_scaler.is_inside_polygon``."""
        return self.zone_scaler.is_inside_polygon(x1, y1, x2, y2, polygon)

    def _apply_simple_tracking(self, detections: list[tuple]) -> list[tuple]:
        """Apply simple SingleSubjectTracker (IoU+Distance) to detections.

        Used when ByteTrack is disabled. Assigns ID=1 to the best detection.
        """
        if not detections:
            self._single_subject_tracker.reset()
            return []

        tracked = self._single_subject_tracker.assign(detections)
        return tracked

    def _apply_byte_tracking(
        self, detections: list[tuple], frame_shape: tuple[int, int, int]
    ) -> list[tuple]:
        """Apply ByteTracker to detections for robust multi-frame tracking.

        Args:
            detections: List of detection tuples.
            frame_shape: Frame dimensions as (height, width, channels).

        Returns:
            List of tracked detection tuples with assigned track IDs.
        """
        log.debug(
            "single_detector.bytetrack.input",
            num_detections=len(detections),
            frame_shape=frame_shape,
        )

        if not detections:
            tracker = self._ensure_byte_tracker()
            if tracker is not None:
                empty = np.empty((0, 5), dtype=np.float32)
                frame_dims = (frame_shape[0], frame_shape[1])
                tracker.update(empty, frame_dims, frame_dims)
            log.debug(
                "single_detector.bytetrack.output",
                num_tracks=0,
                reason="no_input_detections",
            )
            return []

        tracker = self._ensure_byte_tracker()
        if tracker is None:
            log.warning("single_detector.bytetrack.tracker_init_failed")
            return [
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    None,
                    int(class_id),
                )
                for x1, y1, x2, y2, confidence, track_id, class_id in detections
            ]

        det_array = np.array(
            [
                [
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2),
                    float(confidence),
                ]
                for x1, y1, x2, y2, confidence, _, _ in detections
            ],
            dtype=np.float32,
        )

        frame_dims = (frame_shape[0], frame_shape[1])

        log.debug(
            "single_detector.bytetrack.calling_update",
            det_array_shape=det_array.shape,
            frame_dims=frame_dims,
            img_size_passed=frame_dims,
        )

        tracks = tracker.update(det_array, frame_dims, frame_dims)

        log.debug(
            "single_detector.bytetrack.update_result",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
        )

        # Map tracks to class_ids based on IoU with original detections
        results: list[tuple] = []
        for track in tracks:
            track_bbox = track.tlbr

            best_iou = 0.0
            best_class_id = 0
            best_det = None

            for det in detections:
                det_x1, det_y1, det_x2, det_y2, _det_conf, _, det_class_id = det

                iou = DetectionPostProcessor.calculate_iou(
                    track_bbox[0],
                    track_bbox[1],
                    track_bbox[2],
                    track_bbox[3],
                    det_x1,
                    det_y1,
                    det_x2,
                    det_y2,
                )

                if iou > best_iou:
                    best_iou = iou
                    best_class_id = det_class_id
                    best_det = det

            # Use ORIGINAL detection coordinates, not Kalman-filtered
            if best_det is not None and best_iou > 0.1:
                x1, y1, x2, y2 = (
                    best_det[0],
                    best_det[1],
                    best_det[2],
                    best_det[3],
                )
                confidence = best_det[4]

                log.debug(
                    "single_detector.bytetrack.using_original_detection",
                    track_bbox=(
                        int(track_bbox[0]),
                        int(track_bbox[1]),
                        int(track_bbox[2]),
                        int(track_bbox[3]),
                    ),
                    original_det=(x1, y1, x2, y2),
                    iou=best_iou,
                    track_id=track.track_id,
                )
            else:
                x1, y1, x2, y2 = track_bbox
                confidence = track.score

                log.warning(
                    "single_detector.bytetrack.no_matching_detection",
                    track_bbox=(int(x1), int(y1), int(x2), int(y2)),
                    best_iou=best_iou,
                    track_id=track.track_id,
                )

            results.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    int(track.track_id),
                    int(best_class_id),
                )
            )

        log.debug(
            "single_detector.bytetrack.output",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
            num_results=len(results),
        )

        # When ByteTracker returns no tracks but we have detections
        if len(results) == 0 and len(detections) > 0:
            if self._single_subject_mode:
                best_det = max(detections, key=lambda d: d[4])
                log.debug(
                    "single_detector.bytetrack.single_subject_fallback_id1",
                    num_detections=len(detections),
                    chosen_confidence=float(best_det[4]),
                    message=("ByteTracker returned no tracks; forcing ID=1 on best detection"),
                )
                results = [
                    (
                        int(best_det[0]),
                        int(best_det[1]),
                        int(best_det[2]),
                        int(best_det[3]),
                        float(best_det[4]),
                        1,
                        int(best_det[6]),
                    )
                ]
            else:
                log.debug(
                    "single_detector.bytetrack.passthrough_untracked",
                    num_detections=len(detections),
                    reason=("bytetracker_returned_no_tracks_but_detections_exist"),
                )
                results = [
                    (
                        int(det[0]),
                        int(det[1]),
                        int(det[2]),
                        int(det[3]),
                        float(det[4]),
                        None,
                        int(det[6]),
                    )
                    for det in detections
                ]

        if len(results) < len(detections) and not self._single_subject_mode:
            from zebtrack.tracker.basetrack import BaseTrack

            log.warning(
                "single_detector.bytetrack.fallback_simple_ids",
                num_tracks=len(results),
                num_detections=len(detections),
                reason="bytetrack_returned_fewer_tracks_than_detections",
            )
            results = [
                (
                    int(det[0]),
                    int(det[1]),
                    int(det[2]),
                    int(det[3]),
                    float(det[4]),
                    BaseTrack.next_id(),
                    int(det[6]),
                )
                for det in detections
            ]

        # Re-filter tracked positions by polygon
        if self.zone_scaler.scaled_polygon.size > 0:
            results_before_filter = len(results)
            filtered_results = []
            for det in results:
                x1, y1, x2, y2 = det[0], det[1], det[2], det[3]
                is_inside = self.zone_scaler.is_inside_polygon(
                    x1, y1, x2, y2, self.zone_scaler.scaled_polygon
                )
                if is_inside:
                    filtered_results.append(det)
                else:
                    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
                    log.warning(
                        "single_detector.bytetrack.post_filter_rejected",
                        bbox=(x1, y1, x2, y2),
                        center=(center_x, center_y),
                        track_id=det[5],
                        reason="track_outside_polygon",
                    )

            results = filtered_results
            filtered_count = results_before_filter - len(results)
            if filtered_count > 0:
                log.info(
                    "single_detector.bytetrack.post_filter_applied",
                    before=results_before_filter,
                    after=len(results),
                    filtered_out=filtered_count,
                    reason=("tracks_moved_outside_polygon_by_kalman_filter"),
                )

        return results

    def _ensure_byte_tracker(self) -> BYTETracker | None:
        """Ensure ByteTracker is initialized with current settings."""
        pp = DetectionPostProcessor
        track_thresh = pp.get_track_threshold(self.settings, self.plugin)
        match_thresh = pp.get_match_threshold(self.settings, self.plugin)
        track_buffer = pp.get_track_buffer(self.settings, self.plugin)
        max_center_distance = pp.get_max_center_distance(self.settings)
        iou_threshold = pp.get_iou_threshold(self.settings)
        use_bytetrack = pp.should_use_bytetrack(self.settings)
        single_animal_mode = pp.get_single_animal_mode(self.settings, self._single_subject_mode)

        params = (
            track_thresh,
            match_thresh,
            track_buffer,
            max_center_distance,
            iou_threshold,
            single_animal_mode,
            use_bytetrack,
        )
        if self._byte_tracker is not None and self._byte_tracker_params == params:
            return self._byte_tracker

        if not use_bytetrack:
            return None

        try:
            args = SimpleNamespace(
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                mot20=False,
            )

            processing_interval = pp.get_processing_interval(self.settings)
            frame_rate = pp.get_fps(self.settings)

            log.info(
                "single_detector.bytetrack.initializing",
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                max_center_distance=max_center_distance,
                iou_threshold=iou_threshold,
                use_hybrid_matching=True,
                processing_interval=processing_interval,
                single_animal_mode=single_animal_mode,
            )

            self._byte_tracker = BYTETracker(
                args=args,
                frame_rate=frame_rate,
                use_hybrid_matching=True,
                max_center_distance=max_center_distance,
                processing_interval=processing_interval,
                iou_threshold=iou_threshold,
                single_animal_mode=single_animal_mode,
            )
            self._byte_tracker_params = params
        except Exception:  # pragma: no cover - defensive
            log.warning("single_detector.bytetrack.init_failed", exc_info=True)
            self._byte_tracker = None
            self._byte_tracker_params = None

        return self._byte_tracker

    def _ensure_simple_tracker(self) -> SingleSubjectTracker:
        """Ensure SingleSubjectTracker is up to date with settings."""
        pp = DetectionPostProcessor
        iou_thresh = pp.get_iou_threshold(self.settings)
        max_dist = pp.get_max_center_distance(self.settings)

        if (
            self._single_subject_tracker.iou_threshold != iou_thresh
            or self._single_subject_tracker.max_center_distance != max_dist
        ):
            log.info(
                "single_detector.simple_tracker.updating",
                iou=iou_thresh,
                dist=max_dist,
            )
            self._single_subject_tracker = SingleSubjectTracker(
                track_id=1,
                iou_threshold=iou_thresh,
                max_center_distance=max_dist,
            )
        return self._single_subject_tracker

    # =========================================================================
    # Overlay drawing
    # =========================================================================

    def draw_overlay(self, frame: np.ndarray, detections: list[tuple]) -> None:
        """Draw detection overlays on the frame.

        Args:
            frame: Input BGR frame (modified in-place).
            detections: List of detection tuples to draw.
        """
        # Draw the ROI polygons
        for i, polygon in enumerate(self.zone_scaler.scaled_roi_polygons):
            if i < len(self.roi_colors):
                color = self.roi_colors[i]
                cv2.polylines(
                    frame,
                    [polygon],
                    isClosed=True,
                    color=color,
                    thickness=2,
                )

        # Draw the processing area polygon
        if self.zone_scaler.scaled_polygon.size > 0:
            cv2.polylines(
                frame,
                [self.zone_scaler.scaled_polygon],
                isClosed=True,
                color=(0, 0, 0),
                thickness=1,
            )

        # Draw the bounding boxes for detections
        for detection in detections:
            if len(detection) == 6:
                x1, y1, x2, y2, confidence, track_id = detection
            else:
                x1, y1, x2, y2, confidence, track_id, _ = detection
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
            label = f"ID: {track_id} ({int(confidence * 100)}%)"
            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2,
            )

    def _draw_zones(self, frame: np.ndarray) -> None:
        """Lightweight zone drawing for diagnostic output."""
        if isinstance(self.zones, ZoneData):
            colors = getattr(self.zones, "roi_colors", [])
            log.debug("single_detector.drawing.single", rois=len(colors))

    # =========================================================================
    # Batch detection
    # =========================================================================

    def detect_batch(
        self,
        frames: list[np.ndarray],
        batch_size: int = 4,
    ) -> list[list[tuple]]:
        """Process multiple frames in batches for offline analysis.

        This method is for single-aquarium mode. For multi-aquarium,
        use MultiAquariumDetector.detect_partitioned_optimized() per frame.

        Args:
            frames: List of BGR frames to process.
            batch_size: Number of frames to process per batch.

        Returns:
            List of detection lists, one per input frame.
        """
        import time

        if not frames:
            return []

        all_results: list[list[tuple]] = []
        start_time = time.perf_counter()

        for i in range(0, len(frames), batch_size):
            batch = frames[i : i + batch_size]

            if hasattr(self.plugin, "detect_batch") and callable(
                getattr(self.plugin, "detect_batch", None)
            ):
                batch_detections = self.plugin.detect_batch(batch)
            else:
                batch_detections = [self.plugin.detect(frame) for frame in batch]

            for frame_detections in batch_detections:
                processed = []
                for det in frame_detections:
                    det = DetectionPostProcessor.ensure_track_tuple(det)
                    processed.append(det)

                if self._byte_tracker is not None and processed:
                    frame_shape_cached = (
                        self._last_height or 720,
                        self._last_width or 1280,
                        3,
                    )
                    tracked = self._apply_byte_tracking(processed, frame_shape_cached)
                else:
                    tracked = processed

                all_results.append(tracked)

        elapsed = time.perf_counter() - start_time
        log.info(
            "single_detector.batch.complete",
            total_frames=len(frames),
            batch_size=batch_size,
            elapsed_ms=round(elapsed * 1000, 2),
            avg_ms_per_frame=(round(elapsed * 1000 / len(frames), 2) if frames else 0),
        )

        return all_results

    # =========================================================================
    # State restoration
    # =========================================================================

    def _restore_trackers(self, previous_state: dict[str, Any]) -> None:
        """Restore tracker states from a previous state dictionary.

        Args:
            previous_state: Dict with tracker state to restore.
        """
        # Restore ByteTracker state
        if "byte_tracker_state" in previous_state and self._byte_tracker is not None:
            if hasattr(self._byte_tracker, "restore_state"):
                self._byte_tracker.restore_state(  # type: ignore[attr-defined]
                    previous_state["byte_tracker_state"]
                )
            log.debug("single_detector.restore_trackers.byte_tracker_restored")

        # Restore global track ID counter
        if "basetrack_id_counter" in previous_state:
            from zebtrack.tracker.basetrack import BaseTrack

            BaseTrack.set_id_counter(previous_state["basetrack_id_counter"])
            log.debug(
                "single_detector.restore_trackers.basetrack_id_counter_restored",
                counter=previous_state["basetrack_id_counter"],
            )

        log.info("single_detector.restore_trackers.completed")

    # =========================================================================
    # Data accessors
    # =========================================================================

    def get_zone_data(self) -> ZoneData:
        """Helper to get current zone configuration as ZoneData object."""
        if hasattr(self.zones, "to_zone_data"):
            return self.zones.to_zone_data(0)  # type: ignore[union-attr]
        return self.zones  # type: ignore[return-value]

    def bbox_hits_roi_polygon(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        roi_polygon: np.ndarray,
    ) -> bool:
        """Delegate ROI polygon check to zone_scaler."""
        return self.zone_scaler.bbox_hits_roi_polygon(x1, y1, x2, y2, roi_polygon)
