"""Lightweight tracker that assigns a stable track ID in single-subject mode."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

Detection = tuple[int, int, int, int, float, int | None, int]
TrackedDetection = tuple[int, int, int, int, float, int, int]


class SingleSubjectTracker:
    """Assigns a fixed track ID to the most plausible detection in each frame."""

    def __init__(self, track_id: int = 1, iou_threshold: float = 0.3) -> None:
        self.track_id = int(track_id)
        self.iou_threshold = float(iou_threshold)
        self._last_bbox: tuple[int, int, int, int] | None = None

    def reset(self) -> None:
        """Forget any previously tracked bounding box."""

        self._last_bbox = None

    def assign(self, detections: Sequence[Detection]) -> list[TrackedDetection]:
        """Return the best candidate annotated with the stable ``track_id``.

        When multiple detections are available, prefer the one that overlaps the
        previous selection. If none overlap sufficiently, fall back to the highest
        confidence detection.
        """

        if not detections:
            self._last_bbox = None
            return []

        normalised = [self._normalise_detection(det) for det in detections]

        selected = None
        if self._last_bbox is not None:
            best_by_iou = max(normalised, key=lambda det: self._compute_iou(det[:4]))
            best_iou = self._compute_iou(best_by_iou[:4])
            if best_iou >= self.iou_threshold:
                selected = best_by_iou

        if selected is None:
            selected = max(normalised, key=lambda det: det[4])

        bbox = selected[:4]
        confidence = selected[4]
        class_id = selected[6]
        self._last_bbox = bbox
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
