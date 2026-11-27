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

Per-animal defaults (ADR-014). The global settings are the zebrafish baseline, so
``zebrafish`` and ``other`` have NO entry in :data:`_ANIMAL_DEFAULTS`: a project
that declares no profile resolves exactly as before. A rodent project that does
not declare a value of its own gets the rodent number instead of the zebrafish one
(:func:`animal_behavior_defaults`); a value the project declares always wins.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective
from zebtrack.core.services.experiment_profile import AnimalModel, resolve_experiment_profile
from zebtrack.settings import DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S

__all__ = [
    "AnimalBehaviorDefaults",
    "animal_behavior_defaults",
    "freezing_defaults",
    "geotaxis_applies",
    "resolve_behavioral_config",
    "resolve_max_plausible_speed",
]


@dataclass(frozen=True, slots=True)
class AnimalBehaviorDefaults:
    """The behavioural defaults an animal model replaces the zebrafish baseline with.

    Attributes:
        max_plausible_speed_cm_s: Speed above which the trajectory validator
            flags a frame.
        thigmotaxis_distance_cm: Width of the "near the wall" band.
        freezing_velocity_threshold: Speed (cm/s) below which the animal counts
            as immobile.
        freezing_min_duration_s: Shortest immobility (s) that counts as freezing.
    """

    max_plausible_speed_cm_s: float
    thigmotaxis_distance_cm: float
    freezing_velocity_threshold: float
    freezing_min_duration_s: float


#: Animal models that override the zebrafish baseline. Sources:
#:
#: * ``max_plausible_speed_cm_s = 100`` and ``thigmotaxis_distance_cm = 15`` are
#:   the numbers of the shipped "Rodent, top view" template
#:   (``resources/wizard_templates/rodent_top_down.json``, #695), already used by
#:   the lab for open-field rats.
#: * ``freezing_velocity_threshold = 2.0`` and ``freezing_min_duration_s = 1.0``
#:   are PROVISIONAL: freezing in rodents is immobility except for breathing, and
#:   a tracked centroid jitters by a pixel or two, so the zebrafish 1.5 cm/s is
#:   nudged up. They are not validated against manual scoring yet (ADR-014 asks
#:   the lab to confirm them); a project can always declare its own.
_ANIMAL_DEFAULTS: Mapping[AnimalModel, AnimalBehaviorDefaults] = MappingProxyType(
    {
        AnimalModel.RODENT: AnimalBehaviorDefaults(
            max_plausible_speed_cm_s=100.0,
            thigmotaxis_distance_cm=15.0,
            freezing_velocity_threshold=2.0,
            freezing_min_duration_s=1.0,
        )
    }
)


def animal_behavior_defaults(animal_model: AnimalModel) -> AnimalBehaviorDefaults | None:
    """The defaults ``animal_model`` imposes, or ``None`` for the zebrafish baseline.

    ``None`` means "use the global settings unchanged": ``zebrafish`` (the
    baseline itself) and ``other`` (no assumption is made about an unknown animal).
    """
    return _ANIMAL_DEFAULTS.get(animal_model)


def freezing_defaults(
    animal_model: AnimalModel, baseline_velocity: float, baseline_min_duration_s: float
) -> tuple[float, float]:
    """``(velocity threshold cm/s, minimum duration s)`` of freezing for ``animal_model``.

    The freezing thresholds are read from ``settings.video_processing`` in many
    places, so only the dialogs that edit them can follow the animal model: they
    pass their baseline (the settings' values) and get it back for the zebrafish
    baseline, or the animal's own numbers.
    """
    defaults = animal_behavior_defaults(animal_model)
    if defaults is None:
        return baseline_velocity, baseline_min_duration_s
    return defaults.freezing_velocity_threshold, defaults.freezing_min_duration_s


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

    project_block: Any = None
    if project_data:
        if "behavioral_config" in project_data:
            project_block = project_data["behavioral_config"]
        else:
            project_block = project_data.get("behavioral_analysis")
        if isinstance(project_block, Mapping):
            config.update(project_block)

    # A rodent project that never declared its own wall band gets the rodent one
    # instead of the zebrafish 1.5 cm the global settings carry.
    animal_defaults = animal_behavior_defaults(
        resolve_experiment_profile(project_data=project_data).animal_model
    )
    if animal_defaults is not None and not _declares(project_block, "thigmotaxis_distance_cm"):
        config["thigmotaxis_distance_cm"] = animal_defaults.thigmotaxis_distance_cm

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

    Precedence: explicit argument > project ``behavioral_config`` > the animal
    model's own ceiling (rodent only, see :func:`animal_behavior_defaults`) >
    ``settings.behavioral_analysis`` > the zebrafish default. A value that is
    missing, non-numeric or not positive falls through to the next level, so a
    hand-edited project cannot switch the check off by accident.
    """
    behavioral = getattr(settings_obj, "behavioral_analysis", None)
    animal_defaults = animal_behavior_defaults(
        resolve_experiment_profile(behavioral_config=behavioral_config).animal_model
    )
    candidates = (
        explicit,
        (behavioral_config or {}).get("max_plausible_speed_cm_s"),
        None if animal_defaults is None else animal_defaults.max_plausible_speed_cm_s,
        getattr(behavioral, "max_plausible_speed_cm_s", None),
    )
    for candidate in candidates:
        speed = _positive_float(candidate)
        if speed is not None:
            return speed
    return DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S


def _declares(block: Any, key: str) -> bool:
    """Whether ``block`` is a mapping that gives ``key`` a value (``None`` is undeclared)."""
    return isinstance(block, Mapping) and block.get(key) is not None


def _positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    return speed if math.isfinite(speed) and speed > 0 else None
