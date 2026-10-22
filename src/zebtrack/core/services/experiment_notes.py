"""Single source of the experimental notes of a live project.

The researcher annotates what the numbers cannot show: an animal that jumped
out of the tank, a light that flickered, a session restarted halfway. A note
belongs either to a whole Day x Group BLOCK or to one SUBJECT of that block.

Storage: ``project_data["experiment_notes"]``, keyed exactly like the session
duration overrides -- :func:`duration_override_key` for a subject and
:func:`block_override_key` (subject ``"*"``) for the block. Reusing those
builders means the day is normalized the same way (``1``, ``"1"``, ``"Dia_1"``
and ``"Dia_01"`` are the same day), so a note written from the dialog is found
again by the report, whichever day format each call site carries. **Never**
build a key by hand at a call site.

Value: ``{"text": str, "updated_at": iso8601}``.

Backward compatibility: up to v7.2 the block note was stored as a bare string
under ``"Dia_{n}_{grupo}"``. Those notes are still READ as block notes (with no
timestamp); the next write of the same block moves it to the new key.

Anything unreadable DEGRADES, never raises: a corrupt note is skipped with a
warning. Losing one annotation is bad; a report that fails to generate because
of it is worse.

The module is pure: no I/O, no singleton, no UI. Callers persist the project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog

from zebtrack.core.services.session_duration_resolver import (
    SUBJECT_WILDCARD,
    duration_override_key,
    normalize_day,
)

log = structlog.get_logger()

__all__ = [
    "NOTES_KEY",
    "NOTE_COLUMNS",
    "ExperimentNote",
    "NoteRecord",
    "block_has_notes",
    "block_records",
    "collect_block_notes",
    "get_note",
    "iter_notes",
    "note_rows",
    "set_note",
]

NOTES_KEY: Final[str] = "experiment_notes"

NOTE_COLUMNS: Final[tuple[str, ...]] = ("day", "group", "scope", "subject", "note", "updated_at")

# Pre-v7.3 block key: ``f"Dia_{day_num}_{group_name}"``.
_LEGACY_KEY_RE: Final = re.compile(r"^Dia_0*(\d+)_(.+)$")


@dataclass(frozen=True)
class ExperimentNote:
    """One note. ``updated_at`` is ``None`` only for notes saved before v7.3."""

    text: str
    updated_at: str | None = None


@dataclass(frozen=True)
class NoteRecord:
    """A note located in the design. ``subject is None`` means the block note."""

    day: str
    group: str
    subject: str | None
    note: ExperimentNote


def _legacy_block_key(day: object, group: object) -> str:
    return f"{normalize_day(day)}_{group}"


def _notes_dict(project_data: dict[str, Any] | None) -> dict[str, Any]:
    notes = (project_data or {}).get(NOTES_KEY)
    return notes if isinstance(notes, dict) else {}


def _coerce_note(raw: object, key: str) -> ExperimentNote | None:
    """Turn a stored value into a note, or ``None`` (with a warning) if unusable."""
    if isinstance(raw, str):
        text = raw.strip()
        return ExperimentNote(text=text) if text else None
    if isinstance(raw, dict):
        raw_text = raw.get("text")
        if isinstance(raw_text, str) and raw_text.strip():
            updated_at = raw.get("updated_at")
            return ExperimentNote(
                text=raw_text.strip(),
                updated_at=updated_at if isinstance(updated_at, str) else None,
            )
    log.warning("experiment_notes.invalid", key=key, raw=repr(raw)[:80])
    return None


def get_note(
    project_data: dict[str, Any] | None,
    day: object,
    group: object,
    subject: object = SUBJECT_WILDCARD,
) -> ExperimentNote | None:
    """Note of one subject, or of the block when ``subject`` is ``"*"``."""
    notes = _notes_dict(project_data)
    key = duration_override_key(day, group, subject)
    if key in notes:
        note = _coerce_note(notes[key], key)
        if note is not None:
            return note

    if str(subject).strip() == SUBJECT_WILDCARD:
        legacy_key = _legacy_block_key(day, group)
        if legacy_key in notes:
            return _coerce_note(notes[legacy_key], legacy_key)
    return None


def set_note(
    project_data: dict[str, Any],
    day: object,
    group: object,
    subject: object,
    text: str | None,
    *,
    now: datetime | None = None,
) -> ExperimentNote | None:
    """Write (or remove, when ``text`` is blank) a note in ``project_data``, in place.

    Does NOT save the project: ``save_project()`` can fail and the caller is
    the one who can tell the user. Returns the note written, or ``None`` when
    the note was removed.
    """
    notes = project_data.get(NOTES_KEY)
    if not isinstance(notes, dict):
        notes = {}
        project_data[NOTES_KEY] = notes

    key = duration_override_key(day, group, subject)
    if str(subject).strip() == SUBJECT_WILDCARD:
        # The legacy copy would resurface as soon as the new key is cleared.
        notes.pop(_legacy_block_key(day, group), None)

    cleaned = (text or "").strip()
    if not cleaned:
        notes.pop(key, None)
        log.info("experiment_notes.cleared", key=key)
        return None

    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    notes[key] = {"text": cleaned, "updated_at": stamp}
    log.info("experiment_notes.set", key=key, length=len(cleaned))
    return ExperimentNote(text=cleaned, updated_at=stamp)


def _parse_key(key: str) -> tuple[str, str, str | None] | None:
    """``(day, group, subject|None)`` of a stored key, or ``None`` if unrecognized."""
    if "|" in key:
        day, _sep, rest = key.partition("|")
        group, sep, subject = rest.rpartition("|")
        if not sep or not day or not group or not subject:
            return None
        return day, group, None if subject == SUBJECT_WILDCARD else subject
    match = _LEGACY_KEY_RE.match(key)
    if match:
        return f"Dia_{int(match.group(1))}", match.group(2), None
    return None


def _day_number(day: str) -> int:
    digits = day.removeprefix("Dia_")
    return int(digits) if digits.isdigit() else 0


def _subject_order(subject: str | None) -> tuple[int, int, str]:
    if subject is None:
        return (0, 0, "")
    if subject.isdigit():
        return (1, int(subject), subject)
    return (2, 0, subject)


def iter_notes(project_data: dict[str, Any] | None) -> list[NoteRecord]:
    """Every readable note of the project, ordered by day, group and subject.

    When a block has both a legacy and a new-format note, the new one wins.
    """
    records: dict[tuple[str, str, str | None], NoteRecord] = {}
    legacy: list[NoteRecord] = []
    for key, raw in _notes_dict(project_data).items():
        parsed = _parse_key(str(key))
        if parsed is None:
            log.warning("experiment_notes.unrecognized_key", key=key)
            continue
        note = _coerce_note(raw, str(key))
        if note is None:
            continue
        day, group, subject = parsed
        record = NoteRecord(day=day, group=group, subject=subject, note=note)
        if "|" in str(key):
            records[(day, group, subject)] = record
        else:
            legacy.append(record)

    for record in legacy:
        records.setdefault((record.day, record.group, None), record)

    return sorted(
        records.values(),
        key=lambda r: (_day_number(r.day), r.group, _subject_order(r.subject)),
    )


def block_records(
    project_data: dict[str, Any] | None,
    day: object,
    group: object,
) -> list[NoteRecord]:
    """The notes of one Day x Group block, block note first."""
    target_day = normalize_day(day)
    target_group = str(group).strip()
    return [
        record
        for record in iter_notes(project_data)
        if record.day == target_day and record.group.strip() == target_group
    ]


def note_rows(records: list[NoteRecord]) -> list[dict[str, str]]:
    """Tabular form of notes for the report spreadsheets (columns :data:`NOTE_COLUMNS`).

    Column names and values are data, not copy: they do not follow
    ``ui.language``, so a script reading the workbook keeps working.
    """
    return [
        {
            "day": record.day,
            "group": record.group,
            "scope": "block" if record.subject is None else "subject",
            "subject": record.subject or "",
            "note": record.note.text,
            "updated_at": record.note.updated_at or "",
        }
        for record in records
    ]


def collect_block_notes(
    project_data: dict[str, Any] | None,
    day: object,
    group: object,
) -> tuple[ExperimentNote | None, dict[str, ExperimentNote]]:
    """``(block note, {subject: note})`` of one Day x Group block."""
    block_note: ExperimentNote | None = None
    subject_notes: dict[str, ExperimentNote] = {}
    for record in block_records(project_data, day, group):
        if record.subject is None:
            block_note = record.note
        else:
            subject_notes[record.subject] = record.note
    return block_note, subject_notes


def block_has_notes(project_data: dict[str, Any] | None, day: object, group: object) -> bool:
    """Whether the block, or any subject of it, has a note."""
    block_note, subject_notes = collect_block_notes(project_data, day, group)
    return block_note is not None or bool(subject_notes)
