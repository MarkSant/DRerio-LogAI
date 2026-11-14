"""Species-neutral rules for the behavioural metrics (#631).

Two questions used to be answered with zebrafish assumptions baked in at each
call site:

* **Does geotaxis apply?** Geotaxis measures depth (distance to the BOTTOM of
  the tank), so it only means something in a SIDE view. A top-down video of a
  rat has no bottom: its "geotaxis" is just the y coordinate of the floor plan.
  ``AnalysisService.run_full_analysis`` computed it whenever a distance
  threshold existed, and ``collect_analysis_parameters`` let the global
  ``lateral`` default's ``geotaxis_enabled=True`` survive a project that
  declared ``top_down``.
* **What speed is implausible?** 50 cm/s is a ceiling for adult zebrafish; a
  rat sprinting in an open field passes it, and every such run then carried a
  spurious "implausible speed" warning.

Both answers live here so the analysis service, the parameter collector and
the processing snapshot agree.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective
from zebtrack.settings import DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S

__all__ = ["geotaxis_applies", "resolve_behavioral_config", "resolve_max_plausible_speed"]


def geotaxis_applies(behavioral_config: Mapping[str, Any] | None) -> bool:
    """Whether geotaxis may be computed for this behavioural configuration.

    ``top_down`` always disables it, whatever ``geotaxis_enabled`` says (the
    same rule the wizard's ``BehavioralAnalysisData`` validator applies). In a
    side view it is on unless the configuration explicitly turns it off, so a
    zebrafish configuration that never mentions the flag keeps its geotaxis.

    ``DataTransformer`` is deliberately stricter (it needs an explicit
    ``geotaxis_enabled=True`` before adding columns to the tidy table): loosening
    it would add columns to existing zebrafish spreadsheets.
    """
    config = behavioral_config or {}
    if normalize_aquarium_perspective(config.get("aquarium_perspective")) != "lateral":
        return False
    return config.get("geotaxis_enabled") is not False


def resolve_behavioral_config(
    project_data: Mapping[str, Any] | None, settings_obj: Any
) -> dict[str, Any]:
    """The behavioural config every report path hands the reporters (#695).

    Settings defaults (under the PROJECT key names) < the project's
    ``behavioral_config`` (or the legacy ``behavioral_analysis`` key), with the
    perspective normalised and ``geotaxis_enabled`` always re-derived by
    :func:`geotaxis_applies`. ``AnalysisService.collect_analysis_parameters``
    ("Generate reports") and the automatic pre-recorded pipeline both read it;
    until #695 the pipeline passed ``{}``, so its xlsx said ``lateral`` and
    1.5 cm whatever the project declared, and never carried geotaxis.

    Returns a new dict; neither argument is modified.
    """
    config: dict[str, Any] = {}
    behavioral = getattr(settings_obj, "behavioral_analysis", None) if settings_obj else None
    if behavioral is not None:
        perspective = normalize_aquarium_perspective(
            getattr(behavioral, "aquarium_perspective", "lateral")
        )
        config = {
            "thigmotaxis_distance_cm": behavioral.default_thigmotaxis_distance_cm,
            "geotaxis_distance_cm": behavioral.default_geotaxis_distance_cm,
            "geotaxis_num_zones": behavioral.default_geotaxis_num_zones,
            "geotaxis_bottom_zones": behavioral.default_geotaxis_bottom_zones,
            "aquarium_perspective": perspective,
            "geotaxis_enabled": perspective == "lateral",
        }

    if project_data:
        if "behavioral_config" in project_data:
            project_block = project_data["behavioral_config"]
        else:
            project_block = project_data.get("behavioral_analysis")
        if isinstance(project_block, Mapping):
            config.update(project_block)

    if config:
        config["aquarium_perspective"] = normalize_aquarium_perspective(
            config.get("aquarium_perspective")
        )
        config["geotaxis_enabled"] = geotaxis_applies(config)
    return config


def resolve_max_plausible_speed(
    explicit: float | None,
    behavioral_config: Mapping[str, Any] | None,
    settings_obj: Any,
) -> float:
    """Speed ceiling (cm/s) above which a frame is flagged as implausible.

    Precedence: explicit argument > project ``behavioral_config`` >
    ``settings.behavioral_analysis`` > the zebrafish default. A value that is
    missing, non-numeric or not positive falls through to the next level, so a
    hand-edited project cannot switch the check off by accident.
    """
    behavioral = getattr(settings_obj, "behavioral_analysis", None)
    candidates = (
        explicit,
        (behavioral_config or {}).get("max_plausible_speed_cm_s"),
        getattr(behavioral, "max_plausible_speed_cm_s", None),
    )
    for candidate in candidates:
        speed = _positive_float(candidate)
        if speed is not None:
            return speed
    return DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S


def _positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    return speed if math.isfinite(speed) and speed > 0 else None
