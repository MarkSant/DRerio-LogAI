"""Single builder for the ``Settings`` a project run must actually use.

Every path that analyses a PROJECT needs the same object: the session settings
with that project's overrides layered on top, and the shared singleton left
untouched. Until this module there were TWO implementations of that idea —
``VideoSelectionMixin._create_project_settings_snapshot`` and
``ReportGenerationCoordinator._create_project_settings_snapshot`` — and they
applied different keys:

======================================  ==========  ============
key                                     processing  regeneration
======================================  ==========  ============
``analysis_parameters`` (smoothing)     yes         no
``behavioral_config``                   yes         no
``analysis_offset_frames``              yes         no
``analysis_interval_frames``            no          yes
``display_interval_frames``             no          yes
``single_animal_per_aquarium``          no          yes
ROI rule                                yes         yes
======================================  ==========  ============

So REGENERATING a report produced different numbers than PROCESSING the same
video — the exact failure ``tests/coordinators/test_roi_rule_propagation.py``
was written for, which had been closed for the ROI rule alone. This module is
the union, and both call sites now delegate here.

Why a ``baseline`` argument
---------------------------
The ad-hoc dialogs (``SingleVideoConfigDialog``, ``LiveAnalysisDialog``) write
their per-run choices into the SHARED ``Settings`` object, permanently. Freezing
thresholds and the Savitzky-Golay window are among them, and a project that does
not carry its own values would silently inherit whatever the last ad-hoc run
left behind — changing reported freezing time, sharp turns, distance and speed.

``baseline`` is a pristine copy taken at startup, before any dialog can run. The
precedence for a project is therefore **project > baseline > schema default**,
and the live (mutated) settings object never enters the answer. Passing no
baseline falls back to ``settings_obj``, which keeps old call sites working.

Everything here DEGRADES: a value that ``Settings`` refuses is logged and the
previous one is kept. ``Settings`` uses ``validate_assignment=True``, so a
hand-edited ``project_config.json`` with an even ``window_length`` would
otherwise raise ``ValidationError`` in the middle of an analysis.
"""

from __future__ import annotations

import copy
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.core.services.roi_rule_resolver import (
    apply_roi_rule_to_settings,
    resolve_roi_rule,
)

log = structlog.get_logger()

__all__ = [
    "ANALYSIS_PARAMETER_FIELDS",
    "build_project_settings_snapshot",
]

#: ``project_data["analysis_parameters"]`` key -> ``settings.video_processing`` field.
#:
#: The key names are the ones the existing readers already use
#: (``AnalysisService.collect_analysis_parameters`` and the processing snapshot);
#: ``sharp_turn_threshold`` is new — it was the one threshold with no project
#: home at all, even though the ad-hoc dialogs happily overwrote it globally.
ANALYSIS_PARAMETER_FIELDS: dict[str, str] = {
    "freezing_vel_threshold": "freezing_velocity_threshold",
    "freezing_min_duration": "freezing_min_duration_s",
    "sharp_turn_threshold": "sharp_turn_threshold_deg_s",
}


def _replace_submodel(snapshot: Any, name: str, changes: dict[str, Any]) -> bool:
    """Rebuild one sub-model with ``changes`` and hand it to the PARENT.

    Assigning fields on a sub-model in place is not enough. ``Settings`` carries
    cross-field validators that span sub-models — ``processing_offset`` must stay
    below ``processing_interval``, for one — and those only run when the parent
    is assigned. Writing straight to the sub-model leaves the parent in an
    invalid state and the ``ValidationError`` then surfaces at the NEXT parent
    assignment, blaming an unrelated field.

    Going through the parent validates the whole batch at once and, on refusal,
    leaves the previous sub-model untouched.
    """
    current = getattr(snapshot, name, None)
    if current is None or not changes:
        return False

    dump = getattr(current, "model_dump", None)
    if not callable(dump):
        # Stub sub-model (tests, half-wired objects): no validation to honour.
        for field, value in changes.items():
            setattr(current, field, value)
        return True

    try:
        setattr(snapshot, name, type(current)(**{**dump(), **changes}))
        return True
    except (ValidationError, ValueError, TypeError) as exc:
        # Pydantic v2 writes the field BEFORE running the model validator, so a
        # rejected assignment still leaves the new (invalid) sub-model in place.
        # The exception alone is not a rollback: without this the snapshot stays
        # corrupt and blows up later at an unrelated assignment — which is
        # exactly how ``processing_offset`` surfaced as a ROI-rule failure.
        # ``__dict__`` restores the previous, known-valid sub-model without
        # re-triggering validation.
        try:
            snapshot.__dict__[name] = current
        # except Exception justified: a stand-in without a writable ``__dict__``
        # is already a degraded object; the warning below is the useful signal.
        except Exception:
            log.debug("project_settings_snapshot.submodel.rollback_failed", submodel=name)
        log.warning(
            "project_settings_snapshot.submodel.rejected",
            submodel=name,
            changes=changes,
            error=str(exc),
        )
        return False


def _apply_submodel(snapshot: Any, name: str, changes: dict[str, Any]) -> None:
    """Apply ``changes`` as a batch, falling back to one key at a time.

    A single bad value must not discard the good ones alongside it — a project
    with one hand-edited typo should still get the rest of its configuration.
    """
    if not changes:
        return
    if _replace_submodel(snapshot, name, changes):
        return
    for field, value in changes.items():
        _replace_submodel(snapshot, name, {field: value})


