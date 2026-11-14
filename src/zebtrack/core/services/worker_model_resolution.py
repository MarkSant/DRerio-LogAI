"""Which weight the processing worker loads, decided in the MAIN process (ADR-009).

Why this module exists
----------------------
The batch worker runs in a separate process and used to rebuild its model from
the global settings alone: ``settings.weights.<perspective>.det_filename``,
``yolo_model.path`` and an OpenVINO folder guessed from the file stem. It never
saw the project's ``model_overrides`` nor the :class:`WeightManager`, so the
weight a researcher chose for the project (say a rat detector) was silently
swapped for the zebrafish default while every report still came out complete.

:func:`resolve_worker_model` resolves the effective weight where all the
information lives -- project overrides, weight registry, settings -- and ships
the answer to the worker as a pickle-safe :class:`WorkerModelSpec`. The worker
uses the spec verbatim; its settings-only path survives only as a warned
fallback for callers that build no spec.

Precedence for the weight:

1. the project's ``model_overrides["slot_weights"]["<method>:zebrafish"]``;
2. the project's explicit ``model_overrides["active_weight"]`` (or the top-level
   ``active_weight`` of a pre-overrides project);
3. :meth:`WeightManager.get_weight_path_by_method` for the project's method and
   the configured perspective (honours runtime slot overrides and defaults);
4. the settings filenames (the worker's historical behaviour).

The animal method itself comes from the project's ``model_selection`` (written
by the wizard since 8.0) before the global ``settings.model_selection``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from zebtrack.core.detection.class_roles import ClassRoleSource, parse_class_roles

log = structlog.get_logger()

__all__ = [
    "VALID_ANIMAL_METHODS",
    "WorkerModelSpec",
    "resolve_project_animal_method",
    "resolve_project_class_roles",
    "resolve_worker_model",
]

VALID_ANIMAL_METHODS = ("det", "seg")
_ANIMAL_TARGET = "zebrafish"  # persistence contract of the slot keys (ADR-012)
_SLOT_SEPARATOR = ":"


@dataclass(frozen=True)
class WorkerModelSpec:
    """The model the worker must load. Plain values only: it crosses a process.

    Attributes:
        model_path: What the plugin opens (the ``.pt`` or the OpenVINO folder).
        model_type: ``"yolo"`` or ``"openvino"``.
        weight_sha256: sha256 of the ``.pt`` (``""`` when the file is missing).
        openvino_path: The OpenVINO export in use, ``None`` for PyTorch.
        class_roles: Explicit ``{class name: role}`` or ``None`` (aliases).
        class_roles_source: ``"project"``/``"weight"`` for an explicit map.
        weight_name: Registry name of the weight, ``None`` when not registered.
        animal_method: ``"det"`` or ``"seg"``.
        resolved_from: Which precedence level picked the weight (for logs).
    """

    model_path: str
    model_type: str
    weight_sha256: str
    openvino_path: str | None = None
    class_roles: dict[str, str] | None = None
    class_roles_source: str | None = None
    weight_name: str | None = None
    animal_method: str = "det"
    resolved_from: str = ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    """A collaborator's string answer, or ``""`` (stubs and mocks answer anything)."""
    return value if isinstance(value, str) else ""


def resolve_project_animal_method(project_data: Mapping[str, Any] | None, settings_obj: Any) -> str:
    """Animal method of the project, then of the settings, then ``"det"``.

    Args:
        project_data: The loaded project (``None`` outside a project).
        settings_obj: Injected settings (stubs and mocks tolerated).

    Returns:
        ``"det"`` or ``"seg"``.
    """
    project_method = _as_dict(_as_dict(project_data).get("model_selection")).get("animal_method")
    if project_method in VALID_ANIMAL_METHODS:
        return str(project_method)
    settings_method = getattr(getattr(settings_obj, "model_selection", None), "animal_method", None)
    if settings_method in VALID_ANIMAL_METHODS:
        return str(settings_method)
    return "det"


