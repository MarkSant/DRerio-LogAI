"""Editor for what each class of a detection weight IS (ADR-009).

Why this module exists
----------------------
A weight such as the Barnes-maze one, ``{0: arena, 1: experimenter, 2: rat,
3: start_box}``, needs somebody to say that the rat is the SUBJECT, the arena is
the ARENA and the experimenter and the start box are CONTEXT (observed, never
tracked). The resolver in :mod:`zebtrack.core.detection.class_roles` accepts that
answer from two places, and this editor writes to both:

- **weight scope** — the ``class_roles`` of the weight's ``weights_config.json``
  entry (``WeightManager.set_weight_class_roles``). Every project that uses the
  weight sees it;
- **project scope** — ``project_data["model_overrides"]["class_roles"]`` plus
  ``class_roles_weight_sha256``, the sha256 of the project's EFFECTIVE weight.
  The resolver trusts it only while that sha matches the weight being loaded, so
  a retrained weight saved under the same name never inherits stale roles.

Layers
------
Everything that decides something is plain Python and is tested without Tk:
building and validating the map (at least one subject, at most one arena),
pre-filling it from the current resolution, detecting a project map recorded for
another weight, persisting each scope (the project edit is undone in memory when
the save fails) and announcing the change with ``UIEvents.CLASS_ROLES_CHANGED``.
:class:`ClassRolesPanel` only shuttles widget values into that model.

Reading the class names means loading the model (``ModelService.inspect_model``),
which takes seconds the first time. It runs on a daemon thread and comes back to
Tk through ``after(0, ...)``; the names are cached by ``(weight, sha256)``.

The role tokens are persistence contracts and are never translated; only their
labels are (:func:`role_labels`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from tkinter import StringVar, TclError, Toplevel, ttk
from typing import Any

import structlog

from zebtrack.core.detection.class_aliases import ClassAliases, normalize_class_name
from zebtrack.core.detection.class_roles import (
    ClassRole,
    ClassRoleMap,
    ClassRoleSource,
    ClassRolesUnresolvedError,
    parse_class_roles,
    resolve_class_role_map,
)
from zebtrack.core.services.worker_model_resolution import resolve_worker_model
from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()

__all__ = [
    "OVERRIDES_KEY",
    "PROJECT_ROLES_KEY",
    "PROJECT_SHA_KEY",
    "ROLE_ORDER",
    "ClassNamesCache",
    "ClassRolesDialog",
    "ClassRolesEditor",
    "ClassRolesPanel",
    "ClassRolesSaveError",
    "ClassRolesScope",
    "ClassRolesView",
    "ConflictingRolesError",
    "NoSubjectClassError",
    "ProjectClassRolesContext",
    "RoleMapError",
    "RoleRow",
    "SeveralArenaClassesError",
    "TargetWeight",
    "build_role_mapping",
    "build_view",
    "coerce_class_names",
    "model_service_names_loader",
    "named_target_weight",
    "overlay_roles_for",
    "project_roles_are_stale",
    "project_target_weight",
    "role_from_label",
    "role_labels",
    "role_map_error_message",
    "rows_from_role_map",
    "source_labels",
    "store_project_roles",
    "store_weight_roles",
    "stored_project_roles",
]

OVERRIDES_KEY = "model_overrides"
PROJECT_ROLES_KEY = "class_roles"
PROJECT_SHA_KEY = "class_roles_weight_sha256"

#: Order of the roles in every dropdown.
ROLE_ORDER: tuple[ClassRole, ...] = (
    ClassRole.SUBJECT,
    ClassRole.ARENA,
    ClassRole.CONTEXT,
    ClassRole.IGNORED,
)


class ClassRolesScope(StrEnum):
    """Where an edit is stored. The values travel in ``ClassRolesChangedPayload``."""

    WEIGHT = "weight"
    PROJECT = "project"


# ---------------------------------------------------------------------------
# Labels (functions: ``_()`` resolves the catalogue at call time)
# ---------------------------------------------------------------------------


def role_labels() -> dict[ClassRole, str]:
    """User-facing label of each role token."""
    return {
        ClassRole.SUBJECT: _("Subject (tracked animal)"),
        ClassRole.ARENA: _("Arena"),
        ClassRole.CONTEXT: _("Context (observed, not tracked)"),
        ClassRole.IGNORED: _("Ignored"),
    }


def role_from_label(label: str) -> ClassRole | None:
    """Role token behind a dropdown label (``None`` for an unknown label)."""
    for role, text in role_labels().items():
        if text == label:
            return role
    return None


def source_labels() -> dict[ClassRoleSource, str]:
    """Where the roles in use came from, in words."""
    return {
        ClassRoleSource.PROJECT: _("set in this project"),
        ClassRoleSource.WEIGHT: _("saved with the weight"),
        ClassRoleSource.ALIASES: _("automatic, recognised by class name"),
        ClassRoleSource.LEGACY_POSITIONAL: _("automatic, by class position (no class names)"),
    }


# ---------------------------------------------------------------------------
# Validation (typed errors; the message comes from the TYPE, never the text)
# ---------------------------------------------------------------------------


class RoleMapError(ValueError):
    """The roles chosen in the editor cannot be stored."""


class NoSubjectClassError(RoleMapError):
    """No class was given the ``subject`` role."""


class SeveralArenaClassesError(RoleMapError):
    """More than one class name was given the ``arena`` role."""

    def __init__(self, names: Iterable[str]) -> None:
        self.names = tuple(names)
        super().__init__(f"several arena classes: {self.names}")


class ConflictingRolesError(RoleMapError):
    """Two classes with the same normalised name were given different roles.

    Roles are stored by NAME, so two ids that share a name share one role.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"conflicting roles for class name {name!r}")


