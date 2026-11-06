"""Single rule for "does this project track ONE animal per aquarium?" (issue #649).

The answer switches ByteTrack's single-animal mode (ID 1 forced, resurrection
instead of a new id). It used to be re-derived in four places with four
different orders: the processing coordinators, ``DetectorService``, the live
mode label and the load-time migration. In two of them the
``tracking.use_single_subject_tracker`` flag beat the animal count, and the
migration wrote that flag from ``settings.tracking.use_single_subject_tracker``
(``False`` by default) whenever a project had no ``tracking`` stanza. A
one-rat Barnes project therefore ran the multi-subject tracker, which opened
spurious ids, and the report counted three animals.

The animal COUNT is what the researcher declared (wizard, template, dialogs);
every UI derives the flag from it. So the count wins over the stored flag, and
the flag only decides when no count exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = [
    "SingleSubjectDecision",
    "count_means_single",
    "resolve_project_single_subject",
]


@dataclass(frozen=True)
class SingleSubjectDecision:
    """Outcome of :func:`resolve_project_single_subject`.

    Attributes:
        single: ``True`` for one animal per aquarium.
        source: Dotted key of ``project_data`` that decided it.
        value: Raw value read at ``source``.
    """

    single: bool
    source: str
    value: Any


def count_means_single(value: object) -> bool | None:
    """``True`` for a count of at most one animal, ``None`` when unreadable.

    Args:
        value: An ``animals_per_aquarium`` value (int, numeric string, ...).
    """
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(str(value)) <= 1
    except (TypeError, ValueError):
        return None


def _list_means_single(values: object) -> bool | None:
    """Per-aquarium counts (``[1, 1, 2]``): single only if every entry is <= 1."""
    if not isinstance(values, list) or not values:
        return None
    try:
        return max(int(v) for v in values) <= 1
    except (TypeError, ValueError):
        return None


def _section(project_data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = project_data.get(key)
    return value if isinstance(value, Mapping) else {}


def resolve_project_single_subject(
    project_data: Mapping[str, Any] | None,
) -> SingleSubjectDecision | None:
    """Decide single-animal tracking from a project's data.

    Precedence:

    1. Legacy explicit top-level flags ``use_single_subject_tracker`` and
       ``single_animal_per_aquarium``.
    2. The animal count: top-level ``animals_per_aquarium``, then
       ``calibration.animals_per_aquarium``, ``calibration.animals_per_aquarium_list``,
       ``_wizard_metadata.animals_per_aquarium_list`` and
       ``video_processing.animals_per_aquarium``.
    3. ``tracking.use_single_subject_tracker``: only without any count, because
       a load-time migration used to write it from the global settings.

    Args:
        project_data: The project's data, or ``None``.

    Returns:
        The decision with the key that made it, or ``None`` when nothing in the
        project says; the caller then keeps its own default.
    """
    if not project_data:
        return None

    for key in ("use_single_subject_tracker", "single_animal_per_aquarium"):
        flag = project_data.get(key)
        if flag is not None:
            return SingleSubjectDecision(bool(flag), key, flag)

    calibration = _section(project_data, "calibration")
    counts: tuple[tuple[str, Any, Any], ...] = (
        ("animals_per_aquarium", project_data.get("animals_per_aquarium"), count_means_single),
        (
            "calibration.animals_per_aquarium",
            calibration.get("animals_per_aquarium"),
            count_means_single,
        ),
        (
            "calibration.animals_per_aquarium_list",
            calibration.get("animals_per_aquarium_list"),
            _list_means_single,
        ),
        (
            "_wizard_metadata.animals_per_aquarium_list",
            _section(project_data, "_wizard_metadata").get("animals_per_aquarium_list"),
            _list_means_single,
        ),
        (
            "video_processing.animals_per_aquarium",
            _section(project_data, "video_processing").get("animals_per_aquarium"),
            count_means_single,
        ),
    )
    for source, value, reader in counts:
        single = reader(value)
        if single is not None:
            return SingleSubjectDecision(single, source, value)

    flag = _section(project_data, "tracking").get("use_single_subject_tracker")
    if flag is not None:
        return SingleSubjectDecision(bool(flag), "tracking.use_single_subject_tracker", flag)

    return None
