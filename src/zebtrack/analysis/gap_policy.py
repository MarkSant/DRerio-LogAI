"""When an interval between two analysed samples stops being continuous.

The trajectory only has rows where the subject was DETECTED, so the interval
that ends on the first row after a tracking gap (the rat hidden by the
experimenter's hand, the fish behind a reflection) spans the whole gap. That
interval is unobserved time, and every metric has to treat it the same way:

- ROI time credits at most the cap to the ROI and reports the excess as
  ``tempo_nao_observado_s`` (:class:`zebtrack.analysis.roi.ROIAnalyzer`);
- behaviour never lets an episode (freezing, inactivity, burst), a smoothing
  window or a distance step cross it
  (:class:`zebtrack.analysis.behavior.BehavioralAnalyzer`).

One rule, one module: the two analysers used to be able to disagree on what a
gap is. This module is a leaf (numpy only) so that ``behavior.py`` can import
it without pulling ``zebtrack.core.services`` and its detector stack.
"""

from __future__ import annotations

from typing import Final

import numpy as np

__all__ = ["MAX_GAP_AUTO_FACTOR", "resolve_max_gap_s"]

#: Automatic cap = this factor times the median observed interval between
#: analysed samples. Three intervals tolerate the jitter of a variable frame
#: rate (the Barnes recordings run at ~9.9 fps) and a single missed detection,
#: while a hand over the arena for half a second is already a gap.
MAX_GAP_AUTO_FACTOR: Final[float] = 3.0


def resolve_max_gap_s(dt_seconds: np.ndarray, configured: float | None) -> float:
    """Effective cap on one interval, in seconds (``inf`` = no cap).

    Args:
        dt_seconds: Intervals between consecutive samples of the SAME subject,
            in seconds. ``NaN`` and non-positive values (a subject's first
            row, repeated timestamps) carry no interval and are ignored.
        configured: ``roi_max_gap_s`` as resolved for the project. ``None``
            means automatic; ``math.inf`` disables the cap.

    Returns:
        ``configured`` when it is set, otherwise ``MAX_GAP_AUTO_FACTOR`` times
        the median positive interval, or ``inf`` when there is no interval to
        derive it from (a single sample).
    """
    if configured is not None:
        return float(configured)

    values = np.asarray(dt_seconds, dtype=float)
    positive = values[np.isfinite(values) & (values > 0.0)]
    if positive.size == 0:
        return float(np.inf)
    return float(MAX_GAP_AUTO_FACTOR * np.median(positive))
