"""Detection post-processing utilities for zebrafish tracking.

Stateless utility functions for frame validation, detection tuple normalization,
coordinate offset, IoU calculation, class ID resolution, and settings extraction.
Used by both SingleDetector and MultiAquariumDetector.
"""

from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

if TYPE_CHECKING:
    from zebtrack.plugins.base import DetectorPlugin
    from zebtrack.settings import Settings

log = structlog.get_logger()

__all__ = ["DetectionPostProcessor"]


class DetectionPostProcessor:
    """Stateless post-processing utilities for detection pipeline.

    All methods are static — no instance state is needed. This class groups
    related utilities for frame validation, tuple normalization, coordinate
    adjustment, IoU math, class ID resolution, and settings extraction.
    """

    @staticmethod
    def validate_frame(frame: np.ndarray) -> None:
        """Validate that a frame is a valid BGR numpy array.

        Args:
            frame: Input frame to validate.

        Raises:
            ValueError: If frame is None, empty, or not HxWx3.
        """
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")
        if frame.size == 0:
            raise ValueError("Frame cannot be empty")
        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3, got {frame.shape}")

    @staticmethod
    def ensure_track_tuple(
        detection: tuple,
    ) -> tuple[float, float, float, float, float, int | None, int]:
        """Normalize a detection tuple to 7-element format.

        Handles 5-element (no track_id, no class_id), 6-element (no class_id),
        and 7+ element detection tuples.

        Args:
            detection: Detection tuple of varying length.

        Returns:
            Normalized 7-element tuple: (x1, y1, x2, y2, confidence, track_id, class_id).
        """
        if len(detection) == 5:
            x1, y1, x2, y2, confidence = detection
            track_id = None
            class_id = 0  # Default class if not provided
        elif len(detection) == 6:
            x1, y1, x2, y2, confidence, track_id = detection
            class_id = 0  # Default class if not provided
        else:
            x1, y1, x2, y2, confidence, track_id, class_id = detection[:7]
        return (
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(confidence),
            track_id,
            int(class_id),
        )

    @staticmethod
    def offset_detections(
        raw_detections: list,
        dx: int,
        dy: int,
    ) -> list[tuple[float, float, float, float, float, int, int]]:
        """Offset detection coordinates by (dx, dy).

        Used after cropping a frame sub-region to adjust coordinates
        back to the full frame coordinate system.

        Args:
            raw_detections: List of raw detection tuples.
            dx: Horizontal offset.
            dy: Vertical offset.

        Returns:
            List of offset detection tuples in 7-element format.
        """
        preds: list[tuple[float, float, float, float, float, int, int]] = []
        for det in raw_detections:
            x1_c, y1_c, x2_c, y2_c, conf, tid, cid = DetectionPostProcessor.ensure_track_tuple(det)
            preds.append(
                (
                    float(x1_c + dx),
                    float(y1_c + dy),
                    float(x2_c + dx),
                    float(y2_c + dy),
                    float(conf),
                    int(tid) if tid is not None else -1,
                    int(cid),
                )
            )
        return preds

    @staticmethod
    def calculate_iou(
        x1_a: float,
        y1_a: float,
        x2_a: float,
        y2_a: float,
        x1_b: float,
        y1_b: float,
        x2_b: float,
        y2_b: float,
    ) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes.

        Args:
            x1_a: Left x of box A.
            y1_a: Top y of box A.
            x2_a: Right x of box A.
            y2_a: Bottom y of box A.
            x1_b: Left x of box B.
            y1_b: Top y of box B.
            x2_b: Right x of box B.
            y2_b: Bottom y of box B.

        Returns:
            IoU value between 0.0 and 1.0.
        """
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

    @staticmethod
    def apply_class_mismatch_fallback(
        detections: list[tuple],
        scaled_polygon: np.ndarray,
        aquarium_class_id: int | None,
        animal_class_id: int | None,
    ) -> list[tuple]:
        """Convert small aquarium-class detections into animal-class detections.

        When the model detects an object as "aquarium" but it's small relative
        to the arena, it's likely actually a fish. This corrects the class ID.

        Args:
            detections: List of detection tuples.
            scaled_polygon: Scaled arena polygon for area comparison.
            aquarium_class_id: Class ID for aquarium detections.
            animal_class_id: Class ID for animal detections.

        Returns:
            List of detections with corrected class IDs.
        """
        if (
            not detections
            or scaled_polygon.size == 0
            or aquarium_class_id is None
            or animal_class_id is None
        ):
            return detections

        arena_area = cv2.contourArea(scaled_polygon)
        if arena_area <= 0:
            return detections

        adjusted: list[tuple] = []
        for det in detections:
            x1, y1, x2, y2, conf, track_id, class_id = det
            if class_id == aquarium_class_id:
                det_area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
                if det_area / arena_area < 0.5:
                    class_id = animal_class_id
            adjusted.append((x1, y1, x2, y2, conf, track_id, class_id))

        return adjusted

    @staticmethod
    def validate_track_continuity(detections: list[tuple]) -> None:
        """Validate track_id continuity and log warnings for gaps.

        Detects missing track IDs which may indicate tracking issues
        or object loss. This helps identify potential problems with ByteTracker.

        Args:
            detections: List of (x1, y1, x2, y2, confidence, track_id, class_id) tuples.
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
                "post_processor.track_id_gaps_detected",
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

        # Additional validation: Check for duplicate track_ids
        if len(track_ids) != len(actual_ids):
            duplicate_ids = [tid for tid in actual_ids if track_ids.count(tid) > 1]
            log.error(
                "post_processor.duplicate_track_ids",
                duplicate_track_ids=duplicate_ids,
                total_detections=len(detections),
                message="Multiple detections with same track_id in single frame!",
            )

    @staticmethod
    def resolve_class_ids(
        plugin: "DetectorPlugin",
    ) -> tuple[int, int]:
        """Resolve class IDs from plugin metadata.

        Inspects the plugin's class_names mapping to determine which class IDs
        correspond to aquariums and animals.

        Args:
            plugin: Detector plugin instance with class_names attribute.

        Returns:
            Tuple of (aquarium_class_id, animal_class_id).
        """
        aquarium_class_id = 0
        animal_class_id = 1

        if hasattr(plugin, "class_names") and plugin.class_names:
            aquarium_names = ["aqua", "aquarium", "tank", "agua"]
            animal_names = ["zebrafish", "fish", "peixe"]

            found_aquarium = False
            found_animal = False

            for cid, name in plugin.class_names.items():
                name_lower = name.lower()
                if name_lower in aquarium_names:
                    aquarium_class_id = cid
                    found_aquarium = True
                if name_lower in animal_names:
                    animal_class_id = cid
                    found_animal = True

            # If we found an animal class at 0 but no aquarium class,
            # likely a single-class model
            if found_animal and not found_aquarium and animal_class_id == 0:
                # Ensure we don't overlap if we default aquarium to 0
                aquarium_class_id = -1  # effectively disable aquarium detection by ID

            log.info(
                "post_processor.class_ids.resolved",
                aquarium_id=aquarium_class_id,
                animal_id=animal_class_id,
                plugin_classes=plugin.class_names,
            )

        return aquarium_class_id, animal_class_id

    # =========================================================================
    # Settings resolution helpers
    # =========================================================================

    @staticmethod
    def get_track_threshold(settings: "Settings | None", plugin: "DetectorPlugin | None") -> float:
        """Get track threshold from plugin or settings.

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Track threshold value (default: 0.25).
        """
        if plugin is not None:
            value = getattr(plugin, "track_threshold", None)
            if value is not None:
                return float(value)
        if settings and hasattr(settings, "bytetrack"):
            return float(getattr(settings.bytetrack, "track_threshold", 0.25))
        return 0.25  # Default matching config.yaml

    @staticmethod
    def get_match_threshold(settings: "Settings | None", plugin: "DetectorPlugin | None") -> float:
        """Get match threshold from plugin or settings.

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Match threshold value (default: 0.95).
        """
        if plugin is not None:
            value = getattr(plugin, "match_threshold", None)
            if value is not None:
                return float(value)
        if settings and hasattr(settings, "bytetrack"):
            return float(getattr(settings.bytetrack, "match_threshold", 0.95))
        return 0.95

    @staticmethod
    def get_track_buffer(settings: "Settings | None", plugin: "DetectorPlugin | None") -> int:
        """Get track buffer size from settings or plugin.

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Track buffer size (default: 150).
        """
        if plugin is not None:
            value = getattr(plugin, "track_buffer", None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 150
        if settings and hasattr(settings, "bytetrack"):
            return int(getattr(settings.bytetrack, "track_buffer", 150))
        return 150

    @staticmethod
    def get_max_center_distance(settings: "Settings | None") -> float:
        """Get max center distance for hybrid matching.

        This parameter controls how far (in pixels) a detection can be from
        the predicted track position and still be considered a match.

        Args:
            settings: Application settings (optional).

        Returns:
            Max center distance in pixels (default: 400.0).
        """
        if settings and hasattr(settings, "bytetrack"):
            return float(getattr(settings.bytetrack, "max_center_distance", 400.0))
        return 400.0

    @staticmethod
    def get_iou_threshold(settings: "Settings | None") -> float:
        """Get IoU threshold for hybrid matching.

        Lower values make the tracker prefer center distance over IoU,
        which is better for small, fast-moving objects.

        Args:
            settings: Application settings (optional).

        Returns:
            IoU threshold (default: 0.05).
        """
        if settings and hasattr(settings, "bytetrack"):
            return float(getattr(settings.bytetrack, "iou_threshold", 0.05))
        return 0.05

    @staticmethod
    def should_use_bytetrack(settings: "Settings | None") -> bool:
        """Check if ByteTrack should be used based on settings.

        Args:
            settings: Application settings (optional).

        Returns:
            True if ByteTrack is enabled (default: True).
        """
        if settings and hasattr(settings, "tracking"):
            return settings.tracking.use_bytetrack
        return True

    @staticmethod
    def get_processing_interval(settings: "Settings | None") -> int:
        """Get processing interval from settings.

        Args:
            settings: Application settings (optional).

        Returns:
            Processing interval in frames (default: 1).
        """
        if settings and hasattr(settings, "video_processing"):
            return getattr(settings.video_processing, "processing_interval", 1) or 1
        return 1

    @staticmethod
    def get_fps(settings: "Settings | None") -> int:
        """Get FPS from settings.

        Args:
            settings: Application settings (optional).

        Returns:
            Frames per second (default: 30).
        """
        if settings and hasattr(settings, "video_processing"):
            return getattr(settings.video_processing, "fps", 30) or 30
        return 30

    @staticmethod
    def get_single_animal_mode(settings: "Settings | None", explicit_mode: bool) -> bool:
        """Determine single_animal_mode for ByteTracker.

        Priority: explicit mode flag > global settings.

        Args:
            settings: Application settings (optional).
            explicit_mode: Explicit single-subject mode flag.

        Returns:
            True if single animal mode should be enabled.
        """
        if explicit_mode:
            return True
        if settings and hasattr(settings, "video_processing"):
            return getattr(settings.video_processing, "single_animal_per_aquarium", False)
        return False
