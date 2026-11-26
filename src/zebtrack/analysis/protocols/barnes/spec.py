"""The Barnes-maze :class:`ProtocolSpec` registered in ``registry._builtin_specs()``.

``window_preset`` stays ``None`` until the ``barnes-entry`` front ships
``barnes_maze_preset_v2``; the hub then wires it here (CONTRACTS §6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from zebtrack.analysis.protocols.barnes.contract import (
    ASSISTANT_ID,
    barnes_tidy_columns,
    parse_barnes_params,
)
from zebtrack.analysis.protocols.barnes.metrics import compute_barnes_metrics
from zebtrack.analysis.protocols.base import GenericReportSection, ProtocolSpec
from zebtrack.core.services.experiment_profile import ProtocolId
from zebtrack.i18n import _

__all__ = ["BARNES_SPEC"]


def _display_name() -> str:
    return _("Barnes maze")


def _tidy_columns(raw_params: Mapping[str, Any]) -> tuple[str, ...]:
    """The ``barnes_*`` tidy columns of a project with these raw params."""
    return barnes_tidy_columns(parse_barnes_params(raw_params)[0].n_holes)


BARNES_SPEC = ProtocolSpec(
    protocol=ProtocolId.BARNES,
    display_name=_display_name,
    compute_metrics=compute_barnes_metrics,
    tidy_columns=_tidy_columns,
    # A top-down rat on a dry table has no wall to hug and no depth axis.
    suppressed_report_sections=frozenset(
        {GenericReportSection.THIGMOTAXIS, GenericReportSection.GEOTAXIS}
    ),
    window_preset=None,
    zone_assistant=ASSISTANT_ID,
)