class ClassRolesSaveError(RuntimeError):
    """Persisting the roles failed; nothing was changed in memory."""


def role_map_error_message(exc: RoleMapError) -> str:
    """User-facing sentence for a validation error, chosen by its type."""
    if isinstance(exc, NoSubjectClassError):
        return _("Choose at least one class as the subject (the animal to track).")
    if isinstance(exc, SeveralArenaClassesError):
        return _("Only one class can be the arena; {names} are all marked as arena.").format(
            names=", ".join(f"'{name}'" for name in exc.names)
        )
    if isinstance(exc, ConflictingRolesError):
        return _(
            "Classes named '{name}' must share one role: roles are stored by class name."
        ).format(name=exc.name)
    return _("The class roles are not valid.")


# ---------------------------------------------------------------------------
# Rows ⇄ map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleRow:
    """One class of the weight, as shown in the editor."""

    class_id: int
    name: str
    role: ClassRole


def coerce_class_names(raw: Any) -> dict[int, str]:
    """A model's ``names`` (mapping or sequence) as ``{int id: str name}``."""
    if isinstance(raw, list | tuple):
        raw = dict(enumerate(raw))
    if not isinstance(raw, Mapping):
        return {}
    names: dict[int, str] = {}
    for key, value in raw.items():
        try:
            class_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, str):
            names[class_id] = value
    return names


def rows_from_role_map(role_map: ClassRoleMap, *, by_name_only: bool = False) -> list[RoleRow]:
    """Pre-fill the editor from a resolved map, one row per class id.

    By default each row shows what the detector really does with that id
    (:meth:`ClassRoleMap.role_of_id`), positional legacy ids included. With
    ``by_name_only`` the rows carry only the roles a NAME earned, which is what
    an unresolved weight must show: offering the positional guess as a default
    would let one click save "track class 1" for a weight the gate refuses.
    """
    rows: list[RoleRow] = []
    for class_id in sorted(role_map.names):
        name = role_map.names[class_id]
        role = role_map.role_of_name(name) if by_name_only else role_map.role_of_id(class_id)
        rows.append(RoleRow(class_id=class_id, name=name, role=role))
    return rows


def build_role_mapping(rows: Iterable[RoleRow]) -> dict[str, str]:
    """Validate the edited rows and turn them into the stored ``{name: token}``.

    Raises:
        ConflictingRolesError: two classes with the same name, different roles.
        NoSubjectClassError: no subject class.
        SeveralArenaClassesError: more than one arena class name.
    """
    roles: dict[str, ClassRole] = {}
    for row in rows:
        key = normalize_class_name(row.name)
        if not key:
            continue
        previous = roles.get(key)
        if previous is not None and previous != row.role:
            raise ConflictingRolesError(row.name)
        roles[key] = row.role
    if ClassRole.SUBJECT not in roles.values():
        raise NoSubjectClassError("no subject class")
    arenas = sorted(name for name, role in roles.items() if role is ClassRole.ARENA)
    if len(arenas) > 1:
        raise SeveralArenaClassesError(arenas)
    return {name: role.value for name, role in roles.items()}


def overlay_roles_for(role_map: ClassRoleMap | None) -> dict[int, str] | None:
    """``{class id: role token}`` for the overlays, or ``None`` for legacy colours.

    Only an EXPLICIT map (project or weight) recolours the boxes: an alias map of
    a zebrafish weight must leave the 7.2 overlay exactly as it was.
    """
    if role_map is None or not role_map.is_explicit or not role_map.names:
        return None
    return {class_id: role_map.role_of_id(class_id).value for class_id in sorted(role_map.names)}


# ---------------------------------------------------------------------------
# The weight being edited
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetWeight:
    """A registered weight: name, sha256 of its ``.pt`` and registry entry."""

    name: str | None
    sha256: str = ""
    details: Mapping[str, Any] | None = None

    @property
    def cache_key(self) -> tuple[str, str] | None:
        """Key of the class-name cache (``None``: nothing worth caching)."""
        if not self.name or not self.sha256:
            return None
        return self.name, self.sha256


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _details(weight_manager: Any, name: str | None) -> Mapping[str, Any] | None:
    if not name or weight_manager is None:
        return None
    details = weight_manager.get_weight_details(name)
    return details if isinstance(details, Mapping) else None


def named_target_weight(weight_manager: Any, name: str | None) -> TargetWeight:
    """The registered weight called ``name`` (weight scope, wizard)."""
    if not name or weight_manager is None:
        return TargetWeight(name=None)
    return TargetWeight(
        name=name,
        sha256=_text(weight_manager.get_weight_sha256(name)),
        details=_details(weight_manager, name),
    )


