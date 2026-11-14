"""Colour and label of a detection box by class ROLE (ADR-009).

Until v8 both overlays decided the colour by class NUMBER: ``class_id == 0`` was
painted as the aquarium and everything else as the animal. That is right for a
zebrafish weight ``{0: aquarium, 1: zebrafish}`` and wrong for any other: on a
rodent weight ``{0: rat, 1: arena}`` the rat was drawn as the arena, and the
Barnes weight's experimenter and start box were drawn as animals.

When the project's weight has an EXPLICIT role map (set in the project or on the
weight), the boxes are coloured and labelled by role. Without one — every
zebrafish project, every weight nobody configured — the 7.2 colours and labels
are returned unchanged, byte for byte: the alias resolution of a zebrafish
weight is not consulted here on purpose, so nothing about those overlays moves.

The role tokens (``subject``, ``arena``, ``context``, ``ignored``) are persistence
contracts and are never translated; only the labels drawn next to the boxes are.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from zebtrack.i18n import _

__all__ = [
    "CANVAS_ROLE_COLORS",
    "FRAME_ROLE_COLORS",
    "frame_style",
    "role_of_class",
    "zone_canvas_style",
]

#: Zone-canvas (Tk) colour per role. ``subject`` is absent on purpose: the
#: subject keeps the 7.2 colour, which depends on the single-subject mode.
CANVAS_ROLE_COLORS: dict[str, str] = {
    "arena": "yellow",
    "context": "orange",
    "ignored": "gray",
}

#: Analysis-frame (OpenCV, BGR) colour per role.
FRAME_ROLE_COLORS: dict[str, tuple[int, int, int]] = {
    "subject": (255, 0, 255),
    "arena": (0, 255, 255),
    "context": (0, 165, 255),
    "ignored": (160, 160, 160),
}

_LEGACY_ARENA_CLASS_ID = 0
_LEGACY_FRAME_ARENA = (0, 255, 255)
_LEGACY_FRAME_OTHER = (255, 0, 255)


def role_of_class(class_id: Any, class_roles: Mapping[int, str] | None) -> str | None:
    """Role token of a detection's class, or ``None`` for the legacy colours.

    ``None`` whenever there is no explicit map (anything that is not a non-empty
    mapping counts as none, so a stubbed GUI attribute can never recolour the
    overlay). A class the map does not list is ``ignored`` — the same rule
    :class:`ClassRoleMap` applies to a class absent from an explicit map.
    """
    if not isinstance(class_roles, Mapping) or not class_roles:
        return None
    try:
        key = int(class_id)
    except (TypeError, ValueError):
        return "ignored"
    return str(class_roles.get(key, "ignored"))


def _class_label(class_id: Any, class_names: Mapping[int, str] | None, fallback: str) -> str:
    if isinstance(class_names, Mapping):
        try:
            name = class_names.get(int(class_id))
        except (TypeError, ValueError):
            name = None
        if name:
            return str(name)
    return fallback


def _subject_label(track_id: Any, *, is_single_subject: bool) -> str:
    if is_single_subject:
        return _("Target")
    return f"ID: {track_id}" if track_id is not None else "Det"


def zone_canvas_style(
    class_id: Any,
    track_id: Any,
    *,
    is_single_subject: bool,
    class_roles: Mapping[int, str] | None = None,
    class_names: Mapping[int, str] | None = None,
) -> tuple[str, str]:
    """``(Tk colour, label)`` of a box on the zone canvas.

    Args:
        class_id: Model class id of the detection.
        track_id: Tracker id (``None`` for an untracked detection).
        is_single_subject: Single-subject tracking mode (magenta "Target" box).
        class_roles: ``{class id: role token}`` of an explicit map, or ``None``.
        class_names: ``{class id: name}`` used to label context/ignored boxes.
    """
    subject_color = "magenta" if is_single_subject else "cyan"
    role = role_of_class(class_id, class_roles)
    if role is None:
        color = "yellow" if class_id == _LEGACY_ARENA_CLASS_ID else subject_color
        return color, _subject_label(track_id, is_single_subject=is_single_subject)
    if role == "subject":
        return subject_color, _subject_label(track_id, is_single_subject=is_single_subject)
    if role == "arena":
        return CANVAS_ROLE_COLORS["arena"], _("Arena")
    if role == "context":
        return CANVAS_ROLE_COLORS["context"], _class_label(class_id, class_names, _("Context"))
    return CANVAS_ROLE_COLORS["ignored"], _class_label(class_id, class_names, _("Ignored"))


def frame_style(
    class_id: Any,
    track_id: Any,
    *,
    class_roles: Mapping[int, str] | None = None,
    class_names: Mapping[int, str] | None = None,
) -> tuple[tuple[int, int, int], str]:
    """``(BGR colour, label)`` of a box drawn on the analysis frame.

    The confidence suffix is appended by the caller; it does not depend on role.
    """
    role = role_of_class(class_id, class_roles)
    tracked_label = f"ID {track_id}" if track_id is not None else _("Object")
    if role is None:
        color = _LEGACY_FRAME_ARENA if class_id == _LEGACY_ARENA_CLASS_ID else _LEGACY_FRAME_OTHER
        return color, tracked_label
    if role == "subject":
        return FRAME_ROLE_COLORS["subject"], tracked_label
    if role == "arena":
        return FRAME_ROLE_COLORS["arena"], _("Arena")
    if role == "context":
        return FRAME_ROLE_COLORS["context"], _class_label(class_id, class_names, _("Context"))
    return FRAME_ROLE_COLORS["ignored"], _class_label(class_id, class_names, _("Ignored"))
