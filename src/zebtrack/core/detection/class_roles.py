"""What each class of a detection weight IS, resolved by class NAME (ADR-009).

Why this module exists
----------------------
Until v8 the detector knew two roles, arena and animal, resolved by the alias
lists in :mod:`zebtrack.core.detection.class_aliases`. That is enough for a
zebrafish weight ``{0: aqua, 1: zebrafish}``, but not for a weight such as the
Barnes maze one, ``{0: arena, 1: experimenter, 2: rat, 3: start_box}``, where
the user needs to say that the experimenter and the start box are CONTEXT —
objects worth observing (to start a session when the experimenter leaves, to
end it when the rat enters the box) but never the tracked subject.

A :class:`ClassRoleMap` stores the role of every class by its NORMALISED NAME,
never by id. Ids are resolved against ``model.names`` when the map is built, so
a retrain that inserts a class (and shifts every id after it) keeps every role.

One resolver, :func:`resolve_class_role_map`, decides with this precedence:

1. the project override (``model_overrides.class_roles``), trusted only while
   its recorded weight sha256 matches the weight actually loaded;
2. the ``class_roles`` stored on the weight's ``weights_config.json`` entry;
3. the aliases — animal → subject, arena → arena, everything else → ignored.
   Aliases NEVER produce ``context``, so a zebrafish weight pays nothing;
4. positional ``(0, 1)`` when the model exposes no names at all.

Levels 3 and 4 reproduce ``class_aliases.resolve_class_ids`` EXACTLY (ADR-013
invariant 1): same arena id, ONE subject id (the lowest), ``arena = -1`` for a
single-class animal weight at id 0, and the positional guess for an
unrecognised two-class weight. The one deliberate change is that a weight with
names, three or more classes and no recognisable subject now raises
:class:`ClassRolesUnresolvedError` instead of tracking class 1 by position —
on a COCO-like weight that guess tracks a bicycle and every report still looks
complete.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator
from pydantic import ValidationError as PydanticValidationError

from zebtrack.core.detection.class_aliases import (
    ClassAliases,
    normalize_class_name,
)
from zebtrack.core.exceptions import DetectorError
from zebtrack.i18n import _

log = structlog.get_logger()

__all__ = [
    "MIN_CLASSES_FOR_STRICT_SUBJECT",
    "ClassRole",
    "ClassRoleMap",
    "ClassRoleSource",
    "ClassRolesUnresolvedError",
    "parse_class_roles",
    "resolve_class_role_map",
]

#: A weight with names and at least this many classes MUST have a subject the
#: resolver can name. Below it, the 7.2 positional guess (animal = 1) is kept:
#: a two-class weight with unrecognised names is far more likely a renamed
#: arena/animal pair than an unrelated model.
MIN_CLASSES_FOR_STRICT_SUBJECT = 3

_LEGACY_ARENA_ID = 0
_LEGACY_SUBJECT_ID = 1
_NO_ARENA = -1


class ClassRole(StrEnum):
    """Role of a class. The values are persistence tokens — never translate them."""

    SUBJECT = "subject"
    ARENA = "arena"
    CONTEXT = "context"
    IGNORED = "ignored"


class ClassRoleSource(StrEnum):
    """Where a :class:`ClassRoleMap` came from (persisted in logs and sidecars)."""

    PROJECT = "project"
    WEIGHT = "weight"
    ALIASES = "aliases"
    LEGACY_POSITIONAL = "legacy_positional"


#: Sources that mean "nobody said what the classes are": the detectors keep the
#: 7.2 heuristics (``apply_class_mismatch_fallback``) only for these.
_LEGACY_SOURCES = frozenset({ClassRoleSource.ALIASES, ClassRoleSource.LEGACY_POSITIONAL})


class ClassRolesUnresolvedError(DetectorError):
    """The weight has class names but none of them can be the tracked subject.

    Typed so that callers branch on the exception TYPE, never on its text (the
    text is translated). The message is user-facing and built at raise time.

    Attributes:
        class_names: The model's ``{id: name}`` map that could not be resolved.
    """

    def __init__(self, class_names: Mapping[int, str]) -> None:
        self.class_names = dict(class_names)
        listed = ", ".join(f"{cid}: {name}" for cid, name in sorted(self.class_names.items()))
        super().__init__(
            _(
                "None of the model classes ({classes}) is recognised as the animal to "
                "track. Assign the 'subject' role to a class in the model configuration, "
                "or add its name to model_selection.class_aliases.animal."
            ).format(classes=listed),
            details={"class_names": self.class_names},
        )


class ClassRoleMap(BaseModel):
    """Roles of a model's classes, keyed by normalised class name.

    Attributes:
        names: ``{class_id: name}`` exactly as read from the model.
        roles_by_name: ``{normalised name: role}`` for every model class.
        source: Which precedence level produced the map.
        weight_sha256: sha256 of the weight file the map was resolved for.
        positional_arena_id: Arena id used when no class NAME carries the arena
            role (legacy alias/positional paths only; ``None`` → no arena).
        positional_subject_id: Subject id used when no class NAME carries the
            subject role (legacy paths only).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    names: dict[int, str]
    roles_by_name: dict[str, ClassRole]
    source: ClassRoleSource
    weight_sha256: str | None = None
    positional_arena_id: int | None = None
    positional_subject_id: int | None = None

    _subject_ids: frozenset[int] = PrivateAttr(default_factory=frozenset)
    _context_ids: frozenset[int] = PrivateAttr(default_factory=frozenset)
    _arena_id: int = PrivateAttr(default=_NO_ARENA)

    @model_validator(mode="after")
    def _derive_and_validate(self) -> ClassRoleMap:
        by_role: dict[ClassRole, list[int]] = {role: [] for role in ClassRole}
        for class_id in sorted(self.names):
            by_role[self.role_of_name(self.names[class_id])].append(class_id)

        subjects = by_role[ClassRole.SUBJECT]
        if not subjects and self.positional_subject_id is not None:
            subjects = [self.positional_subject_id]
        if not subjects:
            raise ValueError("a class-role map needs at least one subject class")
        if self.source in _LEGACY_SOURCES:
            # 7.2 tracked exactly ONE class: the lowest animal id.
            subjects = [min(subjects)]

        arenas = by_role[ClassRole.ARENA]
        arena_names = {normalize_class_name(self.names[cid]) for cid in arenas}
        if len(arena_names) > 1:
            raise ValueError(f"a class-role map allows at most one arena class, got {arena_names}")
        if arenas:
            arena_id = arenas[0]
        elif self.positional_arena_id is not None:
            arena_id = self.positional_arena_id
        else:
            arena_id = _NO_ARENA

        self._subject_ids = frozenset(subjects)
        self._context_ids = frozenset(by_role[ClassRole.CONTEXT])
        self._arena_id = arena_id
        return self

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    @property
    def subject_ids(self) -> frozenset[int]:
        """Class ids tracked as the subject (one track-id axis for all of them)."""
        return self._subject_ids

    @property
    def arena_id(self) -> int:
        """Class id of the arena, ``-1`` when the weight has none."""
        return self._arena_id

    @property
    def context_ids(self) -> frozenset[int]:
        """Class ids observed as context (never tracked as the subject)."""
        return self._context_ids

    @property
    def has_context(self) -> bool:
        """Whether any class is a context class (activates the context crop)."""
        return bool(self._context_ids)

    @property
    def is_explicit(self) -> bool:
        """Whether somebody SAID what the classes are (project or weight)."""
        return self.source not in _LEGACY_SOURCES

    def to_legacy_tuple(self) -> tuple[int, int]:
        """``(arena_id, lowest subject id)`` — the shape 7.2 callers expect."""
        return self._arena_id, min(self._subject_ids)

    def role_of_name(self, name: Any) -> ClassRole:
        """Role of a class name (``ignored`` when the map does not list it)."""
        return self.roles_by_name.get(normalize_class_name(name), ClassRole.IGNORED)

    def role_of_id(self, class_id: int) -> ClassRole:
        """Role of a class id, honouring the positional legacy ids."""
        if class_id in self._subject_ids:
            return ClassRole.SUBJECT
        if class_id == self._arena_id:
            return ClassRole.ARENA
        if class_id in self._context_ids:
            return ClassRole.CONTEXT
        return ClassRole.IGNORED

    def class_name_of(self, class_id: int) -> str:
        """Model name of a class id (its number as text when unnamed)."""
        return self.names.get(class_id, str(class_id))

    def roles_as_dict(self) -> dict[str, str]:
        """Plain ``{name: role token}`` — JSON- and pickle-safe."""
        return {name: role.value for name, role in self.roles_by_name.items()}


