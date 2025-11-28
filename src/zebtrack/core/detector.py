"""Detection coordination module for zebrafish tracking.

Manages the detection process by delegating to detector plugins and handling
stateful logic for zone tracking, ROI filtering, and overlay rendering.
"""

import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

from zebtrack.core.single_subject_tracker import SingleSubjectTracker
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.tracker.byte_tracker import BYTETracker

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: list[list[int]] = field(default_factory=list)
    roi_polygons: list[list[list[int]]] = field(default_factory=list)
    roi_names: list[str] = field(default_factory=list)
    roi_colors: list[tuple[int, int, int]] = field(default_factory=list)


class Detector:
    """
    Manages the detection process by delegating to a plugin and handling
    stateful logic for zone tracking.

    Nota de Otimização:
    O rastreamento de objetos é baseado nos bounding boxes. Se o modelo de IA
    carregado for um modelo de segmentação (*_seg.pt), ele realizará a
    tarefa computacionalmente mais custosa de encontrar máscaras de pixel,
    mesmo que apenas os bounding boxes sejam usados. Para um desempenho
    ótimo no rastreamento, um modelo treinado apenas para DETECÇÃO (que
    gera somente bounding boxes) deve ser usado em futuras versões.
    """

    def __init__(
        self,
        plugin: DetectorPlugin,
        base_width: int = 1280,
        base_height: int = 720,
        settings_obj: "Settings | None" = None,
    ):
        """
        Initialize the detector with a specific plugin.

        Args:
            plugin (DetectorPlugin): An instantiated detector plugin.
            base_width (int): The reference width the zones were defined on.
            base_height (int): The reference height the zones were defined on.
            settings_obj: Settings instance (injected, optional for backward compatibility).
        """
        self.plugin = plugin
        if not self.plugin:
            log.error("detector.init.no_plugin")
            raise ValueError("Detector must be initialized with a valid plugin.")

        self.settings = settings_obj
        self.base_width = base_width
        self.base_height = base_height
        log.info("detector.init.success", plugin=self.plugin.get_name())

        # Zone configuration is now set dynamically via set_zones()
        self.zones: ZoneData = ZoneData()
        self.scaled_polygon: np.ndarray = np.array([])
        self.scaled_roi_polygons: list[np.ndarray] = []
        self._scaling_cache: dict = {}
        """Caches scaled zone polygons to avoid recalculation for each frame of the same size."""
        self._single_subject_mode = False
        self._single_subject_tracker = SingleSubjectTracker()
        self._byte_tracker: BYTETracker | None = None
        self._byte_tracker_params: tuple[float, float, int] | None = None
        self._zones_configured = False
        self._last_width: int | None = None
        self._last_height: int | None = None
        self._context: str = "tracking"
        self._aquarium_region_defined: bool = False

    def set_zones(self, zones: ZoneData, actual_width: int, actual_height: int):
        """
        Set the detection zones and scales them to the current video resolution.

        Args:
            zones (ZoneData): The zone configuration object.
            actual_width (int): The width of the video/camera frame to scale to.
            actual_height (int): The height of the video/camera frame to scale to.
        """
        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(
                "Actual dimensions must be positive. "
                f"set_zones(zones, actual_width={actual_width}, actual_height={actual_height})"
            )

        self.zones = zones
        # Clear cache if zones are redefined, as scaling depends on zone data
        self._scaling_cache.clear()
        self._update_scaling(actual_width, actual_height)
        log.info("detector.zones.set", count=len(self.zones.roi_polygons))
        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height
        self._single_subject_tracker.reset()

    def set_context(self, context: str):
        """
        Set the detection context.

        Args:
            context (str): 'tracking' or 'diagnostic'
        """
        if context in ("tracking", "diagnostic"):
            self._context = context
            log.info("detector.context.set", context=context)

    def set_aquarium_region_defined(self, defined: bool = True):
        """
        Set whether aquarium region has been defined.

        Args:
            defined (bool): True if aquarium region is defined
        """
        self._aquarium_region_defined = bool(defined)
        log.info("detector.aquarium_region_defined.set", defined=defined)

    def _update_scaling(self, actual_width: int, actual_height: int):
        """
        Update the coordinates of the polygon and squares based on the actual video resolution.

        Uses a cache to avoid redundant calculations.
        """
        cache_key = (actual_width, actual_height)
        if cache_key in self._scaling_cache:
            cached_data = self._scaling_cache[cache_key]
            self.scaled_polygon = cached_data["polygon"]
            self.scaled_roi_polygons = cached_data["roi_polygons"]
            log.debug("detector.scaling.cache.hit", key=cache_key)
            return

        # Convert base polygons to numpy arrays for scaling
        base_polygon = np.array(self.zones.polygon, dtype=np.int32)
        base_roi_polygons = [np.array(p, dtype=np.int32) for p in self.zones.roi_polygons]

        # Handle empty polygon case (no zones defined)
        if base_polygon.size == 0:
            self.scaled_polygon = base_polygon
            self.scaled_roi_polygons = base_roi_polygons
        elif actual_width == self.base_width and actual_height == self.base_height:
            self.scaled_polygon = base_polygon
            self.scaled_roi_polygons = base_roi_polygons
        else:
            scale_x = actual_width / self.base_width
            scale_y = actual_height / self.base_height
            self.scaled_polygon = (base_polygon * [scale_x, scale_y]).astype(np.int32)
            self.scaled_roi_polygons = [
                (p * [scale_x, scale_y]).astype(np.int32) for p in base_roi_polygons
            ]

        # Store the newly calculated values in the cache
        self._scaling_cache[cache_key] = {
            "polygon": self.scaled_polygon,
            "roi_polygons": self.scaled_roi_polygons,
        }
        log.info(
            "detector.scaling.updated_and_cached",
            width=actual_width,
            height=actual_height,
        )

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        """
        Check if any of the 4 corners OR the center of the bounding box is inside the polygon.

        Returns False if the polygon is empty or invalid.
        """
        if polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return True

        return False

    def bbox_hits_roi_polygon(
        self, x1: int, y1: int, x2: int, y2: int, roi_polygon: np.ndarray
    ) -> bool:
        """
        Return True if 4 corners OR center of bbox falls within roi_polygon
        (cv2.pointPolygonTest >= 0).

        This is a utility helper for future live ROI checking functionality.
        """
        if roi_polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(roi_polygon, point, False) >= 0:
                return True

        return False

    def detect(self, frame: np.ndarray, project_type: str):
        """Process a single frame for object detection and state tracking."""
        # Task 1.3: Frame validation to prevent crashes with invalid input
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")

        if frame.size == 0:
            raise ValueError("Frame cannot be empty")

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3 (BGR image), got shape {frame.shape}")

        if not self._zones_configured:
            raise RuntimeError(
                "Must call set_zones() before detect(). "
                "Zones need video dimensions for proper scaling."
            )

        if self._last_width is not None and frame.shape[:2] != (
            self._last_height,
            self._last_width,
        ):
            log.warning(
                "detector.dimension_mismatch",
                expected=(self._last_width, self._last_height),
                actual=(frame.shape[1], frame.shape[0]),
                message=(
                    "Frame dimensions differ from dimensions used to set zones. "
                    "This may cause inaccurate detection scaling."
                ),
            )
        start_time = time.perf_counter()

        # Optimization: Crop the frame to the bounding box of the arena polygon
        if self.scaled_polygon.size > 0:
            x, y, w, h = cv2.boundingRect(self.scaled_polygon)
            cropped_frame = frame[y : y + h, x : x + w]

            # 1. Delegate actual detection to the loaded plugin on the cropped frame
            predictions = []
            for det in self.plugin.detect(cropped_frame):
                (
                    x1_crop,
                    y1_crop,
                    x2_crop,
                    y2_crop,
                    conf,
                    track_id,
                    class_id,
                ) = self._ensure_track_tuple(det)
                x1 = x1_crop + x
                y1 = y1_crop + y
                x2 = x2_crop + x
                y2 = y2_crop + y
                predictions.append((x1, y1, x2, y2, conf, track_id, class_id))
        else:
            # Fallback to detecting on the full frame if no polygon is defined
            predictions = [self._ensure_track_tuple(det) for det in self.plugin.detect(frame)]

        # 2. Filter detections to only those inside the main polygon
        # This is still necessary for non-rectangular polygons
        # ✅ FIX: In diagnostic mode without polygon, accept ALL detections
        detections_in_polygon = []
        has_polygon = self.scaled_polygon.size > 0

        if len(predictions) > 0:
            log.info(
                "detector.predictions_before_polygon_filter",
                count=len(predictions),
                has_polygon=has_polygon,
            )

            # 🔍 DEBUG: Log decision flags for polygon filtering
            log.info(
                "detector.polygon_filter_decision_flags",
                has_polygon=has_polygon,
                context=self._context,
                aquarium_defined=self._aquarium_region_defined,
                polygon_size=self.scaled_polygon.size
            )

            import sys
            sys.stderr.write(f"DEBUG: has_polygon={has_polygon}, context={self._context}, aquarium_defined={self._aquarium_region_defined}, polygon_size={self.scaled_polygon.size}\n")

            # ✅ If no polygon defined and in diagnostic mode OR detecting aquarium, accept all detections
            if not has_polygon and (self._context == "diagnostic" or not self._aquarium_region_defined):
                log.info(
                    "detector.no_polygon_accept_all",
                    accepting_all_detections=len(predictions),
                    reason="diagnostic_mode" if self._context == "diagnostic" else "aquarium_detection_phase",
                    context=self._context,
                    aquarium_defined=self._aquarium_region_defined,
                )
                detections_in_polygon = [
                    (int(x1), int(y1), int(x2), int(y2), float(confidence), track_id, int(class_id))
                    for x1, y1, x2, y2, confidence, track_id, class_id in predictions
                ]
            else:
                # Normal polygon filtering
                for det in predictions:
                    x1, y1, x2, y2, confidence, track_id, class_id = det
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    confidence = float(confidence)

                    if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                        detections_in_polygon.append((x1, y1, x2, y2, confidence, track_id, class_id))
                        # 🔍 DEBUG: Log why it passed
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        log.info(
                            "detector.polygon_filter.passed",
                            bbox=(x1, y1, x2, y2),
                            center=(cx, cy),
                            polygon_points=self.scaled_polygon.tolist() if hasattr(self.scaled_polygon, "tolist") else "unknown",
                        )
                    else:
                        log.info(
                            "detector.filtered_outside_polygon",
                            bbox=(x1, y1, x2, y2),
                            track_id=track_id,
                            class_id=class_id,
                        )
        else:
            log.info(
                "detector.no_predictions_from_model",
                has_polygon=has_polygon,
            )

        # Centralized filtering logic based on context
        # 🔍 DEBUG: Log current context during filtering
        log.info(
            "detector.filtering_context_check",
            current_context=self._context,
            detections_in_polygon=len(detections_in_polygon),
            aquarium_defined=self._aquarium_region_defined,
        )

        filtered_detections = []
        if self._context == "diagnostic":
            # Diagnostic mode shows everything
            filtered_detections = detections_in_polygon
            log.info(
                "detector.diagnostic_mode",
                detections_count=len(filtered_detections),
            )
        else:
            # Tracking mode
            # Tracking mode
            aquarium_class_id = 0
            zebrafish_class_id = 1

            log.info(
                "detector.filtering_by_class",
                detections_in_polygon=len(detections_in_polygon),
                aquarium_defined=self._aquarium_region_defined,
                target_class="zebrafish(1)" if self._aquarium_region_defined else "aquarium(0)",
            )

            if not self._aquarium_region_defined:
                # Before arena is defined, show only aquarium detections (class_id 0)
                # ✅ FIX: Also accept Class 1 (Fish) if it's "huge" (likely misclassified tank)
                frame_area = 1280 * 720 # Default fallback
                if self._last_width and self._last_height:
                    frame_area = self._last_width * self._last_height

                for det in detections_in_polygon:
                    # det format: (x1, y1, x2, y2, confidence, track_id, class_id)
                    x1, y1, x2, y2, conf, track_id, class_id = det
                    det_area = (x2 - x1) * (y2 - y1)

                    is_valid_aquarium = False
                    if class_id == aquarium_class_id:
                        is_valid_aquarium = True
                    elif class_id == zebrafish_class_id:
                        # If it's class 1 but HUGE (> 10% of frame), it's likely the tank
                        # Lowered from 30% to 10% based on user logs showing tank is ~15%
                        if det_area > (frame_area * 0.10):
                            is_valid_aquarium = True
                            log.info(
                                "detector.class_fallback_aquarium",
                                bbox=(x1, y1, x2, y2),
                                original_class=class_id,
                                new_class=aquarium_class_id,
                                det_area=det_area,
                                frame_area=frame_area,
                                ratio=det_area/frame_area
                            )
                            # Morph to aquarium class
                            class_id = aquarium_class_id
                            det = (x1, y1, x2, y2, conf, track_id, class_id)

                    if is_valid_aquarium:
                        filtered_detections.append(det)
                    else:
                        log.info(
                            "detector.filtered_by_class",
                            bbox=(det[0], det[1], det[2], det[3]),
                            class_id=class_id,
                            conf=det[4],
                            reason="aquarium_not_defined_target_class_0",
                            det_area=det_area,
                            ratio=det_area/frame_area
                        )
            else:
                # After arena is defined, show only zebrafish detections (class_id 1)
                # ✅ FIX: Handle models that output class 0 for animals
                # If a detection is class 0 BUT is significantly smaller than the arena,
                # treat it as an animal (class 1).

                # Calculate arena area for comparison
                arena_area = 0
                if self.scaled_polygon.size > 0:
                    arena_area = cv2.contourArea(self.scaled_polygon)

                for det in detections_in_polygon:
                    x1, y1, x2, y2, conf, track_id, class_id = det

                    # Calculate detection area
                    det_area = (x2 - x1) * (y2 - y1)

                    # Check if it's a "fake" aquarium (actually an animal)
                    # Criteria: Class 0 AND Area < 50% of arena
                    is_fake_aquarium = False
                    if class_id == aquarium_class_id and arena_area > 0:
                        if det_area < (arena_area * 0.5):
                            is_fake_aquarium = True
                            log.info(
                                "detector.class_fallback_applied",
                                bbox=(x1, y1, x2, y2),
                                original_class=aquarium_class_id,
                                new_class=zebrafish_class_id,
                                det_area=det_area,
                                arena_area=arena_area,
                                ratio=det_area/arena_area
                            )
                            # Modify class_id to zebrafish_class_id for this detection
                            class_id = zebrafish_class_id
                            # Update the tuple in the list (tuples are immutable, so we create new one)
                            det = (x1, y1, x2, y2, conf, track_id, class_id)

                    if class_id == zebrafish_class_id:
                        filtered_detections.append(det)
                    else:
                        log.info(
                            "detector.filtered_by_class",
                            bbox=(det[0], det[1], det[2], det[3]),
                            class_id=class_id,
                            reason="arena_defined",
                        )

        # Apply tracking based on mode
        if self._context == "diagnostic" or not self._aquarium_region_defined:
            # Diagnostic mode OR aquarium detection phase: No tracking, preserve all detections as-is
            # - Diagnostic: single video analysis where we want raw detections
            # - Aquarium detection: need raw aquarium bboxes, ByteTracker would reject them
            filtered_detections = [
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    None,  # No track_id
                    int(class_id),
                )
                for x1, y1, x2, y2, confidence, _, class_id in filtered_detections
            ]
            log.info(
                "detector.skip_tracking",
                num_detections=len(filtered_detections),
                reason="diagnostic_mode" if self._context == "diagnostic" else "aquarium_detection_phase",
                context=self._context,
                aquarium_defined=self._aquarium_region_defined,
            )
        elif self._single_subject_mode:
            # Single subject tracking (lightweight)
            filtered_detections = self._single_subject_tracker.assign(filtered_detections)
            log.info(
                "detector.single_subject_tracking.applied",
                num_detections=len(filtered_detections),
            )
        else:
            # Multi-subject tracking with ByteTracker
            # 🔄 DEBUG: Log confidence of input detections
            if filtered_detections:
                confidences = [d[4] for d in filtered_detections]
                log.info("detector.bytetrack.input_confidences", confidences=confidences)

            filtered_detections = self._apply_byte_tracking(filtered_detections, frame.shape)
            log.info(
                "detector.byte_tracking.applied",
                num_detections=len(filtered_detections),
            )

            # BUG FIX #1: Validate track_id continuity after tracking
            self._validate_track_continuity(filtered_detections)

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        # 🔍 INFO: Log final detection count before return
        log.info(
            "detector.detect.final_result",
            num_detections=len(filtered_detections),
            context=self._context,
            single_subject_mode=self._single_subject_mode,
        )

        # The command logic has been removed as it was tied to the old square ROIs
        command_to_send = None
        return filtered_detections, command_to_send

    def set_single_subject_mode(self, enabled: bool) -> None:
        """Toggle lightweight single-subject tracking."""
        enabled = bool(enabled)
        if self._single_subject_mode == enabled:
            log.debug(
                "detector.single_subject_mode.unchanged",
                enabled=enabled,
            )
            return

        self._single_subject_mode = enabled
        self._single_subject_tracker.reset()
        log.info(
            "detector.single_subject_mode.changed",
            enabled=enabled,
            previous=not enabled,
        )

        if hasattr(self.plugin, "set_use_single_subject_mode"):
            try:
                self.plugin.set_use_single_subject_mode(enabled)
                log.info(
                    "detector.single_subject_mode.plugin_updated",
                    enabled=enabled,
                )
            except Exception:  # pragma: no cover - defensive
                log.warning(
                    "detector.single_subject_mode.plugin_update_failed",
                    enabled=enabled,
                    exc_info=True,
                )

    def is_single_subject_mode(self) -> bool:
        """Expose the current single-subject tracking flag."""
        return self._single_subject_mode

    def reset_tracking_state(self) -> None:
        """Reset tracker state between videos."""
        if hasattr(self.plugin, "reset_tracking_state"):
            try:
                self.plugin.reset_tracking_state()
            except Exception:  # pragma: no cover - defensive
                log.warning("detector.reset_tracking_state.plugin_failed", exc_info=True)
        self._single_subject_tracker.reset()
        self._byte_tracker = None
        self._byte_tracker_params = None

    def clear_cache(self):
        """Clear the internal scaling cache to free memory."""
        self._scaling_cache.clear()
        log.debug("detector.cache.cleared")

    @staticmethod
    def _ensure_track_tuple(detection):
        if len(detection) == 5:
            x1, y1, x2, y2, confidence = detection
            track_id = None
            class_id = 0  # Default class if not provided
        elif len(detection) == 6:
            x1, y1, x2, y2, confidence, track_id = detection
            class_id = 0  # Default class if not provided
        else:
            x1, y1, x2, y2, confidence, track_id, class_id = detection[:7]
        return x1, y1, x2, y2, float(confidence), track_id, int(class_id)

    def _apply_byte_tracking(
        self, detections: list[tuple], frame_shape: tuple[int, int, int]
    ) -> list[tuple]:
        # 🔍 INFO: Log ByteTrack input
        log.info(
            "detector.bytetrack.input",
            num_detections=len(detections),
            frame_shape=frame_shape,
        )

        if not detections:
            tracker = self._ensure_byte_tracker()
            if tracker is not None:
                empty = np.empty((0, 5), dtype=np.float32)
                tracker.update(
                    empty,
                    (frame_shape[0], frame_shape[1]),
                    self._resolve_model_input_shape(),
                )
            log.info("detector.bytetrack.output", num_tracks=0, reason="no_input_detections")
            return []

        tracker = self._ensure_byte_tracker()
        if tracker is None:
            log.warning("detector.bytetrack.tracker_init_failed")
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
                for x1, y1, x2, y2, confidence, _, class_id in detections
            ]

        det_array = np.array(
            [
                [float(x1), float(y1), float(x2), float(y2), float(confidence)]
                for x1, y1, x2, y2, confidence, _, _ in detections
            ],
            dtype=np.float32,
        )

        log.info(
            "detector.bytetrack.calling_update",
            det_array_shape=det_array.shape,
            frame_dims=(frame_shape[0], frame_shape[1]),
            model_input_shape=self._resolve_model_input_shape(),
        )

        tracks = tracker.update(
            det_array,
            (frame_shape[0], frame_shape[1]),
            self._resolve_model_input_shape(),
        )

        log.info(
            "detector.bytetrack.update_result",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
        )

        # Create a proper mapping of tracks to class_ids based on IoU with original detections
        # Build a mapping: track bbox -> best matching detection's class_id
        results: list[tuple] = []
        for track in tracks:
            track_bbox = track.tlbr  # (x1, y1, x2, y2)

            # Find the detection with highest IoU overlap with this track
            best_iou = 0.0
            best_class_id = 0  # Default class

            for det in detections:
                det_x1, det_y1, det_x2, det_y2, _, _, det_class_id = det

                # Calculate IoU between track bbox and detection bbox
                iou = self._calculate_iou(
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

            # Use the class_id from the best matching detection
            x1, y1, x2, y2 = track_bbox
            results.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(track.score),
                    int(track.track_id),
                    int(best_class_id),
                )
            )

        # 🔍 INFO: Log final ByteTrack output
        log.info(
            "detector.bytetrack.output",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
            num_results=len(results),
        )

        return results

    def _validate_track_continuity(self, detections: list[tuple]) -> None:
        """
        Validate track_id continuity and log warnings for gaps.

        BUG FIX #1: Detects missing track IDs which may indicate tracking issues
        or object loss. This helps identify potential problems with ByteTracker.

        Args:
            detections: List of (x1, y1, x2, y2, confidence, track_id, class_id) tuples
        """
        if not detections:
            return

        # Extract track_ids, filtering out None values
        track_ids = [d[5] for d in detections if d[5] is not None]

        if not track_ids:
            return  # No valid track_ids to validate

        # Check for gaps in track_id sequence
        min_id, max_id = min(track_ids), max(track_ids)
        expected_ids = set(range(min_id, max_id + 1))
        actual_ids = set(track_ids)
        missing_ids = expected_ids - actual_ids

        if missing_ids:
            log.warning(
                "detector.track_id_gaps_detected",
                missing_track_ids=sorted(missing_ids),
                present_track_ids=sorted(actual_ids),
                total_detections=len(detections),
                message=(
                    "Gaps in track_id sequence detected. This may indicate: "
                    "(1) Objects temporarily lost by tracker, "
                    "(2) Objects left the frame, or "
                    "(3) ByteTracker configuration issues."
                ),
            )

        # Additional validation: Check for duplicate track_ids (shouldn't happen)
        if len(track_ids) != len(actual_ids):
            duplicate_ids = [tid for tid in actual_ids if track_ids.count(tid) > 1]
            log.error(
                "detector.duplicate_track_ids",
                duplicate_track_ids=duplicate_ids,
                total_detections=len(detections),
                message="Multiple detections with same track_id in single frame!",
            )

    def _calculate_iou(
        self,
        x1_a: float,
        y1_a: float,
        x2_a: float,
        y2_a: float,
        x1_b: float,
        y1_b: float,
        x2_b: float,
        y2_b: float,
    ) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes."""
        # Calculate intersection
        inter_x1 = max(x1_a, x1_b)
        inter_y1 = max(y1_a, y1_b)
        inter_x2 = min(x2_a, x2_b)
        inter_y2 = min(y2_a, y2_b)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)

        # Calculate union
        area_a = (x2_a - x1_a) * (y2_a - y1_a)
        area_b = (x2_b - x1_b) * (y2_b - y1_b)
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0

        return inter_area / union_area

    def _ensure_byte_tracker(self) -> BYTETracker | None:
        track_thresh = self._get_track_threshold()
        match_thresh = self._get_match_threshold()
        track_buffer = self._get_track_buffer()

        params = (track_thresh, match_thresh, track_buffer)
        if self._byte_tracker is not None and self._byte_tracker_params == params:
            return self._byte_tracker

        try:
            args = SimpleNamespace(
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                mot20=False,
            )

            log.info(
                "detector.bytetrack.initializing",
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer
            )

            # Get FPS from settings or use default
            if self.settings and hasattr(self.settings, "video_processing"):
                frame_rate = getattr(self.settings.video_processing, "fps", 30) or 30
            else:
                frame_rate = 30
            self._byte_tracker = BYTETracker(args=args, frame_rate=frame_rate)
            self._byte_tracker_params = params
        except Exception:  # pragma: no cover - defensive
            log.warning("detector.bytetrack.init_failed", exc_info=True)
            self._byte_tracker = None
            self._byte_tracker_params = None

        return self._byte_tracker

    def _get_track_threshold(self) -> float:
        value = getattr(self.plugin, "track_threshold", None)
        if value is None:
            if self.settings and hasattr(self.settings, "bytetrack"):
                return float(getattr(self.settings.bytetrack, "track_threshold", 0.1))
            return 0.1
        return float(value)

    def _get_match_threshold(self) -> float:
        value = getattr(self.plugin, "match_threshold", None)
        if value is None:
            if self.settings and hasattr(self.settings, "bytetrack"):
                return float(getattr(self.settings.bytetrack, "match_threshold", 0.15))
            return 0.15
        return float(value)

    def _get_track_buffer(self) -> int:
        value = getattr(self.plugin, "track_buffer", None)
        if value is None:
            return 60
        try:
            return int(value)
        except (TypeError, ValueError):
            return 60

    def _resolve_model_input_shape(self) -> tuple[int, int]:
        try:
            shape = getattr(self.plugin, "model_input_shape", None)
            if shape and len(shape) == 2:
                return int(shape[0]), int(shape[1])
        except Exception:  # pragma: no cover - defensive
            log.debug("detector.model_input_shape.fallback", exc_info=True)
        return int(self.base_height), int(self.base_width)

    def draw_overlay(self, frame, detections):
        """Draws detection overlays on the frame."""
        # Draw the ROI polygons
        for i, polygon in enumerate(self.scaled_roi_polygons):
            if i < len(self.zones.roi_colors):
                color = self.zones.roi_colors[i]
                cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=2)

        # Draw the processing area polygon
        if self.scaled_polygon.size > 0:
            cv2.polylines(
                frame,
                [self.scaled_polygon],
                isClosed=True,
                color=(0, 0, 0),
                thickness=1,
            )

        # Draw the bounding boxes for detections
        for detection in detections:
            # Handle both 6-element (old) and 7-element (new) tuples
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