def _resolve_use_openvino(project_data: Mapping[str, Any] | None, settings_obj: Any) -> bool:
    data = _as_dict(project_data)
    override = _as_dict(data.get("model_overrides")).get("use_openvino")
    if isinstance(override, bool):
        return override
    if isinstance(data.get("use_openvino"), bool):
        return bool(data["use_openvino"])
    flag = getattr(getattr(settings_obj, "model_selection", None), "use_openvino", False)
    return flag is True


def _registered(weight_manager: Any, name: Any) -> dict[str, Any] | None:
    if weight_manager is None or not isinstance(name, str) or not name.strip():
        return None
    details = getattr(weight_manager, "weights", {}).get(name.strip())
    return details if isinstance(details, dict) else None


def _project_weight(
    weight_manager: Any, project_data: Mapping[str, Any] | None, method: str
) -> tuple[str | None, dict[str, Any] | None, str]:
    data = _as_dict(project_data)
    raw_overrides = data.get("model_overrides")
    overrides = _as_dict(raw_overrides)

    slot_name = _as_dict(overrides.get("slot_weights")).get(
        f"{method}{_SLOT_SEPARATOR}{_ANIMAL_TARGET}"
    )
    details = _registered(weight_manager, slot_name)
    if details is not None:
        return str(slot_name).strip(), details, "project_slot"

    active = overrides.get("active_weight")
    if not isinstance(raw_overrides, dict):
        active = data.get("active_weight")
    details = _registered(weight_manager, active)
    if details is not None:
        return str(active).strip(), details, "project_active_weight"

    for label, name in (("slot", slot_name), ("active_weight", active)):
        if isinstance(name, str) and name.strip():
            log.warning(
                "worker_model.project_weight_unregistered",
                source=label,
                weight=name,
                message="The project's weight is not in the registry; using the defaults.",
            )
    return None, None, ""


def _weight_by_path(
    weight_manager: Any, path: Path | str
) -> tuple[str | None, dict[str, Any] | None]:
    path = Path(path) if isinstance(path, str) else path
    try:
        wanted = path.resolve()
    except (OSError, ValueError):
        return None, None
    for name, details in getattr(weight_manager, "weights", {}).items():
        stored = details.get("path") if isinstance(details, dict) else None
        if not stored:
            continue
        try:
            if Path(stored).resolve() == wanted:
                return name, details
        except (OSError, ValueError):
            continue
    return None, None


def _settings_weight_path(settings_obj: Any, method: str, perspective: str | None) -> str:
    """The worker's historical settings-only resolution (last resort)."""
    weights = getattr(settings_obj, "weights", None)
    getter = getattr(weights, "get_filenames_for_perspective", None)
    if callable(getter):
        filename = None
        try:
            per = getter(perspective or "lateral")
            filename = per.det_filename if method == "det" else per.seg_filename
        except AttributeError:
            filename = None
        if isinstance(filename, str) and filename:
            from zebtrack.paths import resolve_weights_dir

            candidate = resolve_weights_dir(settings_obj) / filename
            if candidate.exists():
                return str(candidate)
    yolo_path = getattr(getattr(settings_obj, "yolo_model", None), "path", "")
    return yolo_path if isinstance(yolo_path, str) else ""