def _as_class_map(class_names: Any) -> dict[int, str]:
    """Coerce a model's ``names`` into ``{int id: str name}`` (empty when unusable)."""
    if isinstance(class_names, list | tuple):
        class_names = dict(enumerate(class_names))
    if not isinstance(class_names, Mapping):
        return {}
    result: dict[int, str] = {}
    for key, value in class_names.items():
        try:
            class_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, str):
            result[class_id] = value
    return result


def parse_class_roles(raw: Any) -> dict[str, ClassRole] | None:
    """Validate a persisted ``{name: role}`` mapping.

    Returns ``None`` for anything that is not a non-empty mapping of names to
    the four role tokens, so a hand-edited or corrupted entry degrades to the
    next precedence level instead of raising in the middle of a recording.
    """
    if not isinstance(raw, Mapping) or not raw:
        return None
    parsed: dict[str, ClassRole] = {}
    for name, role in raw.items():
        normalized = normalize_class_name(name)
        if not normalized:
            return None
        try:
            parsed[normalized] = ClassRole(str(role))
        except ValueError:
            return None
    return parsed


def _explicit_map(
    class_map: dict[int, str],
    raw_roles: Any,
    *,
    source: ClassRoleSource,
    weight_sha256: str | None,
) -> ClassRoleMap | None:
    """Build a map from an explicit ``{name: role}``; ``None`` when unusable."""
    parsed = parse_class_roles(raw_roles)
    if parsed is None:
        log.warning("class_roles.explicit.invalid", source=source.value, roles=raw_roles)
        return None
    roles: dict[str, ClassRole] = {}
    for name in class_map.values():
        normalized = normalize_class_name(name)
        roles[normalized] = parsed.get(normalized, ClassRole.IGNORED)
    try:
        return ClassRoleMap(
            names=class_map,
            roles_by_name=roles,
            source=source,
            weight_sha256=weight_sha256,
        )
    except PydanticValidationError as exc:
        log.warning(
            "class_roles.explicit.rejected",
            source=source.value,
            roles=raw_roles,
            class_names=class_map,
            error=str(exc),
        )
        return None


