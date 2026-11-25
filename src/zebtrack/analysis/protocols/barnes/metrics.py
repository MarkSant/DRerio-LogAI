"""The Barnes protocol's ``compute_metrics`` (ADR-014, CONTRACTS §6–§7).

One trial per video. Reads a :class:`ProtocolContext` and returns
``report["protocol_metrics"]``: with status ``ok`` the keys are exactly
``contract.METRICS_KEYS`` in that order; otherwise the contract's ``unavailable``
form, decided in this order: ``no_rois``, ``layout_unresolved``, ``multi_animal``,
``no_trajectory``. Every case that loses information adds a translated warning to
``context.warnings`` (the report's validation warnings).

Timing:

* ``t0`` (``t_start_s``) is the window's START; without one, the first detection
  (``start_source="recording"``, warned);
* the trial ends at ``min(window STOP or last detection, t0 + max_trial_s)``;
* the entry is NEVER re-detected here: it is the window's STOP when its reason is
  ``burrow_entry`` (ADR-011, one evaluator).

``visits_by_distance`` has ``int`` keys in memory; a JSON round-trip turns them
into ``str`` (CONTRACTS §7). Pure: no Tk, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import structlog

from zebtrack.analysis.protocols.barnes.contract import (
    METRICS_VERSION,
    QUADRANT_ROI,
    STOP_REASON_BURROW_ENTRY,
    BarnesParams,
    EntrySource,
    StartSource,
    TrialType,
    max_offset,
    parse_barnes_params,
    parse_barnes_video_inputs,
    probe_score,
)
from zebtrack.analysis.protocols.barnes.layout import ResolvedLayout, resolve_layout
from zebtrack.analysis.protocols.barnes.strategy import (
    classify_strategy,
    count_center_crossings,
    resolve_strategy,
    strategy_features,
)
from zebtrack.analysis.protocols.barnes.visits import (
    HoleVisit,
    SubjectSamples,
    detect_hole_visits,
    path_length_cm,
    subject_samples,
    visits_in_trial,
)
from zebtrack.analysis.protocols.base import (
    ProtocolContext,
    UnavailableReason,
    unavailable_metrics,
)
from zebtrack.analysis.track_significance import count_subjects
from zebtrack.core.services.experiment_profile import ProtocolId
from zebtrack.i18n import _

__all__ = ["compute_barnes_metrics"]

logger = structlog.get_logger()

#: ``kind`` of the conditions-engine node that can end a window with
#: ``burrow_entry`` (``BurrowEntry``, preset v2). A window whose spec has one can
#: detect an entry, so a STOP for another reason means the entry did not happen.
_BURROW_ENTRY_NODE_KIND: Final = "burrow_entry"


def _unavailable(reason: UnavailableReason) -> dict[str, Any]:
    return unavailable_metrics(ProtocolId.BARNES.value, reason, version=METRICS_VERSION)


def _spec_has_kind(node: Any, kind: str) -> bool:
    """Whether a window spec (JSON form) contains a node of ``kind`` anywhere."""
    if isinstance(node, Mapping):
        if node.get("kind") == kind:
            return True
        return any(_spec_has_kind(value, kind) for value in node.values())
    if isinstance(node, list | tuple):
        return any(_spec_has_kind(item, kind) for item in node)
    return False


def _entry(
    context: ProtocolContext, trial_type: TrialType, t0: float, params: BarnesParams
) -> tuple[float | None, bool | None, EntrySource]:
    """``(entry_latency_s, entry_censored, entry_source)``.

    An entry the window found AFTER ``t0 + max_trial_s`` is past the protocol
    ceiling: censored at ``max_trial_s``, exactly like no entry at all.
    """
    if trial_type is TrialType.PROBE:
        return None, None, EntrySource.NOT_APPLICABLE
    window = context.window
    if (
        window is not None
        and window.stop is not None
        and window.stop.reason == STOP_REASON_BURROW_ENTRY
    ):
        latency = float(window.stop.t_s) - t0
        if latency > params.max_trial_s:
            return params.max_trial_s, True, EntrySource.CENSORED
        return latency, False, EntrySource.WINDOW
    if window is not None and _spec_has_kind(window.spec, _BURROW_ENTRY_NODE_KIND):
        return params.max_trial_s, True, EntrySource.CENSORED
    context.warnings.append(
        _(
            "The analysis window of this Barnes trial cannot detect the burrow entry "
            "(it has no burrow_entry stop); the entry latency was not measured."
        )
    )
    return None, None, EntrySource.UNAVAILABLE


def _quadrant_time(
    context: ProtocolContext, layout: ResolvedLayout, t0: float, trial_end: float
) -> tuple[float | None, float | None]:
    """``(target_quadrant_time_s, target_quadrant_time_pct)`` over the TRIAL.

    The report's ROI analyser (its rule and debounce) measured over
    ``[t0, trial_end]`` — the same span as the percentage's denominator, so the
    percentage stays within 0-100 even when the window (or the recording, without
    one) outlasts ``max_trial_s``.
    """
    times: Mapping[str, Mapping[str, float]] = (
        context.roi_analyzer.get_time_spent_in_rois(t0, trial_end)
        if context.roi_analyzer is not None
        else {}
    )
    entry = times.get(QUADRANT_ROI) if layout.quadrant is not None else None
    if entry is None:
        context.warnings.append(
            _(
                "The Barnes ROI {roi} is missing; the time in the target quadrant was not computed."
            ).format(roi=QUADRANT_ROI)
        )
        return None, None
    seconds = float(entry["seconds"])
    return seconds, seconds / (trial_end - t0) * 100.0


def _visit_rows(
    visits: list[HoleVisit],
    t0: float,
    encounter_t: float | None,
) -> tuple[list[dict[str, Any]], list[bool]]:
    rows: list[dict[str, Any]] = []
    perseverative: list[bool] = []
    seen: set[int] = set()
    for order, visit in enumerate(visits, start=1):
        is_target = visit.offset == 0
        repeat = not is_target and visit.offset in seen
        seen.add(visit.offset)
        perseverative.append(repeat)
        t_enter = visit.t_enter_s - t0
        t_exit = None if visit.t_exit_s is None else visit.t_exit_s - t0
        rows.append(
            {
                "order": order,
                "roi": visit.roi,
                "offset": visit.offset,
                "distance": abs(visit.offset),
                "t_enter_s": t_enter,
                "t_exit_s": t_exit,
                "dwell_s": None if t_exit is None else t_exit - t_enter,
                "is_target": is_target,
                "is_perseverative": repeat,
                "before_encounter": encounter_t is None or visit.t_enter_s < encounter_t,
            }
        )
    return rows, perseverative


def _probe(
    visits: list[HoleVisit], t0: float, params: BarnesParams
) -> tuple[int | None, int | None, float | None, int | None]:
    """``(first offset, first score, first-error latency, attempts to target)``."""
    if not visits:
        return None, None, None, None
    first = visits[0]
    first_error = None if first.offset == 0 else first.t_enter_s - t0
    attempts = next(
        (order for order, visit in enumerate(visits, start=1) if visit.offset == 0), None
    )
    return first.offset, probe_score(first.offset, params.probe_score_cap), first_error, attempts


def _trial_bounds(
    context: ProtocolContext, samples: SubjectSamples, params: BarnesParams
) -> tuple[float, StartSource, float] | None:
    """``(t0, start_source, trial_end)``, or ``None`` when there is nothing to measure.

    Nothing to measure: no detection, an empty window, or no detection between
    ``t0`` and the trial end.
    """
    window = context.window
    if len(samples) == 0 or (window is not None and window.is_empty):
        return None
    if window is not None and window.start is not None:
        t0, source = float(window.start.t_s), StartSource.WINDOW
    else:
        t0, source = float(samples.t_s[0]), StartSource.RECORDING
    stop_t = (
        float(window.stop.t_s)
        if window is not None and window.stop is not None
        else float(samples.t_s[-1])
    )
    trial_end = min(stop_t, t0 + params.max_trial_s)
    in_trial = (samples.t_s >= t0) & (samples.t_s <= trial_end)
    if not trial_end > t0 or not bool(in_trial.any()):
        return None
    return t0, source, trial_end


def compute_barnes_metrics(context: ProtocolContext) -> dict[str, Any]:
    """``report["protocol_metrics"]`` of one Barnes trial (module docstring)."""
    params, param_warnings = parse_barnes_params(context.profile.protocol_params)
    inputs, input_warnings = parse_barnes_video_inputs(context.inputs)
    context.warnings.extend(param_warnings)
    context.warnings.extend(input_warnings)

    if not context.rois:
        context.warnings.append(_("This video has no ROIs; the Barnes metrics need the hole ROIs."))
        return _unavailable(UnavailableReason.NO_ROIS)

    resolution = resolve_layout(context.rois, context.arena_polygon_px, params.n_holes)
    if resolution.duplicates:
        context.warnings.append(
            _(
                "Several ROIs share the Barnes name(s) {names}; the Barnes metrics use the "
                "first ROI of each name."
            ).format(names=", ".join(resolution.duplicates))
        )
    layout = resolution.layout
    if layout is None:
        if resolution.missing:
            context.warnings.append(
                _(
                    "The Barnes metrics were not computed: hole ROIs missing or empty: {names}."
                ).format(names=", ".join(resolution.missing))
            )
        else:
            context.warnings.append(
                _("The Barnes metrics were not computed: the hole ROIs do not form a ring.")
            )
        return _unavailable(UnavailableReason.LAYOUT_UNRESOLVED)

    n_subjects = count_subjects(context.trajectory)
    if n_subjects > 1:
        context.warnings.append(
            _("The Barnes metrics need one animal per video; this trajectory has {count}.").format(
                count=n_subjects
            )
        )
        return _unavailable(UnavailableReason.MULTI_ANIMAL)

    gap_threshold_s = float(context.behavioral_analyzer.gap_threshold_s)
    samples = subject_samples(
        context.trajectory,
        pixelcm_x=context.pixelcm_x,
        pixelcm_y=context.pixelcm_y,
        gap_threshold_s=gap_threshold_s,
    )
    bounds = _trial_bounds(context, samples, params)
    if bounds is None:
        context.warnings.append(
            _("The Barnes trial has no detection to measure; the Barnes metrics were not computed.")
        )
        return _unavailable(UnavailableReason.NO_TRAJECTORY)
    t0, start_source, trial_end = bounds
    if start_source is StartSource.RECORDING:
        context.warnings.append(
            _(
                "The analysis window has no START; the Barnes trial is timed from the "
                "first detection."
            )
        )

    trial_type = inputs.trial_type or params.default_trial_type
    detection = detect_hole_visits(samples, layout.holes, params)
    visits = visits_in_trial(detection.visits, t0, trial_end)
    unmeasured = visits_in_trial(detection.unmeasured, t0, trial_end)
    if unmeasured:
        context.warnings.append(
            _(
                "{count} possible hole visit(s) were left out of the Barnes metrics: the "
                "slowdown filter (visit_max_speed_cm_s) could not measure the speed around "
                "them (tracking gaps)."
            ).format(count=len(unmeasured))
        )

    encounter = next((visit for visit in visits if visit.offset == 0), None)
    encounter_t = None if encounter is None else encounter.t_enter_s
    entry_latency, entry_censored, entry_source = _entry(context, trial_type, t0, params)
    entry_t: float | None = None
    if entry_source is EntrySource.WINDOW and entry_latency is not None:
        entry_t = t0 + entry_latency

    visit_rows, perseverative = _visit_rows(visits, t0, encounter_t)
    primary_cutoff = encounter_t if encounter_t is not None else np.inf
    total_cutoff = entry_t if entry_t is not None else trial_end
    primary_errors = sum(1 for v in visits if v.offset != 0 and v.t_enter_s < primary_cutoff)
    total_errors = sum(1 for v in visits if v.offset != 0 and v.t_enter_s < total_cutoff)
    perseverative_errors = sum(
        1
        for v, repeat in zip(visits, perseverative, strict=True)
        if repeat and v.t_enter_s < total_cutoff
    )

    def path_to(t_event: float | None) -> float | None:
        if t_event is None:
            return None
        return path_length_cm(
            samples,
            t0,
            t_event,
            pixelcm_x=context.pixelcm_x,
            pixelcm_y=context.pixelcm_y,
            gap_threshold_s=gap_threshold_s,
        )

    quadrant_s, quadrant_pct = _quadrant_time(context, layout, t0, trial_end)

    visits_by_distance = {d: 0 for d in range(max_offset(params.n_holes) + 1)}
    for visit in visits:
        visits_by_distance[abs(visit.offset)] += 1

    search = visits if encounter is None else visits[: visits.index(encounter) + 1]
    search_end = trial_end if encounter_t is None else encounter_t
    span = (samples.t_s >= t0) & (samples.t_s <= search_end)
    crossings = count_center_crossings(
        layout.in_center_disk(samples.cx[span], samples.cy[span], params.center_radius_ratio)
    )
    features = strategy_features(
        [visit.offset for visit in search],
        errors_before_target=primary_errors,
        center_crossings=crossings,
        params=params,
    )
    strategy_auto = classify_strategy(
        features, found_target=encounter is not None, n_visits=len(visits), params=params
    )
    strategy, strategy_source = resolve_strategy(strategy_auto, inputs.strategy_override)

    probe: tuple[int | None, int | None, float | None, int | None] = (None, None, None, None)
    if trial_type is TrialType.PROBE:
        probe = _probe(visits, t0, params)

    logger.info(
        "barnes.metrics.computed",
        trial_type=trial_type.value,
        visits=len(visits),
        encounter=encounter is not None,
        entry_source=entry_source.value,
        strategy=None if strategy is None else strategy.value,
    )
    return {
        "status": "ok",
        "protocol": ProtocolId.BARNES.value,
        "version": METRICS_VERSION,
        "reason": None,
        "trial_type": trial_type.value,
        "n_holes": params.n_holes,
        "t_start_s": t0,
        "start_source": start_source.value,
        "encounter_latency_s": (params.max_trial_s if encounter_t is None else encounter_t - t0),
        "encounter_censored": encounter_t is None,
        "entry_latency_s": entry_latency,
        "entry_censored": entry_censored,
        "entry_source": entry_source.value,
        "primary_errors": primary_errors,
        "total_errors": total_errors,
        "perseverative_errors": perseverative_errors,
        "primary_path_length_cm": path_to(encounter_t),
        "entry_path_length_cm": path_to(entry_t),
        "target_quadrant_time_s": quadrant_s,
        "target_quadrant_time_pct": quadrant_pct,
        "visits_by_distance": visits_by_distance,
        "visit_sequence": visit_rows,
        "strategy": None if strategy is None else strategy.value,
        "strategy_source": None if strategy_source is None else strategy_source.value,
        "strategy_auto": None if strategy_auto is None else strategy_auto.value,
        "strategy_features": features.as_dict(),
        "probe_first_hole_offset": probe[0],
        "probe_first_hole_score": probe[1],
        "probe_first_error_latency_s": probe[2],
        "probe_attempts_to_target": probe[3],
    }
