"""Species-agnostic resolution of a model's class ids by class NAME.

Why this module exists
----------------------
DRerio LogAI needs two roles from every detection weight: the **arena** (the
container the animal moves in — historically the aquarium) and the **animal**
(historically the zebrafish). The class ids behind those roles were resolved
from two hard-coded name lists, duplicated in ``DetectionPostProcessor`` and
``DetectorService``. A weight whose names were not on those lists fell back to
``arena = 0, animal = 1`` without complaint.

That fallback is a silent failure for any non-zebrafish weight. Roboflow
exports class names in alphabetical order, so a rodent weight trained with
``arena``, ``experimenter`` and ``rat`` arrives as
``{0: "arena", 1: "experimenter", 2: "rat"}``: the fallback would track the
EXPERIMENTER as the animal, and every report would come out complete and wrong.

This module is the single place that knows which names mean which role. The
built-in aliases cover the zebrafish weights shipped so far (unchanged
behaviour) plus rodents and generic names; ``model_selection.class_aliases`` in
the settings ADDS project-specific names on top of them — it never removes the
built-in ones, so a config can only widen recognition.

Classes that match neither role (``experimenter``, ``start_box``…) are left
alone here: the detectors already keep only the animal class, so extra classes
are ignored by the tracking pipeline rather than misread as the animal.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = [
    "DEFAULT_ANIMAL_ALIASES",
    "DEFAULT_ARENA_ALIASES",
    "ClassAliases",
    "ResolvedClassIds",
    "normalize_class_name",
    "resolve_arena_class_id",
    "resolve_class_ids",
]

#: Names that mean "the container the animal moves in". The first four are the
#: names the zebrafish weights have always used and MUST stay recognised.
DEFAULT_ARENA_ALIASES: tuple[str, ...] = (
    "aqua",
    "aquarium",
    "tank",
    "agua",
    "arena",
    "maze",
    "labirinto",
    "open_field",
    "openfield",
    "apparatus",
)

#: Names that mean "the tracked subject". The first three are the zebrafish
#: names and MUST stay recognised; the rest cover rodents and generic labels.
DEFAULT_ANIMAL_ALIASES: tuple[str, ...] = (
    "zebrafish",
    "fish",
    "peixe",
    "rat",
    "rato",
    "mouse",
    "camundongo",
    "rodent",
    "roedor",
    "animal",
    "subject",
)

#: Legacy ids used when a model exposes no class names at all. Kept verbatim so
#: weights without metadata behave exactly as before.
_LEGACY_ARENA_ID = 0
_LEGACY_ANIMAL_ID = 1

_SEPARATORS = re.compile(r"[\s\-]+")


def normalize_class_name(name: Any) -> str:
    """Canonical form used for every alias comparison.

    Case-insensitive, surrounding whitespace ignored, and spaces/hyphens folded
    into underscores, so ``"Open Field"``, ``"open-field"`` and ``"open_field"``
    are the same name.

    Args:
        name: A class name as stored in the model (any type; non-strings are
            converted with ``str``).

    Returns:
        The normalised name.
    """
    return _SEPARATORS.sub("_", str(name).strip().lower())


def _normalize_all(names: Iterable[Any]) -> tuple[str, ...]:
    """Normalise and de-duplicate a sequence of names, preserving order."""
    seen: dict[str, None] = {}
    for name in names:
        normalized = normalize_class_name(name)
        if normalized:
            seen.setdefault(normalized, None)
    return tuple(seen)


@dataclass(frozen=True)
class ClassAliases:
    """The two role vocabularies, already normalised.

    Attributes:
        arena: Names recognised as the arena/container class.
        animal: Names recognised as the tracked-animal class.
    """

    arena: tuple[str, ...] = DEFAULT_ARENA_ALIASES
    animal: tuple[str, ...] = DEFAULT_ANIMAL_ALIASES

    def __post_init__(self) -> None:
        # frozen=True: normalise through object.__setattr__.
        object.__setattr__(self, "arena", _normalize_all(self.arena))
        object.__setattr__(self, "animal", _normalize_all(self.animal))
        overlap = set(self.arena) & set(self.animal)
        if overlap:
            raise ValueError(f"class alias(es) {sorted(overlap)} declared as both arena and animal")

    @classmethod
    def defaults(cls) -> ClassAliases:
        """Built-in vocabularies only."""
        return cls()

    @classmethod
    def with_extra(
        cls,
        arena_extra: Iterable[str] = (),
        animal_extra: Iterable[str] = (),
    ) -> ClassAliases:
        """Built-in vocabularies widened with project-specific names.

        Args:
            arena_extra: Additional names for the arena role.
            animal_extra: Additional names for the animal role.

        Returns:
            A new ``ClassAliases``; built-in names always come first.

        Raises:
            ValueError: If a name ends up in both roles.
        """
        return cls(
            arena=(*DEFAULT_ARENA_ALIASES, *arena_extra),
            animal=(*DEFAULT_ANIMAL_ALIASES, *animal_extra),
        )

    @classmethod
    def from_settings(cls, settings_obj: Any) -> ClassAliases:
        """Read ``model_selection.class_aliases`` from an injected settings object.

        Tolerates ``None``, partial stubs and ``MagicMock`` settings by
        type-checking every value: a mock answers every attribute, so trusting
        ``getattr`` would feed mocks into the vocabularies. Anything unusable
        degrades to the built-in vocabularies, never to an error — a bad alias
        config must not stop a recording.

        Args:
            settings_obj: The ``Settings`` instance (or ``None``).

        Returns:
            The effective ``ClassAliases``.
        """
        section = getattr(getattr(settings_obj, "model_selection", None), "class_aliases", None)
        arena_extra = _string_list(getattr(section, "arena", None))
        animal_extra = _string_list(getattr(section, "animal", None))
        if not arena_extra and not animal_extra:
            return cls.defaults()
        try:
            return cls.with_extra(arena_extra, animal_extra)
        except ValueError as exc:
            log.warning(
                "class_aliases.settings_rejected",
                error=str(exc),
                arena_extra=arena_extra,
                animal_extra=animal_extra,
                message="Conflicting class aliases in settings; using built-in aliases only.",
            )
            return cls.defaults()

    def role_of(self, name: Any) -> str | None:
        """Return ``"arena"``, ``"animal"`` or ``None`` for a class name."""
        normalized = normalize_class_name(name)
        if normalized in self.arena:
            return "arena"
        if normalized in self.animal:
            return "animal"
        return None


def _string_list(value: Any) -> list[str]:
    """Keep only non-empty strings from a list-like settings value."""
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _as_class_map(class_names: Any) -> dict[int, str]:
    """Coerce a model's ``names`` into ``{int id: str name}``.

    Ultralytics exposes ``dict[int, str]``; OpenVINO metadata may carry string
    keys; tests pass ``MagicMock``. Anything that is not a usable mapping yields
    an empty dict, which callers treat as "no metadata".
    """
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


@dataclass(frozen=True)
class ResolvedClassIds:
    """Outcome of resolving a model's class names into roles.

    Attributes:
        arena_id: Class id of the arena (``-1`` disables arena-by-class).
        animal_id: Class id of the animal.
        found_arena: Whether ``arena_id`` came from a recognised name.
        found_animal: Whether ``animal_id`` came from a recognised name.
        ignored: Names that matched neither role (e.g. ``experimenter``).
    """

    arena_id: int
    animal_id: int
    found_arena: bool
    found_animal: bool
    ignored: tuple[str, ...] = ()

    def as_tuple(self) -> tuple[int, int]:
        """``(arena_id, animal_id)`` — the shape legacy callers expect."""
        return self.arena_id, self.animal_id


def resolve_class_ids(class_names: Any, aliases: ClassAliases | None = None) -> ResolvedClassIds:
    """Map a model's class names onto the arena and animal roles.

    Rules, in order:

    1. No usable names → legacy ``(0, 1)``; nothing to resolve against.
    2. Each role takes the LOWEST class id whose name is in its vocabulary.
       More than one candidate is logged, never guessed silently.
    3. Animal found at id 0 with no arena class → arena ``-1`` (single-class
       animal weight, e.g. ``best_oi.pt``); unchanged legacy behaviour.
    4. Names present but no animal recognised → legacy ids are kept for
       backward compatibility, with a WARNING naming the classes, because
       the tracked object is then a guess.

    Args:
        class_names: The model's ``names`` (mapping or sequence).
        aliases: Role vocabularies; built-in ones when ``None``.

    Returns:
        A ``ResolvedClassIds``.
    """
    vocab = aliases or ClassAliases.defaults()
    class_map = _as_class_map(class_names)
    if not class_map:
        return ResolvedClassIds(_LEGACY_ARENA_ID, _LEGACY_ANIMAL_ID, False, False)

    arena_ids: list[int] = []
    animal_ids: list[int] = []
    ignored: list[str] = []
    for class_id in sorted(class_map):
        role = vocab.role_of(class_map[class_id])
        if role == "arena":
            arena_ids.append(class_id)
        elif role == "animal":
            animal_ids.append(class_id)
        else:
            ignored.append(class_map[class_id])

    found_arena = bool(arena_ids)
    found_animal = bool(animal_ids)
    arena_id = arena_ids[0] if found_arena else _LEGACY_ARENA_ID
    animal_id = animal_ids[0] if found_animal else _LEGACY_ANIMAL_ID

    if found_animal and not found_arena and animal_id == 0:
        arena_id = -1

    for role, ids in (("arena", arena_ids), ("animal", animal_ids)):
        if len(ids) > 1:
            log.warning(
                "class_aliases.multiple_candidates",
                role=role,
                candidates={i: class_map[i] for i in ids},
                chosen=ids[0],
            )

    if not found_animal:
        log.warning(
            "class_aliases.no_animal_class",
            class_names=class_map,
            fallback_animal_id=animal_id,
            message=(
                "No class name is recognised as the animal; tracking class id "
                f"{animal_id} by position. Rename the class or add it to "
                "model_selection.class_aliases.animal."
            ),
        )

    resolved = ResolvedClassIds(arena_id, animal_id, found_arena, found_animal, tuple(ignored))
    log.info(
        "class_aliases.resolved",
        arena_id=resolved.arena_id,
        animal_id=resolved.animal_id,
        ignored=list(resolved.ignored),
        class_names=class_map,
    )
    return resolved


def resolve_arena_class_id(class_names: Any, aliases: ClassAliases | None = None) -> int:
    """Class id to request from an arena model (``predict(classes=[id])``).

    Falls back to ``0`` — the historical hard-coded value — whenever the model
    has no usable names or no arena-like class, so existing arena weights and
    mocked models keep their behaviour.

    Args:
        class_names: The arena model's ``names``.
        aliases: Role vocabularies; built-in ones when ``None``.

    Returns:
        The arena class id (never negative).
    """
    vocab = aliases or ClassAliases.defaults()
    class_map = _as_class_map(class_names)
    for class_id in sorted(class_map):
        if vocab.role_of(class_map[class_id]) == "arena":
            return class_id
    return _LEGACY_ARENA_ID