def _alias_map(
    class_map: dict[int, str],
    vocab: ClassAliases,
    *,
    weight_sha256: str | None,
    strict: bool,
) -> ClassRoleMap:
    """Rules 2-4 of ``class_aliases.resolve_class_ids``, expressed as roles."""
    arena_ids: list[int] = []
    animal_ids: list[int] = []
    for class_id in sorted(class_map):
        role = vocab.role_of(class_map[class_id])
        if role == "arena":
            arena_ids.append(class_id)
        elif role == "animal":
            animal_ids.append(class_id)

    if not animal_ids and strict and len(class_map) >= MIN_CLASSES_FOR_STRICT_SUBJECT:
        raise ClassRolesUnresolvedError(class_map)

    roles = {normalize_class_name(name): ClassRole.IGNORED for name in class_map.values()}
    if arena_ids:
        roles[normalize_class_name(class_map[arena_ids[0]])] = ClassRole.ARENA
    if animal_ids:
        roles[normalize_class_name(class_map[animal_ids[0]])] = ClassRole.SUBJECT

    positional_arena: int | None = None
    if not arena_ids and not (animal_ids and animal_ids[0] == 0):
        positional_arena = _LEGACY_ARENA_ID
    positional_subject = None if animal_ids else _LEGACY_SUBJECT_ID

    if not animal_ids:
        log.warning(
            "class_roles.aliases.no_subject",
            class_names=class_map,
            fallback_subject_id=positional_subject,
            message=(
                "No class name is recognised as the animal; tracking class id "
                f"{positional_subject} by position."
            ),
        )

    return ClassRoleMap(
        names=class_map,
        roles_by_name=roles,
        source=ClassRoleSource.ALIASES,
        weight_sha256=weight_sha256,
        positional_arena_id=positional_arena,
        positional_subject_id=positional_subject,
    )