def project_target_weight(
    weight_manager: Any, settings_obj: Any, project_data: Mapping[str, Any] | None
) -> TargetWeight:
    """The project's EFFECTIVE weight — the one the processing worker loads.

    Delegates to :func:`resolve_worker_model`, the single resolver the batch
    worker uses (project slot > project active weight > registry > settings), so
    the sha recorded with a project map is the sha the worker will compare.
    """
    if weight_manager is None:
        return TargetWeight(name=None)
    spec = resolve_worker_model(weight_manager, settings_obj, project_data)
    return TargetWeight(
        name=spec.weight_name,
        sha256=spec.weight_sha256,
        details=_details(weight_manager, spec.weight_name),
    )


# ---------------------------------------------------------------------------
# Project storage
# ---------------------------------------------------------------------------


def _overrides(project_data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    raw = project_data.get(OVERRIDES_KEY) if isinstance(project_data, Mapping) else None
    return raw if isinstance(raw, Mapping) else {}


def stored_project_roles(
    project_data: Mapping[str, Any] | None,
) -> tuple[dict[str, ClassRole] | None, str | None]:
    """The project's explicit map and the sha it was recorded for."""
    overrides = _overrides(project_data)
    sha = overrides.get(PROJECT_SHA_KEY)
    return parse_class_roles(overrides.get(PROJECT_ROLES_KEY)), sha if isinstance(
        sha, str
    ) else None


def project_roles_are_stale(project_data: Mapping[str, Any] | None, effective_sha: str) -> bool:
    """Whether the project holds a map the resolver will DISCARD.

    Same rule as the resolver: a project map counts only while its recorded sha
    equals the sha of the weight being loaded.
    """
    roles, sha = stored_project_roles(project_data)
    if roles is None:
        return False
    return not effective_sha or sha != effective_sha


_MISSING = object()


def store_project_roles(
    project_manager: Any, mapping: Mapping[str, str] | None, weight_sha256: str | None
) -> bool:
    """Write (or clear, with ``None``) the project map and persist the project.

    The edit is made in ``project_data`` and saved; when the save raises, the
    previous values are put back so memory never disagrees with disk.

    Returns:
        ``True`` when written to disk, ``False`` when the project has no path yet
        (the edit stays in memory and is saved with the project).

    Raises:
        ClassRolesSaveError: no project, or the save failed (memory restored).
    """
    project_data = getattr(project_manager, "project_data", None)
    if not isinstance(project_data, dict):
        raise ClassRolesSaveError("no project is loaded")

    raw_overrides = project_data.get(OVERRIDES_KEY, _MISSING)
    overrides = raw_overrides if isinstance(raw_overrides, dict) else {}
    previous_roles = overrides.get(PROJECT_ROLES_KEY, _MISSING)
    previous_sha = overrides.get(PROJECT_SHA_KEY, _MISSING)

    overrides[PROJECT_ROLES_KEY] = dict(mapping) if mapping else None
    overrides[PROJECT_SHA_KEY] = weight_sha256 if mapping else None
    project_data[OVERRIDES_KEY] = overrides

    if not getattr(project_manager, "project_path", None):
        return False
    try:
        project_manager.save_project()
    # except Exception justified: disk/serialisation boundary; the edit is
    # undone and the failure is re-raised as one typed error for the UI.
    except Exception as exc:
        if raw_overrides is _MISSING:
            project_data.pop(OVERRIDES_KEY, None)
        else:
            project_data[OVERRIDES_KEY] = raw_overrides
            for key, value in (
                (PROJECT_ROLES_KEY, previous_roles),
                (PROJECT_SHA_KEY, previous_sha),
            ):
                if value is _MISSING:
                    overrides.pop(key, None)
                else:
                    overrides[key] = value
        log.error("class_roles_panel.project_save_failed", error=str(exc), exc_info=True)
        raise ClassRolesSaveError(str(exc)) from exc
    return True


def store_weight_roles(weight_manager: Any, name: str, mapping: Mapping[str, str] | None) -> None:
    """Write (or clear) the roles on a weight's registry entry.

    ``WeightManager.set_weight_class_roles`` edits the entry and then saves the
    JSON; when the save raises, the entry is restored here.

    Raises:
        ClassRolesSaveError: unknown weight, invalid map or failed save.
    """
    details = weight_manager.get_weight_details(name) if weight_manager is not None else None
    if not isinstance(details, dict):
        raise ClassRolesSaveError(f"unknown weight {name!r}")
    previous = details.get(PROJECT_ROLES_KEY, _MISSING)
    try:
        stored = weight_manager.set_weight_class_roles(name, dict(mapping) if mapping else None)
    # except Exception justified: WeightManager.save_weights raises OSError (and a
    # stub anything); the entry is restored and one typed error surfaces.
    except Exception as exc:
        if previous is _MISSING:
            details.pop(PROJECT_ROLES_KEY, None)
        else:
            details[PROJECT_ROLES_KEY] = previous
        log.error("class_roles_panel.weight_save_failed", weight=name, error=str(exc))
        raise ClassRolesSaveError(str(exc)) from exc
    if stored is not True:
        raise ClassRolesSaveError(f"weight {name!r} refused the class roles")


# ---------------------------------------------------------------------------
# Resolution for display
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassRolesView:
    """Everything the editor shows for one weight.

    Attributes:
        target: The weight being edited.
        class_names: ``{id: name}`` read from the model (empty: unreadable).
        role_map: The resolution in force (``None`` without class names).
        rows: The pre-filled editor rows.
        unresolved: The gate (``strict``) would REFUSE this weight: no class
            can be the subject. The rows then carry no positional guess.
        stale_project_roles: The project holds a map recorded for another
            weight file; the resolver ignores it and a save replaces it.
    """

    target: TargetWeight
    class_names: dict[int, str]
    role_map: ClassRoleMap | None
    rows: tuple[RoleRow, ...]
    unresolved: bool = False
    stale_project_roles: bool = False


def build_view(
    class_names: Mapping[int, str],
    *,
    scope: ClassRolesScope,
    target: TargetWeight,
    project_data: Mapping[str, Any] | None = None,
    aliases: ClassAliases | None = None,
) -> ClassRolesView:
    """Resolve the weight's roles the way the detector will, for the editor.

    The weight scope ignores the project map (it edits what every project sees);
    the project scope applies it under the resolver's own sha rule.
    """
    names = dict(class_names)
    stale = scope is ClassRolesScope.PROJECT and project_roles_are_stale(
        project_data, target.sha256
    )
    if not names:
        return ClassRolesView(
            target=target, class_names={}, role_map=None, rows=(), stale_project_roles=stale
        )

    project_override: Any = None
    project_sha: str | None = None
    if scope is ClassRolesScope.PROJECT:
        overrides = _overrides(project_data)
        project_override = overrides.get(PROJECT_ROLES_KEY)
        recorded = overrides.get(PROJECT_SHA_KEY)
        project_sha = recorded if isinstance(recorded, str) else None

    kwargs: dict[str, Any] = {
        "project_override": project_override,
        "project_override_sha": project_sha,
        "weight_entry": target.details,
        "weight_sha256": target.sha256 or None,
        "aliases": aliases,
    }
    unresolved = False
    try:
        role_map = resolve_class_role_map(names, strict=True, **kwargs)
    except ClassRolesUnresolvedError:
        unresolved = True
        role_map = resolve_class_role_map(names, strict=False, **kwargs)
    rows = rows_from_role_map(role_map, by_name_only=unresolved)
    return ClassRolesView(
        target=target,
        class_names=names,
        role_map=role_map,
        rows=tuple(rows),
        unresolved=unresolved,
        stale_project_roles=stale,
    )


# ---------------------------------------------------------------------------
# Editor (no Tk): the two scopes behind one interface
# ---------------------------------------------------------------------------


class ClassRolesEditor:
    """Load, save and clear class roles in one scope, and announce each change.

    Args:
        scope: Where the roles are stored.
        weight_manager: Injected ``WeightManager``.
        project_manager: Injected ``ProjectManager`` (project scope; it also
            decides the effective weight).
        settings_obj: Injected settings (alias vocabularies, weight fallback).
        event_bus: ``EventBusV2`` for ``CLASS_ROLES_CHANGED`` (optional).
        weight_name: The weight edited in weight scope.
    """

    def __init__(
        self,
        *,
        scope: ClassRolesScope,
        weight_manager: Any,
        project_manager: Any = None,
        settings_obj: Any = None,
        event_bus: Any = None,
        weight_name: str | None = None,
    ) -> None:
        self.scope = scope
        self.weight_manager = weight_manager
        self.project_manager = project_manager
        self.settings_obj = settings_obj
        self.event_bus = event_bus
        self.weight_name = weight_name
        self._names: dict[int, str] = {}
        self._target: TargetWeight | None = None

    def project_data(self) -> dict[str, Any] | None:
        data = getattr(self.project_manager, "project_data", None)
        return data if isinstance(data, dict) else None

    def target(self) -> TargetWeight:
        """The weight this editor edits right now."""
        if self.scope is ClassRolesScope.PROJECT:
            return project_target_weight(
                self.weight_manager, self.settings_obj, self.project_data()
            )
        return named_target_weight(self.weight_manager, self.weight_name)

    def view(
        self, class_names: Mapping[int, str], target: TargetWeight | None = None
    ) -> ClassRolesView:
        """Resolve the roles in force for ``class_names`` of the target weight."""
        resolved_target = target if target is not None else self.target()
        self._target = resolved_target
        self._names = dict(class_names)
        return build_view(
            self._names,
            scope=self.scope,
            target=resolved_target,
            project_data=self.project_data(),
            aliases=ClassAliases.from_settings(self.settings_obj),
        )

    def save(self, rows: Iterable[RoleRow]) -> ClassRolesView:
        """Validate and store the edited rows, then announce them.

        Raises:
            RoleMapError: the rows are not a valid map (nothing stored).
            ClassRolesSaveError: storing failed (nothing changed in memory).
        """
        mapping = build_role_mapping(rows)
        return self._store(mapping)

    def restore_automatic(self) -> ClassRolesView:
        """Remove this scope's explicit map (the resolver falls back a level).

        Raises:
            ClassRolesSaveError: storing failed (nothing changed in memory).
        """
        return self._store(None)

    def _store(self, mapping: dict[str, str] | None) -> ClassRolesView:
        target = self._target if self._target is not None else self.target()
        if not target.name:
            raise ClassRolesSaveError("no weight to store the class roles for")
        if self.scope is ClassRolesScope.PROJECT:
            store_project_roles(self.project_manager, mapping, target.sha256 or None)
        else:
            store_weight_roles(self.weight_manager, target.name, mapping)
        refreshed = named_target_weight(self.weight_manager, target.name)
        view = self.view(self._names, refreshed)
        log.info(
            "class_roles_panel.saved",
            scope=self.scope.value,
            weight=target.name,
            roles=mapping,
            source=None if view.role_map is None else view.role_map.source.value,
        )
        self._publish(view, mapping)
        return view

    def _publish(self, view: ClassRolesView, mapping: dict[str, str] | None) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            Event(
                type=UIEvents.CLASS_ROLES_CHANGED,
                data=payloads.ClassRolesChangedPayload(
                    scope=self.scope.value,
                    weight_name=view.target.name,
                    weight_sha256=view.target.sha256 or None,
                    class_roles=mapping,
                    source=None if view.role_map is None else view.role_map.source.value,
                ),
                source="ClassRolesEditor",
            )
        )


