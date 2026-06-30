"""Per-frame ROI occupancy for the live Arduino command loop.

Pure geometry: given the scaled ROI polygons (pixel space, as produced by
``ZoneScaler``) and the centroids of the current frame's detections, returns the
set of ROI names occupied by at least one animal ("any-track" scope).

Reuses ``ZoneScaler.point_in_polygon`` (cv2-based, the same containment test the
detector itself uses) so the occupancy decision matches the detector's
coordinate space exactly and adds no new geometry dependency to the hot loop.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import structlog

from zebtrack.core.detection.zone_scaler import ZoneScaler

log = structlog.get_logger()


class ArduinoRoiEvaluator:
    """Maps detection centroids to the set of occupied ROI names.

    Args:
        roi_names: ROI names, index-aligned with ``roi_polygons``.
        roi_polygons: Scaled ROI polygons in frame-pixel space (e.g.
            ``ZoneScaler.scaled_roi_polygons``). Each is an ``(N, 2)`` array of
            vertices. Empty/degenerate polygons and names without a matching
            polygon are ignored.
    """

    def __init__(
        self,
        roi_names: Sequence[str],
        roi_polygons: Sequence[np.ndarray | Sequence[Sequence[float]]],
    ) -> None:
        self._rois: list[tuple[str, np.ndarray]] = []
        for name, polygon in zip(roi_names, roi_polygons, strict=False):
            poly = np.asarray(polygon, dtype=np.int32)
            if poly.size == 0 or poly.shape[0] < 3:
                continue
            self._rois.append((str(name), poly))

    @property
    def roi_names(self) -> list[str]:
        """ROI names that have a usable polygon."""
        return [name for name, _ in self._rois]

    def has_rois(self) -> bool:
        """True when at least one usable ROI polygon is configured."""
        return bool(self._rois)

    def occupied_rois(self, centroids: Iterable[tuple[float, float]]) -> set[str]:
        """Return the set of ROI names containing at least one centroid.

        Args:
            centroids: ``(x, y)`` points in frame-pixel space (bbox centers).
        """
        occupied: set[str] = set()
        for cx, cy in centroids:
            point = (float(cx), float(cy))
            for name, polygon in self._rois:
                if name in occupied:
                    continue
                if ZoneScaler.point_in_polygon(point, polygon):
                    occupied.add(name)
            if len(occupied) == len(self._rois):
                break  # every ROI already occupied — no need to test more points
        return occupied

    @staticmethod
    def centroid_of_bbox(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
        """Centroid (center point) of a bounding box."""
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
