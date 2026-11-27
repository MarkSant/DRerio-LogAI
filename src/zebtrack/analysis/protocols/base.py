"""Types of the protocol layer: what a behavioural protocol adds to the analysis (ADR-014).

The generic analysis (trajectory, ROIs, window) is the same for every project. A
*protocol* (Barnes maze today) adds three things on top of it, all declared by a
:class:`ProtocolSpec`:

* its own metrics, computed once per video by ``compute_metrics`` from a
  :class:`ProtocolContext` and written to ``report["protocol_metrics"]``;
* the tidy columns and report sections those metrics become;
* which generic report sections it suppresses (a top-down rat has no geotaxis).

``report["protocol_metrics"]`` is ALWAYS present, like ``analysis_window``: a
generic project gets exactly ``{"status": "none"}`` so the report shape never
depends on the protocol. Every other status carries ``protocol`` and ``version``.

Per-video protocol data (a Barnes trial type, a manual strategy correction) lives
in ``video_entry["protocol_inputs"][<protocol>]`` and is read and written only
through :func:`protocol_inputs_of_entry` and :func:`set_protocol_input`; the
analysis entry points hand it to ``AnalysisService.run_full_analysis`` as
``protocol_inputs``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from zebtrack.core.services.experiment_profile import ExperimentProfile, ProtocolId

if TYPE_CHECKING:
    import pandas as pd

    from zebtrack.analysis.analysis_window_service import WindowResolution
    from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
    from zebtrack.analysis.roi import ROI, ROIAnalyzer
    from zebtrack.analysis.time_base import TimeBase
    from zebtrack.core.conditions.model import WindowSpec

__all__ = [
    "PROTOCOL_INPUTS_KEY",
    "PROTOCOL_METRICS_KEY",
    "GenericReportSection",
    "ProtocolContext",
    "ProtocolSpec",
    "ProtocolStatus",
    "UnavailableReason",
    "clear_protocol_input",
    "none_metrics",
    "protocol_inputs_for",
    "protocol_inputs_of_entry",
    "set_protocol_input",
    "unavailable_metrics",
]

#: ``report`` key of the protocol metrics. English: new keys are (ADR-012).
PROTOCOL_METRICS_KEY: Final = "protocol_metrics"

#: ``video_entry`` key of the per-video protocol inputs. Persistence contract.
PROTOCOL_INPUTS_KEY: Final = "protocol_inputs"


class ProtocolStatus(StrEnum):
    """``report["protocol_metrics"]["status"]`` tokens."""

    #: Generic project: nothing protocol-specific was asked for.
    NONE = "none"
    #: The protocol's metrics were computed.
    OK = "ok"
    #: The protocol was asked for but its metrics cannot be computed (see ``reason``).
    UNAVAILABLE = "unavailable"
    #: The protocol's computation raised; ``error`` carries the message.
    ERROR = "error"


class UnavailableReason(StrEnum):
    """``report["protocol_metrics"]["reason"]`` tokens (``None`` when ``status`` is ok)."""

    #: The configuration declares a protocol this version does not know.
    UNKNOWN_PROTOCOL = "unknown_protocol"
    #: The protocol is known but no :class:`ProtocolSpec` is registered for it.
    UNREGISTERED = "unregistered"
    #: The video has no ROIs.
    NO_ROIS = "no_rois"
    #: The protocol's zone layout cannot be read from the ROIs.
    LAYOUT_UNRESOLVED = "layout_unresolved"
    #: The protocol needs one animal and the trajectory has more.
    MULTI_ANIMAL = "multi_animal"
    #: The video is analysed per aquarium (multi-aquarium path); every protocol
    #: so far assumes one arena per video. Decided by the analysis hook.
    MULTI_AQUARIUM = "multi_aquarium"
    #: Nothing left to measure (empty trajectory or empty window).
    NO_TRAJECTORY = "no_trajectory"
    #: ``compute_metrics`` raised (status ``error``).
    EXCEPTION = "exception"


class GenericReportSection(StrEnum):
    """Generic report sections a protocol may suppress (``ProtocolSpec``)."""

    THIGMOTAXIS = "thigmotaxis"
    GEOTAXIS = "geotaxis"


def none_metrics() -> dict[str, Any]:
    """``report["protocol_metrics"]`` of a generic project. A new dict per call."""
    return {"status": ProtocolStatus.NONE.value}


def unavailable_metrics(
    protocol: str,
    reason: UnavailableReason,
    *,
    version: int | None = None,
    status: ProtocolStatus = ProtocolStatus.UNAVAILABLE,
    error: str | None = None,
) -> dict[str, Any]:
    """``report["protocol_metrics"]`` when a protocol was asked for and cannot answer."""
    result: dict[str, Any] = {
        "status": status.value,
        "protocol": protocol,
        "version": version,
        "reason": reason.value,
    }
    if error is not None:
        result["error"] = error
    return result


@dataclass(frozen=True, slots=True)
class ProtocolContext:
    """Everything ``ProtocolSpec.compute_metrics`` may read for one video.

    All geometry shares ONE coordinate space: the space ``run_full_analysis`` was
    called in (arena-local raw pixels for the individual report, the homography's
    warped space for the summaries that feed the unified report). ``pixelcm_x`` /
    ``pixelcm_y`` convert that space to centimetres. Never mix in coordinates
    from ``ZoneData`` directly: they are raw video pixels.

    Attributes:
        profile: The resolved experiment profile (``profile.protocol`` is the
            protocol being computed; ``profile.protocol_params`` its raw params).
        trajectory: The trajectory after ``screen_subjects`` — the WHOLE
            recording, NOT cut to the window (debounce and holds need the frames
            before START). Columns as recorded (``timestamp``, ``frame``,
            ``track_id``, ``x1``..``y2``, ``confidence`` and, when present,
            ``x_center_px``/``y_center_px``). ``timestamp`` is the event clock
            (PTS pre-recorded; capture instant live, after ``retime_from_ledger``).
        rois: The report's ROIs, in their stored order (``ROI.name`` is the
            contract; ``ROI.geometry`` is a shapely geometry in this space).
        arena_polygon_px: The arena outline in this space.
        pixelcm_x: Pixels per centimetre along x.
        pixelcm_y: Pixels per centimetre along y.
        window: The analysis window (``None`` = whole recording). ``window.cut``
            is ``(t_start, t_stop)`` on the ``timestamp`` clock; ``window.stop.reason``
            tells why it ended (``burrow_entry``, ``delay``, ``end_of_stream``…).
        time_base: Recording length, rates and median dt of this trajectory.
        behavioral_config: The run's behavioural configuration (read-only).
        inputs: This protocol's per-video inputs
            (``video_entry["protocol_inputs"][<protocol>]``), ``{}`` when none.
        behavioral_analyzer: The run's analyser, ALREADY restricted to the window.
            Read-only: never restrict it again or mutate it.
        roi_analyzer: The run's ROI analyser (report rule), already restricted, or
            ``None`` without ROIs. Read-only.
        warnings: The report's validation warnings — the SAME list as
            ``report["validacao"]["avisos"]``. Append translated, user-facing
            messages here; never remove or reorder entries.
    """

    profile: ExperimentProfile
    trajectory: pd.DataFrame
    rois: tuple[ROI, ...]
    arena_polygon_px: tuple[tuple[float, float], ...]
    pixelcm_x: float
    pixelcm_y: float
    window: WindowResolution | None
    time_base: TimeBase
    behavioral_config: Mapping[str, Any]
    inputs: Mapping[str, Any]
    behavioral_analyzer: ConcreteBehavioralAnalyzer
    roi_analyzer: ROIAnalyzer | None
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class ProtocolSpec:
    """What one protocol adds. Registered in ``analysis/protocols/registry.py``.

    Attributes:
        protocol: The protocol this spec implements.
        display_name: Translated name for the interface; a callable so ``_()``
            runs at call time, never at import (i18n rule).
        compute_metrics: Builds ``report["protocol_metrics"]`` for one video. Must
            return a dict with at least ``status``, ``protocol`` and ``version``;
            should degrade to :func:`unavailable_metrics` rather than raise (an
            exception is caught and reported as status ``error``).
        tidy_columns: Given the protocol's raw params, the ordered tidy columns
            the reporters append AFTER the ``window_*`` columns.
        suppressed_report_sections: Generic sections the reporters omit.
        window_preset: Given the protocol's raw params, the analysis-window spec
            the wizard proposes for a new project (``None`` = no preset).
        zone_assistant: Identifier of the Zones-tab assistant the UI offers
            (``None`` = none).
    """

    protocol: ProtocolId
    display_name: Callable[[], str]
    compute_metrics: Callable[[ProtocolContext], dict[str, Any]]
    tidy_columns: Callable[[Mapping[str, Any]], tuple[str, ...]] = field(default=lambda _params: ())
    suppressed_report_sections: frozenset[GenericReportSection] = frozenset()
    window_preset: Callable[[Mapping[str, Any]], WindowSpec] | None = None
    zone_assistant: str | None = None


# ---------------------------------------------------------------------------
# Per-video inputs (video_entry["protocol_inputs"])
# ---------------------------------------------------------------------------


def protocol_inputs_of_entry(
    video_entry: Mapping[str, Any] | None,
) -> Mapping[str, Mapping[str, Any]]:
    """All per-video protocol inputs of ``video_entry``, keyed by protocol token.

    What an analysis entry point passes as ``run_full_analysis(protocol_inputs=...)``.
    Malformed blocks (not a mapping) are dropped; never raises.
    """
    if not isinstance(video_entry, Mapping):
        return MappingProxyType({})
    raw = video_entry.get(PROTOCOL_INPUTS_KEY)
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    return MappingProxyType(
        {
            str(name): MappingProxyType(dict(block))
            for name, block in raw.items()
            if isinstance(block, Mapping)
        }
    )


def protocol_inputs_for(
    protocol_inputs: Mapping[str, Any] | None, protocol: ProtocolId
) -> Mapping[str, Any]:
    """The inputs of ``protocol`` inside a ``protocol_inputs`` mapping (``{}`` if none)."""
    if not isinstance(protocol_inputs, Mapping):
        return MappingProxyType({})
    block = protocol_inputs.get(protocol.value)
    return MappingProxyType(dict(block)) if isinstance(block, Mapping) else MappingProxyType({})


def set_protocol_input(
    video_entry: MutableMapping[str, Any], protocol: ProtocolId, key: str, value: Any
) -> None:
    """Write one per-video input in place. The caller persists the project.

    A malformed existing block is replaced. ``value`` must be JSON-serialisable.
    """
    blocks = video_entry.get(PROTOCOL_INPUTS_KEY)
    if not isinstance(blocks, MutableMapping):
        blocks = {}
        video_entry[PROTOCOL_INPUTS_KEY] = blocks
    block = blocks.get(protocol.value)
    if not isinstance(block, MutableMapping):
        block = {}
        blocks[protocol.value] = block
    block[key] = value


def clear_protocol_input(
    video_entry: MutableMapping[str, Any], protocol: ProtocolId, key: str
) -> None:
    """Remove one per-video input in place; empty blocks are removed too."""
    blocks = video_entry.get(PROTOCOL_INPUTS_KEY)
    if not isinstance(blocks, MutableMapping):
        return
    block = blocks.get(protocol.value)
    if isinstance(block, MutableMapping):
        block.pop(key, None)
        if not block:
            del blocks[protocol.value]
    if not blocks:
        del video_entry[PROTOCOL_INPUTS_KEY]