def resolve_class_role_map(
    names: Any,
    *,
    project_override: Any = None,
    project_override_sha: str | None = None,
    weight_entry: Mapping[str, Any] | None = None,
    weight_sha256: str | None = None,
    aliases: ClassAliases | None = None,
    strict: bool = True,
) -> ClassRoleMap:
    """Resolve the role of every class of a model (precedence in the module doc).

    Args:
        names: The model's ``names`` (mapping or sequence).
        project_override: ``model_overrides.class_roles`` of the project.
        project_override_sha: ``model_overrides.class_roles_weight_sha256``.
        weight_entry: The weight's ``weights_config.json`` entry.
        weight_sha256: sha256 of the weight actually loaded.
        aliases: Role vocabularies; built-in ones when ``None``.
        strict: When ``False`` an unresolvable multi-class weight degrades to
            the 7.2 positional guess instead of raising (the detectors' own
            legacy path, which must stay byte-identical).

    Returns:
        The resolved :class:`ClassRoleMap`.

    Raises:
        ClassRolesUnresolvedError: ``strict`` and the weight has names,
            ``MIN_CLASSES_FOR_STRICT_SUBJECT`` or more classes and no subject.
    """
    class_map = _as_class_map(names)
    if not class_map:
        return ClassRoleMap(
            names={},
            roles_by_name={},
            source=ClassRoleSource.LEGACY_POSITIONAL,
            weight_sha256=weight_sha256,
            positional_arena_id=_LEGACY_ARENA_ID,
            positional_subject_id=_LEGACY_SUBJECT_ID,
        )

    if project_override:
        if project_override_sha and weight_sha256 and project_override_sha == weight_sha256:
            resolved = _explicit_map(
                class_map,
                project_override,
                source=ClassRoleSource.PROJECT,
                weight_sha256=weight_sha256,
            )
            if resolved is not None:
                return _logged(resolved)
        else:
            log.warning(
                "class_roles.project_override.sha_mismatch",
                project_sha=project_override_sha,
                weight_sha=weight_sha256,
                message=(
                    "The project's class roles were set for another weight; "
                    "ignoring them and resolving from the weight instead."
                ),
            )

    weight_roles = weight_entry.get("class_roles") if isinstance(weight_entry, Mapping) else None
    if weight_roles:
        resolved = _explicit_map(
            class_map,
            weight_roles,
            source=ClassRoleSource.WEIGHT,
            weight_sha256=weight_sha256,
        )
        if resolved is not None:
            return _logged(resolved)

    vocab = aliases or ClassAliases.defaults()
    return _logged(_alias_map(class_map, vocab, weight_sha256=weight_sha256, strict=strict))


def _logged(role_map: ClassRoleMap) -> ClassRoleMap:
    log.info(
        "class_roles.resolved",
        source=role_map.source.value,
        subject_ids=sorted(role_map.subject_ids),
        arena_id=role_map.arena_id,
        context_ids=sorted(role_map.context_ids),
        class_names=role_map.names,
    )
    return role_map
