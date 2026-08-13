"""Display labels that are also compared with ``==`` somewhere else.

These are the strings the UI both *shows* and *tests*: the "all tracks" entry of
the track selector, the placeholders shown when a video has no group/day/subject
recorded, and the tree label that marks the main arena. They live here as
functions rather than as literals scattered across modules because producer and
comparer are usually in different files -- ``common_widgets`` fills the track
selector, ``canvas/video_frame_manager`` tests what came back; ``zone_editor``
writes the arena row, ``menu_manager`` decides which context menu to show from
its text.

Translating one side without the other does not raise: track filtering silently
stops matching, day grouping silently splits, the arena silently offers the
wrong menu. One accessor per value keeps both sides in step.

These are **display values only**. None of them is written to disk. The
persisted tokens are different strings -- ``Sem_Grupo``, ``Dia_Indefinido`` and
``Sujeito_Indefinido``, with underscores, built in
``core/project/output_registration_manager.py`` -- and those must never be
translated (see ``scripts/i18n_allowlist.txt``).

The language cannot change while the application is running, so a value read
twice in one session is always equal to itself.
"""

from __future__ import annotations

from zebtrack.i18n import _


def all_tracks_label() -> str:
    """The track-selector entry meaning "do not filter by animal"."""
    return _("All")


def no_group_label() -> str:
    """Placeholder shown when a video has no experimental group recorded."""
    return _("No Group")


def no_day_label() -> str:
    """Placeholder shown when a video has no experiment day recorded."""
    return _("No Day")


def not_reported_label() -> str:
    """Placeholder shown when a video has no subject recorded."""
    return _("Not reported")


def day_prefix() -> str:
    """Word before a day number in a tree title, as in "Day 03".

    Only for display. The stored form is the ``Dia_N`` directory token built by
    ``core/project/output_registration_manager.py``, which never changes.
    """
    return _("Day")


def main_arena_label() -> str:
    """Zone-list label for the main arena, without its leading icon.

    ``is_main_arena_row()`` is the supported way to test a row against it.
    """
    return _("Main Arena")


def main_arena_row_label() -> str:
    """Zone-list label for the main arena, with its icon, as displayed."""
    return f"🏟 {main_arena_label()}"


def both_models_label() -> str:
    """The "test every engine" entry of the diagnostics model chooser.

    ``model_diagnostics_panel`` offers it alongside the two engine names, which
    are proper nouns and stay as they are; ``model_diagnostics_coordinator``
    then branches on the value it gets back. Translating only the combobox would
    silently reduce "test both" to "test neither".
    """
    return _("Both")


def is_main_arena_row(label: object) -> bool:
    """True when *label* is the zone-list row for the main arena.

    Accepts anything so call sites can pass a raw Treeview value without
    checking its type first.
    """
    return main_arena_label() in str(label)
