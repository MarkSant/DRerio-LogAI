"""Zero and label of every report time axis (ADR-011).

The ``BehavioralAnalyzer`` index IS the recording clock (PTS pre-recorded, the
ledger-redated capture instant live), so a time axis never divides anything by
a frame rate: it subtracts an origin from the index. With an analysis window
the origin is START, so the axis reads "time since the window began"; without
one it is the first sample.

The Word figures (``VisualizationGenerator``) and the interactive HTML report
(``HtmlReporter``) read the rule from here, so the two exports of the same
analysis put an event at the same second.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = ["seconds_on_axis", "time_axis_label", "time_origin"]


def _window_bounds(b_analyzer: Any) -> tuple[float, float] | None:
    bounds = getattr(b_analyzer, "window_bounds", None)
    if isinstance(bounds, tuple) and len(bounds) == 2:
        return bounds
    return None


def time_origin(b_analyzer: Any, index: pd.Index) -> Any:
    """Zero of the time axes: START with an analysis window, else the first sample."""
    bounds = _window_bounds(b_analyzer)
    if bounds is not None:
        return pd.to_timedelta(float(bounds[0]), unit="s")
    return index[0]


def time_axis_label(b_analyzer: Any) -> str:
    """English, like every other axis label of these figures."""
    if _window_bounds(b_analyzer) is not None:
        return "Time since window START (s)"
    return "Time (s)"


def seconds_on_axis(values: Any, origin: Any) -> pd.Index:
    """``values`` (index labels or ``Timedelta``s) as seconds from ``origin``."""
    return pd.Index((pd.TimedeltaIndex(values) - origin).total_seconds())
