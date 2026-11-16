"""Tests for core/services/pattern_match.py: the one rule for the user's regex patterns.

F2-UI-003 (value of a match) and F2-UI-009 (case) used to live, in three diverging
copies, in the pattern dialog, the wizard's detection step and the project import.
"""

from __future__ import annotations

import re

import pytest

from zebtrack.core.services.pattern_match import (
    USER_PATTERN_FLAGS,
    compile_user_pattern,
    finditer_values,
    match_value,
    search_value,
)

ALTERNATION = r"Dia_(\d+)|D(\d+)"


class TestMatchValue:
    def test_takes_the_first_capture_group_when_there_is_one(self):
        match = re.search(r"Dia_(\d+)", "Controle_Dia_2.mp4")
        assert match is not None
        assert match_value(match) == "2"

    def test_takes_the_whole_match_when_the_pattern_has_no_group(self):
        match = re.search(r"Control|Treatment", "Video_Treatment_Day1.mp4")
        assert match is not None
        assert match_value(match) == "Treatment"

    def test_a_named_group_counts_as_a_group(self):
        match = re.search(r"Dia_(?P<day>\d+)", "Dia_12.mp4")
        assert match is not None
        assert match_value(match) == "12"

    def test_a_group_that_did_not_participate_is_skipped(self):
        match = re.search(ALTERNATION, "D3.mp4")
        assert match is not None
        assert match.group(1) is None  # the premise: group 1 is not the one that matched
        assert match_value(match) == "3"

    def test_the_first_of_two_participating_groups_wins(self):
        match = re.search(r"(Dia)_(\d+)", "Dia_7.mp4")
        assert match is not None
        assert match_value(match) == "Dia"

    def test_an_empty_group_that_took_part_is_the_value(self):
        match = re.search(r"Dia_(\d*)", "Dia_.mp4")
        assert match is not None
        assert match_value(match) == ""

    def test_with_groups_but_none_participating_the_whole_match_is_the_value(self):
        match = re.search(r"(Dia)?_x", "_x")
        assert match is not None
        assert match.group(1) is None
        assert match_value(match) == "_x"


class TestCompileUserPattern:
    def test_a_string_is_compiled_case_insensitively(self):
        compiled = compile_user_pattern(r"Dia_(\d+)")

        assert compiled.flags & USER_PATTERN_FLAGS
        assert compiled.search("dia_2") is not None

    def test_a_pattern_compiled_without_the_flag_is_recompiled_with_it(self):
        plain = re.compile(r"Dia_(\d+)")

        compiled = compile_user_pattern(plain)

        assert compiled is not plain
        assert compiled.pattern == plain.pattern
        assert compiled.search("DIA_2") is not None

    def test_a_pattern_that_already_has_the_flag_is_returned_as_is(self):
        already = re.compile(r"Dia_(\d+)", re.IGNORECASE)

        assert compile_user_pattern(already) is already

    def test_the_other_flags_of_a_compiled_pattern_are_kept(self):
        multiline = re.compile(r"^Dia", re.MULTILINE)

        assert compile_user_pattern(multiline).flags & re.MULTILINE

    def test_an_invalid_pattern_raises_re_error_for_the_caller_to_handle(self):
        with pytest.raises(re.error):
            compile_user_pattern("(")


class TestSearchValue:
    def test_the_search_ignores_case(self):
        assert search_value(r"Dia_(\d+)", "controle_dia_2.mp4") == "2"

    def test_the_value_comes_from_the_group_that_took_part(self):
        assert search_value(ALTERNATION, "D3.mp4") == "3"
        assert search_value(ALTERNATION, "Dia_4.mp4") == "4"

    def test_no_match_is_none_not_an_empty_string(self):
        assert search_value(r"Dia_(\d+)", "video.mp4") is None

    def test_an_empty_value_is_not_confused_with_no_match(self):
        assert search_value(r"Dia_(\d*)", "Dia_.mp4") == ""

    def test_the_first_match_in_the_text_is_used(self):
        assert search_value(r"S(\d+)", "S1--S2.mp4") == "1"

    def test_accepts_a_compiled_pattern(self):
        assert search_value(re.compile(r"Dia_(\d+)"), "DIA_9.mp4") == "9"


class TestFinditerValues:
    def test_one_value_per_match_in_order(self):
        assert finditer_values(r"S(\d+)", "G1_D1_S1--G1_D1_S2.mp4") == ["1", "2"]

    def test_matches_are_case_insensitive_and_use_the_participating_group(self):
        assert finditer_values(r"S(\d+)|sub(\d+)", "S1_SUB2_s3") == ["1", "2", "3"]

    def test_no_match_is_an_empty_list(self):
        assert finditer_values(r"S(\d+)", "video.mp4") == []

    def test_without_groups_each_whole_match_is_a_value(self):
        assert finditer_values(r"Control|Treatment", "Control_treatment.mp4") == [
            "Control",
            "treatment",
        ]
