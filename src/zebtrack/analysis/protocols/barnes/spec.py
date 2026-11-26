"""The Barnes-maze :class:`ProtocolSpec` registered in ``registry._builtin_specs()``.

Its ``window_preset`` is ``barnes_maze_preset_v2`` built from the project's
``BarnesParams`` (:func:`barnes_window_preset`), the one mapping of params to
preset arguments: the analysis-window editor builds its v2 proposal with it too.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from zebtrack.analysis.protocols.barnes.contract import (
    ASSISTANT_ID,
    TARGET_ROI,
    BarnesParams,
    barnes_tidy_columns,
    parse_barnes_params,
)
from zebtrack.analysis.protocols.barnes.metrics import compute_barnes_metrics
from zebtrack.analysis.protocols.base import GenericReportSection, ProtocolSpec
from zebtrack.core.conditions.model import WindowSpec
from zebtrack.core.conditions.presets import barnes_maze_preset_v2
from zebtrack.core.services.experiment_profile import ProtocolId
from zebtrack.i18n import _

__all__ = ["BARNES_SPEC", "barnes_window_preset"]


def _display_name() -> str:
    return _("Barnes maze")


def _tidy_columns(raw_params: Mapping[str, Any]) -> tuple[str, ...]:
    """The ``barnes_*`` tidy columns of a project with these raw params."""
    return barnes_tidy_columns(parse_barnes_params(raw_params)[0].n_holes)


def barnes_window_preset(
    params: BarnesParams,
    *,
    k_frames: int | None = None,
    max_s: float | None = None,
    burrow_roi: str = TARGET_ROI,
) -> WindowSpec:
    """The analysis window of a Barnes trial: preset v2 with these params.

    ``max_s`` defaults to ``params.max_trial_s`` and the five entry thresholds
    always come from ``params``; ``k_frames`` defaults to the preset's own release
    hold. ``k_frames``/``max_s``/``burrow_roi`` are overridable so an update from a
    v1 window keeps what the researcher had set there.
    """
    hold = {} if k_frames is None else {"k_frames": k_frames}
    return barnes_maze_preset_v2(
        **hold,
        max_s=params.max_trial_s if max_s is None else max_s,
        burrow_roi=burrow_roi,
        entry_min_cover=params.entry_min_cover,
        entry_max_visible_fraction=params.entry_max_visible_fraction,
        entry_hold_s=params.entry_hold_s,
        entry_absent_s=params.entry_absent_s,
        entry_min_reference_frames=params.entry_min_reference_frames,
    )


def _window_preset(raw_params: Mapping[str, Any]) -> WindowSpec:
    """``ProtocolSpec.window_preset``: the v2 window from a project's raw params."""
    return barnes_window_preset(parse_barnes_params(raw_params)[0])


BARNES_SPEC = ProtocolSpec(
    protocol=ProtocolId.BARNES,
    display_name=_display_name,
    compute_metrics=compute_barnes_metrics,
    tidy_columns=_tidy_columns,
    # A top-down rat on a dry table has no wall to hug and no depth axis.
    suppressed_report_sections=frozenset(
        {GenericReportSection.THIGMOTAXIS, GenericReportSection.GEOTAXIS}
    ),
    window_preset=_window_preset,
    zone_assistant=ASSISTANT_ID,
)