# ---------------------------------------------------------------------------
# Class names (slow: loads the model) — cache + loader
# ---------------------------------------------------------------------------


class ClassNamesCache:
    """Thread-safe ``{(weight name, sha256): {id: name}}``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._names: dict[tuple[str, str], dict[int, str]] = {}

    def get(self, target: TargetWeight) -> dict[int, str] | None:
        key = target.cache_key
        if key is None:
            return None
        with self._lock:
            cached = self._names.get(key)
            return None if cached is None else dict(cached)

    def put(self, target: TargetWeight, names: Mapping[int, str]) -> None:
        key = target.cache_key
        if key is None or not names:
            return
        with self._lock:
            self._names[key] = dict(names)


#: Shared by every editor of the session: one model load per weight file.
SHARED_CLASS_NAMES = ClassNamesCache()


def model_service_names_loader(model_service: Any) -> Callable[[str], dict[int, str]]:
    """``weight name -> {id: name}`` through ``ModelService.inspect_model``."""

    def _load(weight_name: str) -> dict[int, str]:
        try:
            info = model_service.inspect_model(weight_name)
        except (ValueError, ImportError) as exc:
            log.warning("class_roles_panel.inspect_failed", weight=weight_name, error=str(exc))
            return {}
        raw = info.get("class_names") if isinstance(info, Mapping) else None
        return coerce_class_names(raw)

    return _load


def _safe_load(loader: Callable[[str], Mapping[Any, Any]], name: str) -> dict[int, str]:
    try:
        return coerce_class_names(loader(name))
    # except Exception justified: model loading is a heterogeneous ML boundary
    # (torch, file system); an unreadable model is shown as such, never raised
    # on a worker thread where nobody would see it.
    except Exception as exc:
        log.warning("class_roles_panel.load_names_failed", weight=name, error=str(exc))
        return {}


# ---------------------------------------------------------------------------
# Project context for the zone tab (overlay roles + names for the window editor)
# ---------------------------------------------------------------------------


class ProjectClassRolesContext:
    """Class names and explicit role map of the project's effective weight.

    Feeds the analysis-window editor (class names) and both overlays (roles).
    The weight is resolved on the calling (Tk) thread; only the model load runs
    on a daemon thread, and its result is delivered back through ``schedule``.

    Args:
        weight_manager: Injected ``WeightManager``.
        settings_obj: Injected settings.
        project_manager_getter: Returns the CURRENT project manager (it is
            replaced when a project is closed).
        names_loader: ``weight name -> {id: name}``.
        schedule: Runs a callable on the Tk thread (``root.after(0, fn)``).
        cache: Class-name cache (the session-wide one by default).
        on_change: Called on the Tk thread after names/roles changed.
        background: Load on a thread (``False`` only in tests).
    """

    def __init__(
        self,
        *,
        weight_manager: Any,
        settings_obj: Any,
        project_manager_getter: Callable[[], Any],
        names_loader: Callable[[str], Mapping[Any, Any]],
        schedule: Callable[[Callable[[], None]], Any],
        cache: ClassNamesCache | None = None,
        on_change: Callable[[], None] | None = None,
        background: bool = True,
    ) -> None:
        self.weight_manager = weight_manager
        self.settings_obj = settings_obj
        self._project_manager_getter = project_manager_getter
        self._loader = names_loader
        self._schedule = schedule
        self._cache = cache if cache is not None else SHARED_CLASS_NAMES
        self._on_change = on_change
        self._background = background
        self._pending: TargetWeight | None = None
        self._names: dict[int, str] = {}
        self._overlay_roles: dict[int, str] | None = None

    def class_names(self) -> list[str]:
        """Names of the effective weight's classes, by id (``[]`` until loaded)."""
        return [self._names[class_id] for class_id in sorted(self._names)]

    def class_names_by_id(self) -> dict[int, str]:
        return dict(self._names)

    def overlay_roles(self) -> dict[int, str] | None:
        """``{id: role token}`` of an explicit map, ``None`` for legacy colours."""
        return None if self._overlay_roles is None else dict(self._overlay_roles)

    def _project_data(self) -> dict[str, Any] | None:
        data = getattr(self._project_manager_getter(), "project_data", None)
        return data if isinstance(data, dict) else None

    def on_project_manager_replaced(self, _new_manager: Any) -> None:
        """The project closed or changed: its effective weight may differ."""
        self.refresh()

    def refresh(self) -> None:
        """Re-resolve the effective weight and (re)load its names and roles."""
        try:
            target = project_target_weight(
                self.weight_manager, self.settings_obj, self._project_data()
            )
        # except Exception justified: the context is optional decoration of the
        # zone tab; a registry that cannot resolve leaves the legacy behaviour.
        except Exception:
            log.warning("class_roles_context.resolve_failed", exc_info=True)
            target = TargetWeight(name=None)
        self._pending = target
        if not target.name:
            self._apply(target, {})
            return
        cached = self._cache.get(target)
        if cached is not None:
            self._apply(target, cached)
            return

        loader = self._loader
        cache = self._cache
        name = target.name

        def _work() -> None:
            names = _safe_load(loader, name)
            cache.put(target, names)
            self._schedule(lambda: self._apply(target, names))

        if self._background:
            threading.Thread(target=_work, name="ClassRolesContextNames", daemon=True).start()
        else:
            _work()

    def _apply(self, target: TargetWeight, names: Mapping[int, str]) -> None:
        if target != self._pending:
            return  # a newer refresh superseded this load
        view = build_view(
            names,
            scope=ClassRolesScope.PROJECT,
            target=target,
            project_data=self._project_data(),
            aliases=ClassAliases.from_settings(self.settings_obj),
        )
        self._names = dict(view.class_names)
        self._overlay_roles = overlay_roles_for(view.role_map)
        log.info(
            "class_roles_context.resolved",
            weight=target.name,
            classes=len(self._names),
            explicit=self._overlay_roles is not None,
        )
        if self._on_change is not None:
            self._on_change()


