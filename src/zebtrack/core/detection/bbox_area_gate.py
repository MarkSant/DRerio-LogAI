"""Runaway-bbox gate: rejects detections whose box has exploded in size.

Why this exists
---------------
The live pipeline calls ``detect`` with a deliberately permissive
``conf_threshold=0.05`` and, before this module, nothing anywhere bounded the
SIZE of an animal detection — the only area gates in the codebase belonged to
aquarium detection and never reached the tracking path.

Once the tracker loses the animal, YOLO commonly keeps emitting a box that
swells over reflections, shadows or the whole tank. The consequences are not
cosmetic:

- the oversized box is written straight into ``3_CoordMovimento``, corrupting
  distance, speed and ROI occupancy for the rest of the session;
- the tracker may latch onto it, so the bad box persists across frames;
- in a closed-loop setup it drives the edge-triggered Arduino ROI dispatch,
  delivering a stimulus for an animal that is not where the box claims.

The gate compares against a ROLLING MEDIAN of recently accepted areas rather
than an absolute pixel size, so a single threshold works across species, zoom
levels and camera distances without per-project tuning.
"""

from __future__ import annotations

import statistics
from collections import deque

import structlog

log = structlog.get_logger()

__all__ = ["BboxAreaGate"]

# Fallbacks matching ``YOLOModelSettings``' declared defaults, used when no
# Settings object is available (``settings_obj`` is optional on both detectors).
DEFAULT_RATIO_MAX = 3.0
DEFAULT_WINDOW = 30
DEFAULT_WARMUP = 10


class BboxAreaGate:
    """Rolling-median size filter for one detection stream.

    One instance per independent stream: a single detector owns one, while the
    multi-aquarium detector owns one PER AQUARIUM (different crops mean
    different apparent scales, so their areas are not comparable).

    Design notes:

    - **Median, not mean.** The runaway frames are precisely the outliers the
      statistic has to survive. A mean would be dragged upward by them until the
      gate silently stopped rejecting anything.
    - **Warmup.** Below ``warmup`` samples the median is not trustworthy, so
      everything passes. A cold statistic must never discard real data.
    - **Upper bound only.** A too-small box is a missed detection, not a
      corrupted one, and small boxes are legitimate when the animal is far away
      or partly occluded. The user explicitly did not ask for a minimum.
    - **Only accepted areas are remembered**, so a burst of runaway frames
      cannot inflate the very baseline meant to reject it.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        ratio_max: float = DEFAULT_RATIO_MAX,
        window: int = DEFAULT_WINDOW,
        warmup: int = DEFAULT_WARMUP,
        label: str = "",
    ) -> None:
        self.enabled = enabled
        self.ratio_max = ratio_max
        self.warmup = warmup
        self.label = label
        self._areas: deque[float] = deque(maxlen=max(2, window))
        self._rejections = 0

    @classmethod
    def from_settings(cls, settings_obj: object | None, *, label: str = "") -> BboxAreaGate:
        """Build a gate from ``settings.yolo_model``, tolerating partial configs.

        ``settings_obj`` may be ``None`` (both detectors accept that) and an
        older ``config.yaml`` will not carry the new keys, so every field falls
        back to the declared default rather than raising.
        """
        yolo = getattr(settings_obj, "yolo_model", None)
        return cls(
            enabled=bool(getattr(yolo, "bbox_area_gate_enabled", True)),
            ratio_max=float(getattr(yolo, "bbox_area_median_ratio_max", DEFAULT_RATIO_MAX)),
            window=int(getattr(yolo, "bbox_area_history_window", DEFAULT_WINDOW)),
            warmup=int(getattr(yolo, "bbox_area_gate_warmup", DEFAULT_WARMUP)),
            label=label,
        )

    @property
    def rejections(self) -> int:
        """How many detections this gate has rejected since the last reset."""
        return self._rejections

    @property
    def sample_count(self) -> int:
        """How many accepted areas currently back the median."""
        return len(self._areas)

    def reset(self) -> None:
        """Forget history so the next video re-learns its own baseline.

        Areas are only comparable within one framing. Carrying them across
        videos would let a previous session's scale reject the new one's valid
        detections during exactly the window where the gate has no data of its
        own.
        """
        self._areas.clear()
        self._rejections = 0

    def filter(self, detections: list[tuple]) -> list[tuple]:
        """Return the detections that pass the gate, preserving input order.

        Each detection is a tuple whose first four entries are ``x1, y1, x2, y2``.
        """
        if not self.enabled or not detections:
            return detections

        kept: list[tuple] = []
        for det in detections:
            area = abs(float(det[2]) - float(det[0])) * abs(float(det[3]) - float(det[1]))
            if area <= 0:
                # Degenerate box: no width or height. Never feed it to the
                # median (it would drag the baseline to zero and make the gate
                # reject everything afterwards).
                continue

            if len(self._areas) >= self.warmup:
                median_area = statistics.median(self._areas)
                if median_area > 0 and area > median_area * self.ratio_max:
                    self._rejections += 1
                    # A runaway box persists for hundreds of consecutive frames;
                    # one log line per frame would bury the rest of the session.
                    # Report the first, then every 100th.
                    if self._rejections == 1 or self._rejections % 100 == 0:
                        log.warning(
                            "detector.bbox_area_gate.rejected",
                            label=self.label,
                            area=area,
                            median_area=median_area,
                            ratio=area / median_area,
                            ratio_max=self.ratio_max,
                            total_rejections=self._rejections,
                        )
                    continue

            self._areas.append(area)
            kept.append(det)

        return kept
