"""Tests for the experimental notes of a live project (block and subject)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from zebtrack.core.services.experiment_notes import (
    NOTES_KEY,
    ExperimentNote,
    block_has_notes,
    collect_block_notes,
    get_note,
    iter_notes,
    set_note,
)
from zebtrack.core.services.session_duration_resolver import SUBJECT_WILDCARD

FIXED_NOW = datetime(2026, 10, 22, 14, 30, 5)


def _text(note: ExperimentNote | None) -> str | None:
    return None if note is None else note.text


class TestSetAndGet:
    def test_block_note_is_stored_under_the_block_key_with_timestamp(self):
        data: dict = {}

        note = set_note(data, 1, "Controle", SUBJECT_WILDCARD, "  luz piscou  ", now=FIXED_NOW)

        assert note == ExperimentNote(text="luz piscou", updated_at="2026-10-22T14:30:05")
        assert data[NOTES_KEY] == {
            "Dia_1|Controle|*": {"text": "luz piscou", "updated_at": "2026-10-22T14:30:05"}
        }

    def test_subject_note_is_stored_under_the_subject_key(self):
        data: dict = {}
        set_note(data, "Dia_2", "CBD", "3", "pulou do aquario", now=FIXED_NOW)

        assert list(data[NOTES_KEY]) == ["Dia_2|CBD|3"]
        assert get_note(data, 2, "CBD", "3") == ExperimentNote(
            "pulou do aquario", "2026-10-22T14:30:05"
        )
        # A subject note is not the block note.
        assert get_note(data, 2, "CBD") is None

    @pytest.mark.parametrize("day", [1, "1", "Dia_1", "Dia_01"])
    def test_any_day_format_reads_the_same_note(self, day):
        data: dict = {}
        set_note(data, "Dia_1", "Controle", "2", "nota", now=FIXED_NOW)

        assert _text(get_note(data, day, "Controle", "2")) == "nota"

    @pytest.mark.parametrize("blank", ["", "   \n\t", None])
    def test_blank_text_removes_the_note(self, blank):
        data: dict = {}
        set_note(data, 1, "Controle", "2", "nota", now=FIXED_NOW)

        assert set_note(data, 1, "Controle", "2", blank) is None
        assert data[NOTES_KEY] == {}
        assert get_note(data, 1, "Controle", "2") is None

    def test_set_note_does_not_touch_other_keys_of_the_project(self):
        data: dict[str, Any] = {
            "recording_duration_s": 300.0,
            NOTES_KEY: {"Dia_1|Outro|1": {"text": "x"}},
        }
        set_note(data, 1, "Controle", "2", "nota", now=FIXED_NOW)

        assert data["recording_duration_s"] == 300.0
        assert set(data[NOTES_KEY]) == {"Dia_1|Outro|1", "Dia_1|Controle|2"}

    def test_set_note_replaces_a_corrupt_notes_container(self):
        data: dict = {NOTES_KEY: "garbage"}
        set_note(data, 1, "Controle", "2", "nota", now=FIXED_NOW)

        assert data[NOTES_KEY] == {
            "Dia_1|Controle|2": {"text": "nota", "updated_at": "2026-10-22T14:30:05"}
        }

    def test_multiline_text_is_preserved(self):
        data: dict = {}
        set_note(data, 1, "G", "1", "linha 1\nlinha 2", now=FIXED_NOW)

        assert _text(get_note(data, 1, "G", "1")) == "linha 1\nlinha 2"


class TestLegacyNotes:
    def test_legacy_string_note_is_read_as_the_block_note(self):
        data = {NOTES_KEY: {"Dia_1_Controle": "nota antiga"}}

        assert get_note(data, 1, "Controle") == ExperimentNote("nota antiga", None)
        # ...and never as a subject note.
        assert get_note(data, 1, "Controle", "1") is None

    def test_writing_the_block_note_removes_the_legacy_key(self):
        data = {NOTES_KEY: {"Dia_1_Controle": "nota antiga"}}

        set_note(data, 1, "Controle", SUBJECT_WILDCARD, "nota nova", now=FIXED_NOW)

        assert "Dia_1_Controle" not in data[NOTES_KEY]
        assert _text(get_note(data, 1, "Controle")) == "nota nova"

    def test_clearing_the_block_note_does_not_resurrect_the_legacy_one(self):
        data = {NOTES_KEY: {"Dia_1_Controle": "nota antiga"}}

        set_note(data, 1, "Controle", SUBJECT_WILDCARD, "")

        assert get_note(data, 1, "Controle") is None
        assert data[NOTES_KEY] == {}

    def test_writing_a_subject_note_keeps_the_legacy_block_note(self):
        data = {NOTES_KEY: {"Dia_1_Controle": "nota antiga"}}

        set_note(data, 1, "Controle", "4", "sujeito", now=FIXED_NOW)

        assert _text(get_note(data, 1, "Controle")) == "nota antiga"


class TestDegradation:
    @pytest.mark.parametrize("raw", [42, None, {"text": ""}, {"text": 7}, ["a"], "   "])
    def test_unusable_value_is_skipped_not_raised(self, raw):
        data = {NOTES_KEY: {"Dia_1|Controle|2": raw}}

        assert get_note(data, 1, "Controle", "2") is None
        assert iter_notes(data) == []

    def test_non_string_timestamp_is_dropped_but_text_kept(self):
        data = {NOTES_KEY: {"Dia_1|Controle|2": {"text": "ok", "updated_at": 123}}}

        assert get_note(data, 1, "Controle", "2") == ExperimentNote("ok", None)

    def test_missing_or_corrupt_container_reads_as_empty(self):
        assert get_note(None, 1, "G") is None
        assert get_note({NOTES_KEY: ["x"]}, 1, "G") is None
        assert iter_notes({NOTES_KEY: "x"}) == []

    def test_unrecognized_key_is_skipped(self):
        data = {NOTES_KEY: {"lixo": "x", "a|b": "y", "Dia_1|G|1": "ok"}}

        records = iter_notes(data)

        assert [(r.day, r.group, r.subject) for r in records] == [("Dia_1", "G", "1")]


class TestIterNotes:
    def test_records_are_located_and_ordered(self):
        data: dict = {}
        set_note(data, 2, "B", "10", "d2 b s10", now=FIXED_NOW)
        set_note(data, 2, "B", "2", "d2 b s2", now=FIXED_NOW)
        set_note(data, 2, "B", SUBJECT_WILDCARD, "d2 b bloco", now=FIXED_NOW)
        set_note(data, 1, "A", "1", "d1 a s1", now=FIXED_NOW)
        data[NOTES_KEY]["Dia_10_A"] = "legado d10"

        located = [(r.day, r.group, r.subject, r.note.text) for r in iter_notes(data)]

        assert located == [
            ("Dia_1", "A", "1", "d1 a s1"),
            ("Dia_2", "B", None, "d2 b bloco"),
            ("Dia_2", "B", "2", "d2 b s2"),
            ("Dia_2", "B", "10", "d2 b s10"),
            ("Dia_10", "A", None, "legado d10"),
        ]

    def test_group_names_with_underscores_and_pipes_survive(self):
        data: dict = {}
        set_note(data, 1, "CBD_10mg", SUBJECT_WILDCARD, "bloco", now=FIXED_NOW)
        set_note(data, 1, "a|b", "3", "sujeito", now=FIXED_NOW)
        data[NOTES_KEY]["Dia_3_Grupo_X"] = "legado"

        located = {(r.day, r.group, r.subject) for r in iter_notes(data)}

        assert located == {
            ("Dia_1", "CBD_10mg", None),
            ("Dia_1", "a|b", "3"),
            ("Dia_3", "Grupo_X", None),
        }

    def test_new_block_note_wins_over_legacy_duplicate(self):
        data = {
            NOTES_KEY: {
                "Dia_1_Controle": "antiga",
                "Dia_1|Controle|*": {"text": "nova", "updated_at": "2026-01-01T00:00:00"},
            }
        }

        records = iter_notes(data)

        assert [r.note.text for r in records] == ["nova"]

    def test_legacy_zero_padded_day_is_normalized(self):
        records = iter_notes({NOTES_KEY: {"Dia_01_Controle": "x"}})

        assert [(r.day, r.subject) for r in records] == [("Dia_1", None)]


class TestBlockQueries:
    def test_collect_block_notes_splits_block_and_subjects(self):
        data: dict = {}
        set_note(data, 1, "Controle", SUBJECT_WILDCARD, "bloco", now=FIXED_NOW)
        set_note(data, 1, "Controle", "2", "s2", now=FIXED_NOW)
        set_note(data, 1, "CBD", "2", "outro grupo", now=FIXED_NOW)
        set_note(data, 2, "Controle", "2", "outro dia", now=FIXED_NOW)

        block_note, subject_notes = collect_block_notes(data, "Dia_01", "Controle")

        assert block_note is not None and block_note.text == "bloco"
        assert {k: v.text for k, v in subject_notes.items()} == {"2": "s2"}

    def test_block_has_notes_with_only_a_subject_note(self):
        data: dict = {}
        set_note(data, 1, "Controle", "5", "s5", now=FIXED_NOW)

        assert block_has_notes(data, 1, "Controle") is True
        assert block_has_notes(data, 1, "CBD") is False
        assert block_has_notes(data, 2, "Controle") is False

    def test_block_has_notes_with_only_a_legacy_block_note(self):
        assert block_has_notes({NOTES_KEY: {"Dia_1_Controle": "x"}}, 1, "Controle") is True

    def test_empty_project_has_no_notes(self):
        assert block_has_notes({}, 1, "Controle") is False
        assert collect_block_notes({}, 1, "Controle") == (None, {})
