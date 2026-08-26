"""Single rule for HOW the arena is auto-detected: model family and outline shape.

Two flows auto-detect the aquarium, and until this module they disagreed:

* the LIVE camera path — ``LiveCalibrationCoordinator.run_live_calibration`` —
  resolved ``aquarium_method`` from the project, then the settings, then "det",
  and separately read ``preserve_real_aquarium_shape``;
* the PRE-RECORDED path — ``MultiAquariumCoordinator.run_aquarium_detection`` —
  did ``method if method != "auto" else "det"`` and read neither key.

Every pre-recorded call site uses the ``"auto"`` default, so that branch pinned
the pre-recorded flow to detection boxes forever. The consequences were silent
and user-visible at the same time: the "Aquarium AI: seg/det" combobox in
``SingleVideoConfigDialog`` wrote a value nothing read, a project carrying
``model_selection.aquarium_method: "seg"`` still ran "det", and
``ZoneContextPanel`` advertised the seg weight that detection never loaded. The
arena came back as a 4-corner rectangle on tanks that are not rectangles.

The decision is a PURE FUNCTION over ``project_data`` + settings. Callers keep
their own weight resolution, event publishing and dialog wiring, because those
legitimately differ. What must not diverge is the RULE.

Both keys DEGRADE on garbage rather than raising: a project file edited by hand
must not be able to turn "detect the arena" into a traceback. Falling through to
the next precedence level with a warning still produces an arena the user can
correct by hand; an exception produces nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import structlog

log = structlog.get_logger()

__all__ = ["ArenaDetectionPolicy", "ArenaMethod", "resolve_arena_detection"]

ArenaMethod = Literal["seg", "det"]

_VALID_METHODS: tuple[str, ...] = ("seg", "det")

#: Last-resort model family. Deliberately "det": it is the one that always
#: yields an outline (a box), so a project with no preference still detects.
_DEFAULT_METHOD: ArenaMethod = "det"

_TRUE_TOKENS = frozenset({"true", "1", "yes", "on"})
_FALSE_TOKENS = frozenset({"false", "0", "no", "off", ""})


@dataclass(frozen=True)
class ArenaDetectionPolicy:
    """Resolved answer to "which model, and keep the mask or box it?"."""

    method: ArenaMethod
    """``"seg"`` or ``"det"`` — selects both the weight slot and the branch
    taken inside :meth:`AquariumDetector.detect_aquariums`."""

    preserve_real_shape: bool
    """Keep the N-vertex mask outline instead of collapsing it to a 4-corner
    bounding box. Only meaningful with ``method == "seg"``; the detector
    ignores it otherwise, and a "det" model has no mask to preserve."""

    @property
    def uses_masks(self) -> bool:
        """True when the run should read ``results[*].masks``.

        The two flags are only useful together — asking for the real shape from
        a box model is not an error, it simply has no mask to give. Exposing the
        conjunction here keeps call sites from re-deriving it (and getting it
        subtly different, which is how the two flows drifted apart).
        """
        return self.method == "seg" and self.preserve_real_shape


def _coerce_method(value: object, *, source: str) -> ArenaMethod | None:
    """Normalize one candidate method, or ``None`` to fall through.

    ``None``/missing is an ordinary "no preference at this level" and is silent.
    A value that is present but not a valid method IS worth a warning: someone
    wrote it expecting it to matter.
    """
    if value is None:
        return None
    candidate = str(value).strip().lower()
    if candidate in _VALID_METHODS:
        return candidate  # type: ignore[return-value]
    if candidate:
        log.warning(
            "arena_detection_policy.method.invalid",
            source=source,
            value=str(value),
            valid=list(_VALID_METHODS),
        )
    return None


def _coerce_flag(value: object, *, source: str) -> bool | None:
    """Normalize one candidate boolean, or ``None`` to fall through.

    Tolerates the shapes a hand-edited ``project_config.json`` actually
    produces — ``true``, ``"true"``, ``1``, ``"yes"`` — because this key is
    edited by researchers, not only written by the wizard.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    token = str(value).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    log.warning(
        "arena_detection_policy.preserve_real_shape.invalid",
        source=source,
        value=str(value),
    )
    return None


def _settings_method(settings_obj: Any) -> ArenaMethod | None:
    model_selection = getattr(settings_obj, "model_selection", None)
    if model_selection is None:
        return None
    return _coerce_method(
        getattr(model_selection, "aquarium_method", None),
        source="settings.model_selection",
    )


def _settings_preserve_real_shape(settings_obj: Any) -> bool | None:
    detection_zones = getattr(settings_obj, "detection_zones", None)
    if detection_zones is None:
        return None
    return _coerce_flag(
        getattr(detection_zones, "preserve_real_aquarium_shape", None),
        source="settings.detection_zones",
    )


def resolve_arena_detection(
    project_data: dict[str, Any] | None,
    settings_obj: Any = None,
    *,
    requested_method: str = "auto",
) -> ArenaDetectionPolicy:
    """Resolve the arena detection model family and outline shape.

    Args:
        project_data: the open project's data dict. ``None``/empty is the
            ad-hoc single-video case and simply skips the project level.
        settings_obj: injected ``Settings`` (never the module singleton).
        requested_method: an explicit ``"seg"``/``"det"`` from the call site,
            which WINS over both stored preferences. ``"auto"`` (the default)
            means "no explicit request — consult the preferences". This is what
            lets a caller that genuinely knows better, e.g. a diagnostic run,
            pin the family without mutating anyone's configuration.

    Precedence:

    * ``method``: ``requested_method`` > ``project_data["model_selection"]
      ["aquarium_method"]`` > ``settings.model_selection.aquarium_method`` >
      ``"det"``.
    * ``preserve_real_shape``: ``project_data["preserve_real_aquarium_shape"]``
      > ``settings.detection_zones.preserve_real_aquarium_shape`` > ``False``.

    The two keys are resolved INDEPENDENTLY and on purpose: a project may pin
    the model family while leaving the outline choice to the global default, and
    the single-video dialog writes the shape flag into ``project_data`` without
    touching ``model_selection``.
    """
    data = project_data or {}

    explicit = _coerce_method(
        None if requested_method == "auto" else requested_method,
        source="requested_method",
    )
    project_method = _coerce_method(
        (data.get("model_selection") or {}).get("aquarium_method")
        if isinstance(data.get("model_selection"), dict)
        else None,
        source="project_data.model_selection",
    )
    method: ArenaMethod = (
        explicit or project_method or _settings_method(settings_obj) or _DEFAULT_METHOD
    )

    project_flag = _coerce_flag(
        data.get("preserve_real_aquarium_shape"),
        source="project_data",
    )
    preserve = project_flag
    if preserve is None:
        preserve = _settings_preserve_real_shape(settings_obj)
    if preserve is None:
        preserve = False

    policy = ArenaDetectionPolicy(method=method, preserve_real_shape=preserve)
    log.info(
        "arena_detection_policy.resolved",
        method=policy.method,
        preserve_real_shape=policy.preserve_real_shape,
        uses_masks=policy.uses_masks,
        requested_method=requested_method,
        from_project_method=project_method is not None,
        from_project_shape=project_flag is not None,
    )
    return policy
