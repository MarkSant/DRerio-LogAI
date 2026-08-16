"""
Extended unit tests for session_duration_resolver.py.
"""

from __future__ import annotations

from zebtrack.core.services.session_duration_resolver import (
    DEFAULT_RECORDING_DURATION_S,
    OVERRIDES_KEY,
    SUBJECT_WILDCARD,
    _coerce_positive_duration,
    _normalize_day,
    block_override_key,
    collect_block_durations,
    duration_override_key,
    resolve_session_duration,
    set_duration_override,
)


class TestNormalizeDay:
    """Test _normalize_day helper with all supported representations."""

    def test_empty_or_whitespace_returns_empty(self):
        assert _normalize_day("") == ""
        assert _normalize_day("   ") == ""

    def test_integer_and_string_digit(self):
        assert _normalize_day(1) == "Dia_1"
        assert _normalize_day("2") == "Dia_2"
        assert _normalize_day(" 3 ") == "Dia_3"

    def test_prefixed_variants(self):
        assert _normalize_day("Dia_1") == "Dia_1"
        assert _normalize_day("dia_1") == "Dia_1"
        assert _normalize_day("Dia 1") == "Dia_1"
        assert _normalize_day("D1") == "Dia_1"
        assert _normalize_day("d4") == "Dia_4"

    def test_leading_zero_stripped(self):
        assert _normalize_day("Dia_01") == "Dia_1"
        assert _normalize_day("05") == "Dia_5"
        assert _normalize_day("D03") == "Dia_3"

    def test_non_numeric_fallback(self):
        assert _normalize_day("Habituation") == "Habituation"
        assert _normalize_day("Dia_Special") == "Dia_Special"


class TestCoercePositiveDuration:
    """Test _coerce_positive_duration validation."""

    def test_valid_numbers(self):
        assert _coerce_positive_duration(60) == 60.0
        assert _coerce_positive_duration("120.5") == 120.5
        assert _coerce_positive_duration(300.0) == 300.0

    def test_invalid_or_non_positive_numbers(self):
        assert _coerce_positive_duration(0) is None
        assert _coerce_positive_duration(-10) is None
        assert _coerce_positive_duration(None) is None
        assert _coerce_positive_duration("abc") is None
        assert _coerce_positive_duration(float("nan")) is None


class TestKeysAndResolution:
    """Test duration_override_key, block_override_key, and resolve_session_duration."""

    def test_duration_override_key(self):
        key = duration_override_key(1, "Control", 3)
        assert key == "Dia_1|Control|3"

    def test_block_override_key(self):
        key = block_override_key(1, "Control")
        assert key == f"Dia_1|Control|{SUBJECT_WILDCARD}"

    def test_resolve_default_when_no_data(self):
        assert resolve_session_duration(None, 1, "Control", 1) == DEFAULT_RECORDING_DURATION_S
        assert resolve_session_duration({}, 1, "Control", 1) == DEFAULT_RECORDING_DURATION_S

    def test_resolve_project_default(self):
        proj_data = {"recording_duration_s": 450.0}
        assert resolve_session_duration(proj_data, 1, "Control", 1) == 450.0

    def test_resolve_block_override_takes_precedence_over_project(self):
        proj_data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {
                "Dia_1|Control|*": 180.0,
            },
        }
        assert resolve_session_duration(proj_data, 1, "Control", 1) == 180.0
        # Another group falls back to project default
        assert resolve_session_duration(proj_data, 1, "Treatment", 1) == 300.0

    def test_resolve_subject_override_takes_highest_precedence(self):
        proj_data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {
                "Dia_1|Control|*": 180.0,
                "Dia_1|Control|2": 600.0,
            },
        }
        # Subject 2 gets its specific override
        assert resolve_session_duration(proj_data, 1, "Control", 2) == 600.0
        # Subject 1 gets the block override
        assert resolve_session_duration(proj_data, 1, "Control", 1) == 180.0


class TestSetAndCollectDurationOverrides:
    """Test set_duration_override and collect_block_durations."""

    def test_set_duration_override_adds_entry(self):
        proj_data: dict = {}
        set_duration_override(proj_data, 1, "Control", 3, 240.0)
        assert proj_data[OVERRIDES_KEY]["Dia_1|Control|3"] == 240.0

    def test_set_duration_override_none_or_zero_clears_entry(self):
        proj_data: dict = {OVERRIDES_KEY: {"Dia_1|Control|3": 240.0}}
        set_duration_override(proj_data, 1, "Control", 3, None)
        assert "Dia_1|Control|3" not in proj_data[OVERRIDES_KEY]

        proj_data = {OVERRIDES_KEY: {"Dia_1|Control|3": 240.0}}
        set_duration_override(proj_data, 1, "Control", 3, 0.0)
        assert "Dia_1|Control|3" not in proj_data[OVERRIDES_KEY]

    def test_collect_block_durations(self):
        proj_data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {
                "Dia_1|Control|*": 180.0,
                "Dia_1|Control|2": 600.0,
            },
        }
        res = collect_block_durations(proj_data, 1, "Control", ["1", "2", "3"])
        assert res == {"1": 180.0, "2": 600.0, "3": 180.0}