def _cast(value: Any, caster: Any, *, field: str) -> Any:
    try:
        return caster(value)
    except (TypeError, ValueError):
        log.warning(
            "project_settings_snapshot.field.uncastable",
            field=field,
            value=repr(value),
        )
        return None


def _collect_interval_overrides(project_data: dict[str, Any]) -> dict[str, Any]:
    """Frame cadence, offset and single-animal mode."""
    changes: dict[str, Any] = {}
    for key, field, caster in (
        ("analysis_interval_frames", "processing_interval", int),
        ("display_interval_frames", "display_interval", int),
        ("analysis_offset_frames", "processing_offset", int),
        ("single_animal_per_aquarium", "single_animal_per_aquarium", bool),
    ):
        if key not in project_data:
            continue
        value = _cast(project_data[key], caster, field=key)
        if value is not None:
            changes[field] = value
    return changes


def _collect_threshold_overrides(params: dict[str, Any]) -> dict[str, Any]:
    """Freezing and sharp-turn thresholds."""
    changes: dict[str, Any] = {}
    for key, field in ANALYSIS_PARAMETER_FIELDS.items():
        if key not in params:
            continue
        value = _cast(params[key], float, field=key)
        if value is not None:
            changes[field] = value
    return changes


def _apply_smoothing(snapshot: Any, params: dict[str, Any]) -> None:
    """Replace the smoothing sub-model ATOMICALLY.

    ``window_length`` and ``polyorder`` are bound by a cross-field validator
    (``polyorder < window_length``) plus an odd-window rule. Assigning them one
    at a time can therefore fail on a perfectly valid PAIR, purely because of
    the order — raising ``polyorder`` before ``window_length`` trips the
    validator against the old window.
    """
    current = getattr(snapshot, "trajectory_smoothing", None)
    if current is None:
        return
    if "smoothing_window_length" not in params and "smoothing_polyorder" not in params:
        return

    window = _cast(
        params.get("smoothing_window_length", current.window_length),
        int,
        field="smoothing_window_length",
    )
    polyorder = _cast(
        params.get("smoothing_polyorder", current.polyorder),
        int,
        field="smoothing_polyorder",
    )
    if window is None or polyorder is None:
        return

    # As a PAIR, never key by key: a valid pair can be rejected purely on the
    # order the two halves are written in.
    _replace_submodel(
        snapshot,
        "trajectory_smoothing",
        {"window_length": window, "polyorder": polyorder},
    )


def _collect_behavioral_overrides(project_data: dict[str, Any]) -> dict[str, Any]:
    """Thigmotaxis / geotaxis / perspective."""
    behavioral_config = project_data.get("behavioral_config")
    if not isinstance(behavioral_config, dict) or not behavioral_config:
        return {}

    changes: dict[str, Any] = {}
    if "aquarium_perspective" in behavioral_config:
        changes["aquarium_perspective"] = _normalize_perspective(
            behavioral_config["aquarium_perspective"]
        )
    for key, field in (
        ("thigmotaxis_distance_cm", "default_thigmotaxis_distance_cm"),
        ("geotaxis_distance_cm", "default_geotaxis_distance_cm"),
        ("geotaxis_num_zones", "default_geotaxis_num_zones"),
        ("geotaxis_bottom_zones", "default_geotaxis_bottom_zones"),
        ("geotaxis_mode", "geotaxis_mode"),
    ):
        if key in behavioral_config:
            changes[field] = behavioral_config[key]
    return changes


def _copy_settings(source: Any) -> Any:
    """Deep-copy the settings, whatever shape they are.

    Production always passes a Pydantic ``Settings``, but partial stand-ins
    reach here from tests and from call sites that only wire part of the object.
    The invariant that matters is that the SHARED instance is never mutated, and
    ``copy.deepcopy`` upholds it just as well as ``model_copy``.
    """
    model_copy = getattr(source, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    return copy.deepcopy(source)


def _normalize_perspective(raw: Any) -> str:
    token = str(raw).strip().lower().replace("-", "_")
    return "top_down" if token in {"top_down", "top_down_view", "topdown", "top"} else "lateral"


def build_project_settings_snapshot(
    settings_obj: Any,
    project_data: dict[str, Any] | None,
    *,
    baseline: Any = None,
) -> Any:
    """Return a deep copy of the settings with ``project_data`` layered on top.

    Args:
        settings_obj: the session settings. Used to resolve the ROI rule's
            global fallback, and as the baseline when none is supplied.
        project_data: the open project's data. ``None``/empty yields a plain
            copy — the correct answer for an ad-hoc run.
        baseline: pristine settings captured at startup. Supply it wherever a
            PROJECT is being analysed: it is what stops an earlier ad-hoc run's
            thresholds from becoming this project's thresholds.

    The returned object is always a copy; the shared singleton is never mutated.
    """
    source = baseline if baseline is not None else settings_obj
    snapshot = _copy_settings(source)
    data = project_data or {}

    params = data.get("analysis_parameters")
    params = params if isinstance(params, dict) else {}

    _apply_submodel(
        snapshot,
        "video_processing",
        {**_collect_interval_overrides(data), **_collect_threshold_overrides(params)},
    )
    _apply_smoothing(snapshot, params)
    _apply_submodel(snapshot, "behavioral_analysis", _collect_behavioral_overrides(data))

    # Canonical ROI resolution — project > global > default. Kept last because
    # ``apply_roi_rule_to_settings`` depends on an already-consistent object.
    apply_roi_rule_to_settings(snapshot, resolve_roi_rule(data, settings_obj))

    return snapshot