# ---------------------------------------------------------------------------
# Tk panel
# ---------------------------------------------------------------------------


class ClassRolesPanel(ttk.Frame):
    """Table ``id | class | role`` for one weight, with the role chosen from a list.

    Args:
        parent: Tk parent.
        editor: The scope's :class:`ClassRolesEditor`.
        names_loader: ``weight name -> {id: name}`` (slow; runs on a thread).
        persist: ``True`` shows "Save" and stores immediately; ``False`` (the
            wizard) only edits a draft read back with :meth:`draft_mapping`.
        cache: Class-name cache (session-wide by default).
        tree_height: Visible rows of the table.
        wraplength: Width of the explanatory labels.
        background: Load names on a thread (``False`` only in tests).
        load_when_mapped: Defer the model load until the panel is first shown
            (the wizard's collapsed section must not load a model nobody looks at).
    """

    def __init__(
        self,
        parent: Any,
        *,
        editor: ClassRolesEditor,
        names_loader: Callable[[str], Mapping[Any, Any]],
        persist: bool = True,
        cache: ClassNamesCache | None = None,
        tree_height: int = 6,
        wraplength: int = 420,
        background: bool = True,
        load_when_mapped: bool = False,
    ) -> None:
        super().__init__(parent)
        self.editor = editor
        self._loader = names_loader
        self._persist = persist
        self._cache = cache if cache is not None else SHARED_CLASS_NAMES
        self._background = background
        self._wraplength = wraplength
        self._load_when_mapped = load_when_mapped
        self._loaded_once = False

        self.role_choice = StringVar(master=self)
        self._rows: list[RoleRow] = []
        self._view: ClassRolesView | None = None
        self._pending: TargetWeight | None = None

        self._weight_label: ttk.Label | None = None
        self._source_label: ttk.Label | None = None
        self._warning: ttk.Label | None = None
        self._status: ttk.Label | None = None
        self._tree: ttk.Treeview | None = None
        self._role_combo: ttk.Combobox | None = None
        self._save_button: ttk.Button | None = None
        self._restore_button: ttk.Button | None = None

        self._build(tree_height)
        if load_when_mapped:
            self.bind("<Map>", self._on_map, add="+")
        else:
            self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self, tree_height: int) -> None:
        self._weight_label = ttk.Label(self, text="", font=("Segoe UI", 9, "bold"))
        self._weight_label.pack(anchor="w")
        self._source_label = ttk.Label(
            self, text="", foreground="#555555", wraplength=self._wraplength, justify="left"
        )
        self._source_label.pack(anchor="w", pady=(0, 4))
        self._warning = ttk.Label(
            self, text="", foreground="#b00020", wraplength=self._wraplength, justify="left"
        )

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            table,
            columns=("id", "name", "role"),
            show="headings",
            height=tree_height,
            selectmode="extended",
        )
        tree.heading("id", text=_("Id"))
        tree.heading("name", text=_("Class"))
        tree.heading("role", text=_("Role"))
        tree.column("id", width=40, anchor="center", stretch=False)
        tree.column("name", width=140, anchor="w")
        tree.column("role", width=200, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree = tree

        editor_row = ttk.Frame(self)
        editor_row.pack(fill="x", pady=(4, 0))
        ttk.Label(editor_row, text=_("Role of the selected class(es):")).pack(side="left")
        combo = ttk.Combobox(
            editor_row,
            textvariable=self.role_choice,
            state="readonly",
            values=[role_labels()[role] for role in ROLE_ORDER],
            width=30,
        )
        combo.pack(side="left", padx=(4, 0))
        combo.bind("<<ComboboxSelected>>", self._on_role_chosen)
        self._role_combo = combo

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 0))
        self._restore_button = ttk.Button(
            buttons, text=_("Restore automatic"), command=self.restore_automatic
        )
        self._restore_button.pack(side="left")
        if self._persist:
            self._save_button = ttk.Button(buttons, text=_("Save"), command=self.save)
            self._save_button.pack(side="right")

        self._status = ttk.Label(self, text="", foreground="gray", wraplength=self._wraplength)
        self._status.pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def is_alive(self) -> bool:
        """True while the Tk widgets exist (the panel can outlive its tab)."""
        try:
            return bool(self.winfo_exists())
        # except Exception justified: Tk raises assorted errors once the
        # interpreter behind the widget is gone; "not alive" is the answer.
        except Exception:
            return False

    def _on_map(self, _event: Any = None) -> None:
        if not self._loaded_once:
            self.refresh()

    def set_weight_name(self, name: str | None) -> None:
        """Edit another weight (weight scope / wizard)."""
        if name == self.editor.weight_name and self._loaded_once:
            return
        self.editor.weight_name = name
        if self._load_when_mapped and not self._loaded_once and not self.winfo_ismapped():
            return
        self.refresh()

    def refresh(self) -> None:
        """Re-resolve the target weight and (re)load its classes."""
        if not self.is_alive():
            return
        self._loaded_once = True
        try:
            target = self.editor.target()
        # except Exception justified: an unresolvable registry must show a
        # message in the panel, not a traceback in the Tk callback.
        except Exception:
            log.warning("class_roles_panel.target_failed", exc_info=True)
            target = TargetWeight(name=None)
        self._pending = target
        if not target.name:
            self._show_view(None, target)
            return
        cached = self._cache.get(target)
        if cached is not None:
            self._names_loaded(target, cached)
            return

        self._set_status(_("Reading the classes of '{name}'…").format(name=target.name))
        loader = self._loader
        cache = self._cache
        name = target.name

        if not self._background:
            names = _safe_load(loader, name)
            cache.put(target, names)
            self._names_loaded(target, names)
            return

        def _work() -> None:
            names = _safe_load(loader, name)
            cache.put(target, names)
            self._schedule_ui(self._names_loaded, target, names)

        threading.Thread(target=_work, name="ClassRolesNames", daemon=True).start()

    def _schedule_ui(self, func: Callable[..., None], *args: Any) -> None:
        """Run ``func`` on the Tk thread; dropped if the panel is gone."""
        try:
            self.after(0, func, *args)
        except (TclError, RuntimeError):
            log.debug("class_roles_panel.schedule_ui.after_failed")

    def _names_loaded(self, target: TargetWeight, names: Mapping[int, str]) -> None:
        if target != self._pending or not self.is_alive():
            return
        if not names:
            self._show_view(None, target)
            return
        self._show_view(self.editor.view(names, target), target)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _show_view(self, view: ClassRolesView | None, target: TargetWeight) -> None:
        self._view = view
        self._rows = list(view.rows) if view is not None else []
        if self._weight_label is not None:
            self._weight_label.config(
                text=_("Weight: {name}").format(name=target.name)
                if target.name
                else _("No weight selected.")
            )
        if self._source_label is not None:
            if view is not None and view.role_map is not None:
                self._source_label.config(
                    text=_("Roles in use: {source}.").format(
                        source=source_labels()[view.role_map.source]
                    )
                )
            else:
                self._source_label.config(text="")
        self._render_rows()
        self._show_warning(self._warning_text(view, target))
        editable = view is not None and bool(view.rows)
        for widget in (self._save_button, self._restore_button):
            if widget is not None:
                widget.config(state="normal" if editable else "disabled")
        if self._role_combo is not None:
            self._role_combo.config(state="readonly" if editable else "disabled")
        self._set_status("")

    @staticmethod
    def _warning_text(view: ClassRolesView | None, target: TargetWeight) -> str:
        if not target.name:
            return ""
        if view is None:
            return _(
                "Could not read the classes of '{name}': the file is missing or is not a "
                "YOLO model."
            ).format(name=target.name)
        lines: list[str] = []
        if view.stale_project_roles:
            lines.append(
                _(
                    "This project's class roles were set for a different weight file (the "
                    "weight changed or was retrained). They are ignored and will be "
                    "discarded when you save; the roles below are the automatic ones."
                )
            )
        if view.unresolved:
            lines.append(
                _(
                    "No class of this weight is recognised as the animal to track. "
                    "Recording and analysis refuse it until you choose the subject class "
                    "and save."
                )
            )
        return "\n".join(lines)

    def _show_warning(self, text: str) -> None:
        if self._warning is None:
            return
        self._warning.config(text=text)
        if text and not self._warning.winfo_manager() and self._source_label is not None:
            self._warning.pack(anchor="w", fill="x", pady=(0, 4), after=self._source_label)
        elif not text:
            self._warning.pack_forget()

    def _render_rows(self) -> None:
        if self._tree is None:
            return
        self._tree.delete(*self._tree.get_children())
        labels = role_labels()
        for row in self._rows:
            self._tree.insert(
                "", "end", iid=str(row.class_id), values=(row.class_id, row.name, labels[row.role])
            )

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def rows(self) -> list[RoleRow]:
        """The rows as currently edited."""
        return list(self._rows)

    def set_role(self, class_ids: Iterable[int], role: ClassRole) -> None:
        """Give ``role`` to the listed classes (the selection, from the UI)."""
        wanted = set(class_ids)
        self._rows = [
            RoleRow(row.class_id, row.name, role) if row.class_id in wanted else row
            for row in self._rows
        ]
        self._render_rows()
        if self._tree is not None:
            present = [str(cid) for cid in sorted(wanted) if self._tree.exists(str(cid))]
            if present:
                self._tree.selection_set(present)

    def _selected_ids(self) -> list[int]:
        if self._tree is None:
            return []
        return [int(iid) for iid in self._tree.selection()]

    def _on_select(self, _event: Any = None) -> None:
        selected = set(self._selected_ids())
        roles = {row.role for row in self._rows if row.class_id in selected}
        self.role_choice.set(role_labels()[roles.pop()] if len(roles) == 1 else "")

    def _on_role_chosen(self, _event: Any = None) -> None:
        role = role_from_label(self.role_choice.get())
        selected = self._selected_ids()
        if role is None or not selected:
            self._set_status(_("Select one or more classes first."), error=True)
            return
        self.set_role(selected, role)
        self._set_status("")

    # ------------------------------------------------------------------
    # Draft (wizard)
    # ------------------------------------------------------------------
    def draft_mapping(self) -> dict[str, str] | None:
        """The edited map, or ``None`` when the rows equal the automatic ones.

        Raises:
            RoleMapError: the edited rows are not a valid map.
        """
        if self._view is None or tuple(self._rows) == self._view.rows:
            return None
        return build_role_mapping(self._rows)

    def draft_weight_sha256(self) -> str | None:
        """sha256 of the weight the draft was made for (``None`` if unknown)."""
        if self._view is None or not self._view.target.sha256:
            return None
        return self._view.target.sha256

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> bool:
        """Validate and store the rows in the editor's scope."""
        try:
            view = self.editor.save(self._rows)
        except RoleMapError as exc:
            self._set_status(role_map_error_message(exc), error=True)
            return False
        except ClassRolesSaveError:
            self._set_status(_("The class roles could not be saved; nothing changed."), error=True)
            return False
        self._show_view(view, view.target)
        self._set_status(_("Class roles saved."))
        return True

    def restore_automatic(self) -> bool:
        """Drop the explicit map (persisting panel) or the draft edits (wizard)."""
        if not self._persist:
            if self._view is not None:
                self._rows = list(self._view.rows)
                self._render_rows()
            self._set_status(_("Automatic roles restored."))
            return True
        try:
            view = self.editor.restore_automatic()
        except ClassRolesSaveError:
            self._set_status(_("The class roles could not be saved; nothing changed."), error=True)
            return False
        self._show_view(view, view.target)
        self._set_status(_("Automatic roles restored."))
        return True

    def _set_status(self, message: str, *, error: bool = False) -> None:
        if self._status is not None:
            self._status.config(text=message, foreground="#b00020" if error else "#2e7d32")


class ClassRolesDialog(Toplevel):
    """Weight-scope editor opened from the global model configuration."""

    def __init__(
        self,
        parent: Any,
        *,
        weight_name: str,
        weight_manager: Any,
        model_service: Any,
        settings_obj: Any = None,
        event_bus: Any = None,
        background: bool = True,
    ) -> None:
        super().__init__(parent)
        self.title(_("Class roles — {name}").format(name=weight_name))
        self.transient(parent)
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=_(
                "Say what each class of this weight is. Saved with the weight, so every "
                "project that uses it gets these roles unless the project sets its own."
            ),
            wraplength=460,
            justify="left",
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 6))
        self.editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT,
            weight_manager=weight_manager,
            settings_obj=settings_obj,
            event_bus=event_bus,
            weight_name=weight_name,
        )
        self.panel = ClassRolesPanel(
            frame,
            editor=self.editor,
            names_loader=model_service_names_loader(model_service),
            wraplength=460,
            background=background,
        )
        self.panel.pack(fill="both", expand=True)
        ttk.Button(frame, text=_("Close"), command=self.destroy).pack(anchor="e", pady=(8, 0))