def resolve_project_class_roles(
    project_data: Mapping[str, Any] | None,
    weight_details: Mapping[str, Any] | None,
    weight_sha256: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Explicit class roles for the effective weight, and where they came from.

    The project map wins only while it was made for this exact weight
    (``model_overrides.class_roles_weight_sha256``); a map recorded for another
    weight is discarded with a warning. The weight entry's ``class_roles`` come
    next. ``(None, None)`` means "resolve by aliases" (ADR-009).

    Args:
        project_data: The loaded project.
        weight_details: The weight's registry entry.
        weight_sha256: sha256 of the weight that will be loaded.

    Returns:
        ``(roles, source)`` with ``source`` in ``{"project", "weight"}``.
    """
    overrides = _as_dict(_as_dict(project_data).get("model_overrides"))
    project_roles = parse_class_roles(overrides.get("class_roles"))
    if project_roles is not None:
        recorded_sha = overrides.get("class_roles_weight_sha256")
        if weight_sha256 and recorded_sha == weight_sha256:
            return (
                {name: role.value for name, role in project_roles.items()},
                ClassRoleSource.PROJECT.value,
            )
        log.warning(
            "worker_model.project_class_roles.sha_mismatch",
            recorded_sha=recorded_sha,
            weight_sha=weight_sha256 or None,
            message="The project's class roles were set for another weight; ignoring them.",
        )
    weight_roles = parse_class_roles(_as_dict(weight_details).get("class_roles"))
    if weight_roles is not None:
        return (
            {name: role.value for name, role in weight_roles.items()},
            ClassRoleSource.WEIGHT.value,
        )
    return None, None


def resolve_worker_model(
    weight_manager: Any,
    settings_obj: Any,
    project_data: Mapping[str, Any] | None,
) -> WorkerModelSpec:
    """Resolve the effective weight for the worker (precedence in the module doc).

    Args:
        weight_manager: The :class:`WeightManager` (``None`` → settings only).
        settings_obj: Injected settings.
        project_data: The loaded project, or ``None`` for a single video.

    Returns:
        The :class:`WorkerModelSpec` to put in the worker configuration.
    """
    method = resolve_project_animal_method(project_data, settings_obj)
    use_openvino = _resolve_use_openvino(project_data, settings_obj)
    perspective = getattr(
        getattr(settings_obj, "behavioral_analysis", None), "aquarium_perspective", None
    )
    if not isinstance(perspective, str):
        perspective = None

    name, details, resolved_from = _project_weight(weight_manager, project_data, method)

    if details is None and weight_manager is not None:
        path = weight_manager.get_weight_path_by_method(method, "animal", perspective=perspective)
        if isinstance(path, str) and path:
            name, details = _weight_by_path(weight_manager, path)
            resolved_from = "weight_manager"

    if details is not None and name is not None:
        pt_path = str(details.get("path") or "")
        sha = _text(weight_manager.get_weight_sha256(name))
    else:
        name = None
        pt_path = _settings_weight_path(settings_obj, method, perspective)
        resolved_from = "settings"
        sha = _text(weight_manager.sha256_for_path(pt_path)) if weight_manager is not None else ""
        if not sha and pt_path and os.path.isfile(pt_path):
            from zebtrack.utils import calculate_sha256

            sha = calculate_sha256(pt_path)

    model_type = "yolo"
    model_path = pt_path
    openvino_path: str | None = None
    if use_openvino:
        current = (
            name is not None
            and weight_manager is not None
            and weight_manager.openvino_cache_is_current(name) is True
        )
        if current:
            assert details is not None
            openvino_path = str(details.get("openvino_path"))
            model_type = "openvino"
            model_path = openvino_path
        else:
            log.warning(
                "worker_model.openvino_not_ready",
                weight=name,
                fallback="yolo",
                message="OpenVINO requested but no export of this exact weight exists.",
            )

    roles, roles_source = resolve_project_class_roles(project_data, details, sha)

    spec = WorkerModelSpec(
        model_path=model_path,
        model_type=model_type,
        weight_sha256=sha,
        openvino_path=openvino_path,
        class_roles=roles,
        class_roles_source=roles_source,
        weight_name=name,
        animal_method=method,
        resolved_from=resolved_from,
    )
    log.info(
        "worker_model.resolved",
        weight=name,
        model_type=model_type,
        model_path=model_path,
        animal_method=method,
        resolved_from=resolved_from,
        class_roles_source=roles_source,
        weight_sha256=sha[:12] if sha else None,
    )
    return spec
