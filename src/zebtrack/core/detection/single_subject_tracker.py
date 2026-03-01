"""Lightweight tracker that assigns a stable track ID in single-subject mode.

Enhanced in v2.2: Uses a hybrid IoU + distance matching strategy to handle
large inter-frame movements (e.g., when processing every N frames).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

Detection = tuple[int, int, int, int, float, int | None, int]
TrackedDetection = tuple[int, int, int, int, float, int, int]


class SingleSubjectTracker:
    """Assigns a fixed track ID to the most plausible detection in each frame.

    Uses a hybrid matching strategy:
    1. First try IoU-based matching (works when movement is small)
    2. If IoU fails, fall back to center-distance matching (handles large movements)
    3. If distance also fails, use the highest-confidence detection

    This makes the tracker robust to frame skipping scenarios where animals
    can move significantly between processed frames.
    """

    def __init__(
        self,
        track_id: int = 1,
        iou_threshold: float = 0.3,
        max_center_distance: float = 200.0,
    ) -> None:
        """Initialize the single subject tracker.

        Args:
            track_id: The fixed track ID to assign (default: 1).
            iou_threshold: IoU threshold for associating detections (default: 0.3).
            max_center_distance: Maximum center-to-center distance in pixels
                to consider a detection as the same subject (default: 200).
                This is used as a fallback when IoU matching fails.
        """
        self.track_id = int(track_id)
        self.iou_threshold = float(iou_threshold)
        self.max_center_distance = float(max_center_distance)
        self._last_bbox: tuple[int, int, int, int] | None = None
        self._last_center: tuple[float, float] | None = None

    def reset(self) -> None:
        """Forget any previously tracked bounding box."""
        self._last_bbox = None
        self._last_center = None

    def _get_center(self, bbox: tuple[int, int, int, int]) -> tuple[float, float]:
        """Get the center point of a bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _compute_center_distance(self, bbox: tuple[int, int, int, int]) -> float:
        """Compute Euclidean distance between centers of current and last bbox."""
        if self._last_center is None:
            return float("inf")

        cx, cy = self._get_center(bbox)
        last_cx, last_cy = self._last_center
        return math.sqrt((cx - last_cx) ** 2 + (cy - last_cy) ** 2)

    def assign(self, detections: Sequence[Detection]) -> list[TrackedDetection]:
        """Return the best candidate annotated with the stable ``track_id``.

        Uses a hybrid matching strategy:
        1. Try IoU-based matching (works when movement is small)
        2. Fall back to center-distance matching (handles large movements)
        3. If both fail, use highest confidence detection
        """
        if not detections:
            self._last_bbox = None
            self._last_center = None
            return []

        normalised = [self._normalise_detection(det) for det in detections]

        selected = None

        # Strategy 1: Try IoU-based matching
        if self._last_bbox is not None:
            best_by_iou = max(normalised, key=lambda det: self._compute_iou(det[:4]))
            best_iou = self._compute_iou(best_by_iou[:4])
            if best_iou >= self.iou_threshold:
                selected = best_by_iou

        # Strategy 2: Fall back to center-distance matching
        if selected is None and self._last_center is not None:
            best_by_distance = min(
                normalised, key=lambda det: self._compute_center_distance(det[:4])
            )
            best_distance = self._compute_center_distance(best_by_distance[:4])
            if best_distance <= self.max_center_distance:
                selected = best_by_distance

        # Strategy 3: Use highest confidence detection
        if selected is None:
            selected = max(normalised, key=lambda det: det[4])

        bbox = selected[:4]
        confidence = selected[4]
        class_id = selected[6]
        self._last_bbox = bbox
        self._last_center = self._get_center(bbox)
        x1, y1, x2, y2 = bbox
        return [(x1, y1, x2, y2, confidence, self.track_id, class_id)]

    def _normalise_detection(self, detection: Detection) -> Detection:
        # Support both 6-element (old) and 7-element (new) tuples
        if len(detection) == 6:
            x1, y1, x2, y2, confidence, track_id = detection
            class_id = 0  # Default class
        else:
            x1, y1, x2, y2, confidence, track_id, class_id = detection
        return (int(x1), int(y1), int(x2), int(y2), float(confidence), track_id, int(class_id))

    def _compute_iou(self, bbox: Iterable[int]) -> float:
        if self._last_bbox is None:
            return 0.0

        x1, y1, x2, y2 = bbox
        last_x1, last_y1, last_x2, last_y2 = self._last_bbox

        inter_x1 = max(x1, last_x1)
        inter_y1 = max(y1, last_y1)
        inter_x2 = min(x2, last_x2)
        inter_y2 = min(y2, last_y2)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
        area_current = float(max(0, x2 - x1) * max(0, y2 - y1))
        area_last = float(max(0, last_x2 - last_x1) * max(0, last_y2 - last_y1))
        union = area_current + area_last - inter_area
        if union <= 0:
            return 0.0
        return inter_area / union
